
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, User
from app.repositories.stores import list_record_types, list_stores
from app.schemas.forms import bill_to_form, parse_bill_form
from app.security import admin_required, current_user, verify_csrf, writer_required
from app.services import audit_service
from app.services.duplicate_service import find_bill_duplicates, find_manual_duplicates
from app.services.import_service import save_bill
from app.utils.parsing import clean_str, parse_decimal, parse_reference
from app.web import flash, render

router = APIRouter()


def _ctx(db: Session, **extra) -> dict:
    recent_bills = db.scalars(select(EnergyBill).options(joinedload(EnergyBill.unit))
                              .where(EnergyBill.source == "manual").order_by(EnergyBill.id.desc()).limit(10)).all()
    recent_manual = db.scalars(select(ManualRecord).options(joinedload(ManualRecord.store),
                                                            joinedload(ManualRecord.record_type))
                               .order_by(ManualRecord.id.desc()).limit(10)).all()
    return {"stores": list_stores(db, only_active=True), "types": list_record_types(db),
            "recent_bills": recent_bills, "recent_manual": recent_manual, "form": {}, "errors": {}, "dups": [],
            "edit_bill": None, "edit_record": None, **extra}


@router.get("/manual")
def manual_page(request: Request, bill: int | None = None, record: int | None = None,
                store_id: int | None = None, user: User = Depends(writer_required), db: Session = Depends(get_db)):
    extra: dict = {"sel_store": store_id}
    if bill:
        b = db.get(EnergyBill, bill)
        if not b:
            raise HTTPException(404, "Conta não encontrada.")
        extra.update(edit_bill=b, form=bill_to_form(b), sel_store=b.unit.store_id, sel_unit=b.unit_id,
                     sel_type=b.record_type_id)
    elif record:
        r = db.get(ManualRecord, record)
        if not r:
            raise HTTPException(404, "Lançamento não encontrado.")
        form = {"reference": r.reference.strftime("%Y-%m"), "value": f"{r.value:.2f}".replace(".", ","),
                "notes": r.notes or "", **{f"f_{k}": str(v) for k, v in (r.data or {}).items()}}
        extra.update(edit_record=r, form=form, sel_store=r.store_id, sel_unit=r.unit_id, sel_type=r.record_type_id)
    return render(request, "manual/form.html", user=user, **_ctx(db, **extra))


@router.post("/manual", dependencies=[Depends(verify_csrf)])
async def manual_save(request: Request, user: User = Depends(writer_required), db: Session = Depends(get_db)):
    posted = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    edit_bill_id, edit_record_id = posted.get("edit_bill"), posted.get("edit_record")
    rtype = db.get(RecordType, int(posted["type_id"])) if (posted.get("type_id") or "").isdigit() else None
    store_id = int(posted["store_id"]) if (posted.get("store_id") or "").isdigit() else None
    unit_id = int(posted["unit_id"]) if (posted.get("unit_id") or "").isdigit() else None
    unit = db.get(ConsumerUnit, unit_id) if unit_id else None
    errors: dict[str, str] = {}
    if rtype is None:
        errors["type"] = "Selecione o tipo de registro."
    if store_id is None:
        errors["store"] = "Selecione a loja."
    if unit is not None and store_id is not None and unit.store_id != store_id:
        errors["unit"] = "A unidade não pertence à loja selecionada."
    if rtype is not None and rtype.is_bill and unit is None:
        errors["unit"] = "Selecione a unidade consumidora."

    def rerender(dups=None, status=400):
        return render(request, "manual/form.html", status_code=status, user=user,
                      **_ctx(db, form=posted, errors=errors, dups=dups or [], sel_store=store_id, sel_unit=unit_id,
                             sel_type=rtype.id if rtype else None,
                             edit_bill=db.get(EnergyBill, int(edit_bill_id)) if edit_bill_id else None,
                             edit_record=db.get(ManualRecord, int(edit_record_id)) if edit_record_id else None))

    action = posted.get("duplicate_action", "")
    if rtype is not None and rtype.is_bill:
        values, form_errors = parse_bill_form(posted)
        errors.update(form_errors)
        if errors:
            return rerender()
        existing = db.get(EnergyBill, int(edit_bill_id)) if edit_bill_id else None
        dups = find_bill_duplicates(db, unit.id, values["reference"], values["invoice_number"],
                                    exclude_id=existing.id if existing else None)
        if dups and action not in ("replace", "new"):
            return rerender(dups, 409)
        target = existing or (dups[0] if dups and action == "replace" else None)
        save_bill(db, unit, rtype.id, values, user.id, source="manual" if not target else target.source, replace=target)
        db.commit()
        flash(request, "Conta salva.")
        return RedirectResponse(f"/stores/{unit.store_id}?highlight={unit.id}&type_id={rtype.id}", status_code=303)

    # tipos manuais
    reference = parse_reference(posted.get("reference"))
    value = parse_decimal(posted.get("value"))
    if reference is None:
        errors["reference"] = "Informe o mês."
    if value is None:
        errors["value"] = "Informe o valor."
    data: dict = {}
    for f in (rtype.fields if rtype else []):
        raw = posted.get(f"f_{f['key']}")
        if clean_str(raw):
            num = parse_decimal(raw)
            if num is None:
                errors[f"f_{f['key']}"] = "Número inválido."
            else:
                data[f["key"]] = float(num)
    if errors:
        return rerender()
    existing = db.get(ManualRecord, int(edit_record_id)) if edit_record_id else None
    dups = find_manual_duplicates(db, store_id, unit_id, rtype.id, reference, exclude_id=existing.id if existing else None)
    if dups and action not in ("replace", "new"):
        return rerender(dups, 409)
    rec = existing or (dups[0] if dups and action == "replace" else None)
    if rec is None:
        rec = ManualRecord(store_id=store_id, record_type_id=rtype.id, created_by=user.id, reference=reference,
                           value=value)
        db.add(rec)
    rec.unit_id, rec.reference, rec.value, rec.data = unit_id, reference, value, data
    rec.notes, rec.updated_by = clean_str(posted.get("notes"), 2000), user.id
    db.flush()
    audit_service.log(db, user.id, "update" if existing or action == "replace" else "create", "manual_record", rec.id,
                      {"value": str(value), "reference": reference.isoformat(), "data": data})
    db.commit()
    flash(request, "Lançamento salvo.")
    return RedirectResponse(f"/stores/{store_id}?type_id={rtype.id}", status_code=303)


@router.post("/manual/bills/{bill_id}/delete", dependencies=[Depends(verify_csrf)])
def bill_delete(request: Request, bill_id: int, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    bill = db.get(EnergyBill, bill_id)
    if not bill:
        raise HTTPException(404, "Conta não encontrada.")
    unit_id = bill.unit_id
    audit_service.log(db, user.id, "delete", "energy_bill", bill.id,
                      {"reference": bill.reference.isoformat(), "total_value": str(bill.total_value)})
    db.delete(bill)
    db.commit()
    flash(request, "Conta excluída.", "info")
    return RedirectResponse(f"/units/{unit_id}", status_code=303)


@router.post("/manual/records/{record_id}/delete", dependencies=[Depends(verify_csrf)])
def record_delete(request: Request, record_id: int, user: User = Depends(admin_required),
                  db: Session = Depends(get_db)):
    rec = db.get(ManualRecord, record_id)
    if not rec:
        raise HTTPException(404, "Lançamento não encontrado.")
    store_id = rec.store_id
    audit_service.log(db, user.id, "delete", "manual_record", rec.id, {"reference": rec.reference.isoformat()})
    db.delete(rec)
    db.commit()
    flash(request, "Lançamento excluído.", "info")
    return RedirectResponse(f"/stores/{store_id}", status_code=303)


@router.get("/bills/{bill_id}/print")
def bill_print(request: Request, bill_id: int, doc: int = 0, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    from app.services import chart_service
    from app.services.calculation_service import variation

    bill = db.get(EnergyBill, bill_id)
    if not bill:
        raise HTTPException(404, "Conta não encontrada.")
    data = chart_service.bill_print_data(db, bill)
    items = bill.line_items or []
    return render(request, "bills/print.html", user=user, bill=bill, unit=bill.unit, store=bill.unit.store,
                  rtype=db.get(RecordType, bill.record_type_id), include_doc=bool(doc), items=items,
                  items_sum=sum((Decimal(str(i.get("value") or 0)) for i in items), Decimal(0)), variation=variation, **data)
