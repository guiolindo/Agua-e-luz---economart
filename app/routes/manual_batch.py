"""Lançamento manual em lote: um valor (LL Energia) para várias lojas de uma vez."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ManualRecord, RecordType, User
from app.repositories.stores import list_record_types, list_stores
from app.security import verify_csrf, writer_required
from app.services import audit_service
from app.services.duplicate_service import find_manual_duplicates
from app.utils import formatting as fmt
from app.utils.parsing import clean_str, parse_date, parse_decimal, parse_reference
from app.utils.timezone import local_today
from app.web import flash, render

router = APIRouter()
DEFAULT_TYPE_CODE = "ll-energia"
MAX_VALUE = Decimal("999999999999.99")   # Numeric(14, 2)


def _ctx(db: Session, **extra) -> dict:
    types = [t for t in list_record_types(db) if t.is_batch_only]
    sel = extra.pop("sel_type", None)
    chosen = next((t for t in types if t.id == sel), None) or next((t for t in types if t.code == DEFAULT_TYPE_CODE), None) \
        or (types[0] if types else None)
    return {"types": types, "stores": list_stores(db, only_active=True), "sel_type": chosen.id if chosen else None,
            "form": {}, "errors": {}, "selected": set(), "dups": [], **extra}


@router.get("/manual/lote")
def batch_page(request: Request, type: str | None = None, user: User = Depends(writer_required),
               db: Session = Depends(get_db)):
    types = [t for t in list_record_types(db) if t.is_batch_only]
    sel = next((t.id for t in types if t.code == (type or DEFAULT_TYPE_CODE)), None)
    prev = local_today().replace(day=1)
    prev = prev.replace(year=prev.year - 1, month=12) if prev.month == 1 else prev.replace(month=prev.month - 1)
    return render(request, "manual/batch.html", user=user,
                  **_ctx(db, sel_type=sel, form={"reference": prev.strftime("%Y-%m")}))


@router.post("/manual/lote", dependencies=[Depends(verify_csrf)])
async def batch_save(request: Request, user: User = Depends(writer_required), db: Session = Depends(get_db)):
    raw = await request.form()
    posted = {k: v for k, v in raw.items() if isinstance(v, str)}
    ids = {int(x) for x in raw.getlist("store_ids") if str(x).isdigit()}
    rtype = db.get(RecordType, int(posted["type_id"])) if (posted.get("type_id") or "").isdigit() else None
    active_stores = {s.id: s for s in list_stores(db, only_active=True)}
    errors: dict[str, str] = {}

    if rtype is None or not rtype.is_batch_only or not rtype.active:
        errors["type"] = "Selecione o tipo de lançamento."
    reference = parse_reference(posted.get("reference"))
    if reference is None:
        errors["reference"] = "Informe o mês."
    value = parse_decimal(posted.get("value"))
    if value is None:
        errors["value"] = "Informe o valor."
    elif abs(value) > MAX_VALUE:
        errors["value"] = "Valor grande demais."
    due_date = parse_date(posted.get("due_date"))
    if clean_str(posted.get("due_date")) and due_date is None:
        errors["due_date"] = "Data inválida."
    data: dict = {}
    for f in (rtype.fields if rtype else []):
        txt = posted.get(f"f_{f['key']}")
        if clean_str(txt):
            num = parse_decimal(txt)
            if num is None:
                errors[f"f_{f['key']}"] = "Número inválido."
            else:
                data[f["key"]] = float(num)
    if not ids:
        errors["stores"] = "Marque pelo menos uma loja."
    elif not ids <= set(active_stores):
        errors["stores"] = "Há loja inválida ou inativa na seleção. Atualize a página e tente de novo."

    def rerender(dups=None, status=400):
        return render(request, "manual/batch.html", status_code=status, user=user,
                      **_ctx(db, sel_type=rtype.id if rtype else None, form=posted, errors=errors, selected=ids, dups=dups or []))

    if errors:
        return rerender()

    chosen = sorted((active_stores[i] for i in ids), key=lambda s: s.code)
    dups = {s.id: find_manual_duplicates(db, s.id, None, rtype.id, reference) for s in chosen}
    dups = {sid: found for sid, found in dups.items() if found}
    action = posted.get("duplicate_action", "")
    if dups and action not in ("skip", "replace"):
        return rerender([{"store": active_stores[sid], "record": found[0]} for sid, found in dups.items()], 409)

    batch = uuid.uuid4().hex[:8]
    notes = clean_str(posted.get("notes"), 2000)
    created = replaced = skipped = 0
    for s in chosen:
        found = dups.get(s.id)
        if found and action == "skip":
            skipped += 1
            continue
        rec = found[0] if found else ManualRecord(store_id=s.id, record_type_id=rtype.id, created_by=user.id,
                                                   reference=reference, value=value)
        if not found:
            db.add(rec)
        rec.unit_id, rec.reference, rec.value, rec.data, rec.due_date = None, reference, value, dict(data), due_date
        rec.notes, rec.updated_by = notes, user.id
        db.flush()
        audit_service.log(db, user.id, "update" if found else "create", "manual_record", rec.id,
                          {"value": str(value), "reference": reference.isoformat(), "data": data, "batch": batch})
        replaced, created = (replaced + 1, created) if found else (replaced, created + 1)
    db.commit()

    parts = [f"{created} novo(s)"] if created else []
    if replaced:
        parts.append(f"{replaced} substituído(s)")
    if skipped:
        parts.append(f"{skipped} já existia(m) e foi(ram) mantido(s)")
    flash(request, f"{rtype.name} de {fmt.month_label(reference)}: {fmt.brl(value)} em {created + replaced} {'loja' if created + replaced == 1 else 'lojas'}"
                   f" ({', '.join(parts)}).")
    month = reference.strftime("%Y-%m")
    return RedirectResponse(f"/notas?type_id={rtype.id}&start={month}&end={month}&origin=manual", status_code=303)
