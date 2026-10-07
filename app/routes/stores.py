from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ConsumerUnit, Store, User
from app.repositories.stores import (
    default_bill_type,
    get_store_by_code,
    list_record_types,
    list_stores,
)
from app.security import current_user, verify_csrf, writer_required
from app.services import audit_service, chart_service, due_service
from app.services.import_service import UnitConflict, create_unit
from app.utils.parsing import clean_str, normalize_uc, parse_due_day, parse_reference
from app.web import flash, render

router = APIRouter()


def parse_aliases(text: str) -> list[str]:
    seen, out = set(), []
    for a in (text or "").replace(";", ",").split(","):
        a = a.strip()[:60]
        if a and a.lower() not in seen:
            seen.add(a.lower())
            out.append(a)
    return out[:20]


def _store_or_404(db: Session, store_id: int) -> Store:
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Loja não encontrada.")
    return store


@router.get("/stores")
def stores_list(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "stores/list.html", user=user, stores=list_stores(db))


@router.get("/stores/new")
def store_new(request: Request, user: User = Depends(writer_required)):
    return render(request, "stores/form.html", user=user, store=None)


@router.post("/stores", dependencies=[Depends(verify_csrf)])
def store_create(request: Request, code: str = Form(...), name: str = Form(""), location: str = Form(""),
                 aliases: str = Form(""), notes: str = Form(""), region: str = Form(""),
                 user: User = Depends(writer_required), db: Session = Depends(get_db)):
    code = code.strip().upper()
    if not code:
        flash(request, "Informe o código da loja.", "error")
        return RedirectResponse("/stores/new", status_code=303)
    if get_store_by_code(db, code):
        return render(request, "stores/form.html", status_code=409, user=user, store=None,
                      error=f"Já existe uma loja com o código {code}.",
                      form={"code": code, "name": name, "location": location, "aliases": aliases,
                                          "notes": notes})
    store = Store(code=code, name=clean_str(name, 200), location=clean_str(location, 200), notes=clean_str(notes),
                  aliases=parse_aliases(aliases), region=(clean_str(region, 20) or "").upper() or None)
    db.add(store)
    db.flush()
    audit_service.log(db, user.id, "create", "store", store.id, {"code": code})
    db.commit()
    flash(request, f"Loja {code} cadastrada. Agora cadastre as unidades consumidoras.")
    return RedirectResponse(f"/stores/{store.id}/settings", status_code=303)


@router.get("/stores/{store_id}")
def store_history(request: Request, store_id: int, type_id: int | None = None, indicator: str | None = None,
                  view: str = "units", start: str | None = None, end: str | None = None,
                  highlight: int | None = None, unit_id: int | None = None, by: str = "reference",
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    store = _store_or_404(db, store_id)
    by = "due" if by == "due" else "reference"
    types = list_record_types(db)
    chosen = next((t for t in types if t.id == type_id), None) or default_bill_type(db) or (types[0] if types else None)
    start_d, end_d = chart_service.default_range(db, store.id, parse_reference(start), parse_reference(end))
    summary = chart_service.store_summary(db, store, start_d, end_d, by)
    return render(request, "stores/history.html", user=user, store=store, types=types, chosen=chosen,
                  view=view if view in ("units", "types") else "units", indicator=indicator, start=start_d, end=end_d,
                  highlight=highlight, unit_id=unit_id, summary=summary, by=by)


@router.get("/stores/{store_id}/settings")
def store_settings(request: Request, store_id: int, user: User = Depends(writer_required),
                   db: Session = Depends(get_db)):
    return render(request, "stores/settings.html", user=user, store=_store_or_404(db, store_id),
                  types=list_record_types(db))


@router.post("/stores/{store_id}/edit", dependencies=[Depends(verify_csrf)])
def store_edit(request: Request, store_id: int, name: str = Form(""), location: str = Form(""),
               aliases: str = Form(""), notes: str = Form(""), active: str = Form(""), region: str = Form(""),
               user: User = Depends(writer_required), db: Session = Depends(get_db)):
    store = _store_or_404(db, store_id)
    store.name, store.location, store.notes = clean_str(name, 200), clean_str(location, 200), clean_str(notes)
    store.aliases = parse_aliases(aliases)
    store.region = (clean_str(region, 20) or "").upper() or None
    store.active = bool(active)
    audit_service.log(db, user.id, "update", "store", store.id)
    db.commit()
    flash(request, "Loja atualizada.")
    return RedirectResponse(f"/stores/{store_id}/settings", status_code=303)


@router.post("/stores/{store_id}/units", dependencies=[Depends(verify_csrf)])
def unit_add(request: Request, store_id: int, number: str = Form(...), description: str = Form(""),
             internal_code: str = Form(""), record_type_id: int | None = Form(None), due_day: str = Form(""),
             user: User = Depends(writer_required), db: Session = Depends(get_db)):
    store = _store_or_404(db, store_id)
    day, ok = parse_due_day(due_day)
    if not ok:
        flash(request, "Dia de vencimento inválido (use de 1 a 31).", "error")
        return RedirectResponse(f"/stores/{store_id}/settings", status_code=303)
    try:
        unit = create_unit(db, store.id, number, clean_str(description, 200), record_type_id, user.id)
        unit.internal_code, unit.due_day = clean_str(internal_code, 60), day
        db.commit()
        flash(request, f"Unidade {unit.number} adicionada." + (f" Vence todo dia {day}." if day else
              " Defina o dia de vencimento (Editar) para receber o aviso."))
    except UnitConflict as exc:
        db.rollback()
        flash(request, str(exc), "error")
    return RedirectResponse(f"/stores/{store_id}/settings", status_code=303)


@router.get("/units/{unit_id}/edit")
def unit_edit_page(request: Request, unit_id: int, user: User = Depends(writer_required), db: Session = Depends(get_db)):
    unit = db.get(ConsumerUnit, unit_id)
    if not unit:
        raise HTTPException(404, "Unidade não encontrada.")
    nxt = due_service.next_occurrence(unit.due_day, due_service.local_today()) if unit.due_day else None
    return render(request, "units/edit.html", user=user, unit=unit, store=unit.store, stores=list_stores(db),
                  types=[t for t in list_record_types(db) if t.is_bill], next_due=nxt, errors={}, form=None)


@router.post("/units/{unit_id}/edit", dependencies=[Depends(verify_csrf)])
async def unit_edit(request: Request, unit_id: int, number: str = Form(...), description: str = Form(""),
                    internal_code: str = Form(""), notes: str = Form(""), record_type_id: int | None = Form(None),
                    active: str = Form(""), store_id: int | None = Form(None),
                    user: User = Depends(writer_required), db: Session = Depends(get_db)):
    unit = db.get(ConsumerUnit, unit_id)
    if not unit:
        raise HTTPException(404, "Unidade não encontrada.")
    # FastAPI trata campo vazio como ausente: lê o formulário bruto para separar "não mexer" de "limpar o vencimento"
    form = await request.form()
    due_day = form.get("due_day") if "due_day" in form else None
    key = normalize_uc(number)
    clash = db.query(ConsumerUnit).filter(ConsumerUnit.number_normalized == key, ConsumerUnit.id != unit.id).first()
    day, day_ok = parse_due_day(due_day) if due_day is not None else (unit.due_day, True)   # None = campo ausente: não altera
    if not key or clash or not day_ok:
        flash(request, "Dia de vencimento inválido (use de 1 a 31)." if not day_ok else
              "Número de unidade inválido ou já cadastrado.", "error")
        return RedirectResponse(f"/units/{unit.id}/edit", status_code=303)
    before = {"number": unit.number, "due_day": unit.due_day, "active": unit.active, "store_id": unit.store_id}
    unit.number, unit.number_normalized = number.strip(), key
    unit.description, unit.internal_code, unit.notes = (clean_str(description, 200), clean_str(internal_code, 60),
                                                       clean_str(notes))
    unit.record_type_id, unit.active = record_type_id, bool(active)
    if store_id and db.get(Store, store_id):
        unit.store_id = store_id
    if day != unit.due_day:
        unit.due_ack = None          # mudou o dia: o aviso do novo vencimento volta a valer
    unit.due_day = day
    audit_service.log(db, user.id, "update", "consumer_unit", unit.id,
                      {"before": before, "after": {"number": unit.number, "due_day": day, "active": unit.active,
                                                   "store_id": unit.store_id}})
    db.commit()
    flash(request, "Unidade atualizada." + (f" Vence todo dia {day}." if day else " Sem dia de vencimento (não gera aviso)."))
    return RedirectResponse(f"/units/{unit.id}", status_code=303)


@router.get("/units/{unit_id}")
def unit_page(request: Request, unit_id: int, indicator: str | None = None, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    unit = db.get(ConsumerUnit, unit_id)
    if not unit:
        raise HTTPException(404, "Unidade não encontrada.")
    rtype = unit.record_type or default_bill_type(db)
    overview = chart_service.unit_overview(db, unit)
    return render(request, "units/detail.html", user=user, unit=unit, store=unit.store, rtype=rtype,
                  indicators=chart_service.indicators_for_type(rtype) if rtype else [], indicator=indicator,
                  **overview)


@router.get("/stores/{store_id}/report")
def store_report(request: Request, store_id: int, start: str | None = None, end: str | None = None,
                 by: str = "reference", type_id: int | None = None, all: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from datetime import datetime, timezone

    store = _store_or_404(db, store_id)
    by = "due" if by == "due" else "reference"
    data = chart_service.report_data(db, store, parse_reference(start), parse_reference(end), by, type_id, bool(all))
    return render(request, "stores/report.html", user=user, store=store, generated=datetime.now(timezone.utc), **data)
