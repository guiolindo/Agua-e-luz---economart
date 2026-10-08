"""Ponto de energia (unidade consumidora) cadastrado de qualquer tela + lembretes de vencimento."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ConsumerUnit, RecordType, User
from app.repositories.stores import default_bill_type, list_record_types, list_stores
from app.security import alerts_required, verify_csrf, writer_required
from app.services import audit_service, due_service
from app.services.import_service import UnitConflict, create_unit
from app.utils.parsing import clean_str, normalize_uc, parse_date
from app.web import flash, render

router = APIRouter()


def _safe_next(value: str | None) -> str:
    return value if value and value.startswith("/") and not value.startswith("//") and "\\" not in value else "/"


@router.get("/points/new")
def point_form(request: Request, next: str = "/", fragment: int = 0, store_id: int | None = None,
               user: User = Depends(writer_required), db: Session = Depends(get_db)):
    ctx = {"stores": list_stores(db, only_active=True), "types": [t for t in list_record_types(db) if t.is_bill],
           "default_type": default_bill_type(db), "next": _safe_next(next), "store_id": store_id, "form": {}, "errors": {}}
    return render(request, "points/fragment.html" if fragment else "points/new.html", user=user, **ctx)


@router.post("/points", dependencies=[Depends(verify_csrf)])
def point_create(request: Request, store_id: int = Form(...), number: str = Form(..., max_length=40),
                 due_date: str = Form(...), description: str = Form("", max_length=200),
                 record_type_id: int | None = Form(None), next: str = Form("/"),
                 user: User = Depends(writer_required), db: Session = Depends(get_db)):
    errors: dict[str, str] = {}
    due = parse_date(due_date)
    if due is None:
        errors["due_date"] = "Informe a data de vencimento."
    if not normalize_uc(number):
        errors["number"] = "Informe o número da unidade consumidora."
    stores = list_stores(db, only_active=True)
    if store_id not in {s.id for s in stores}:
        errors["store_id"] = "Selecione a loja."
    rtype = db.get(RecordType, record_type_id) if record_type_id else default_bill_type(db)
    if errors:
        return render(request, "points/new.html", status_code=400, user=user, stores=stores,
                      types=[t for t in list_record_types(db) if t.is_bill], default_type=rtype, next=_safe_next(next),
                      store_id=store_id, form={"number": number, "description": description, "due_date": due_date},
                      errors=errors)
    existing = db.scalar(select(ConsumerUnit).where(ConsumerUnit.number_normalized == normalize_uc(number)))
    if existing is not None:
        # já cadastrado: só atualiza o dia de vencimento (e reabre o lembrete)
        existing.due_day, existing.due_ack = due.day, None
        audit_service.log(db, user.id, "update", "consumer_unit", existing.id, {"due_day": due.day, "quick": True})
        db.commit()
        flash(request, f"A unidade {existing.number} já existia ({existing.store.code}). Dia de vencimento atualizado para {due.day}.", "info")
        return RedirectResponse(_safe_next(next), status_code=303)
    try:
        unit = create_unit(db, store_id, number, clean_str(description, 200), rtype.id if rtype else None, user.id)
    except UnitConflict as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return RedirectResponse("/points/new", status_code=303)
    unit.due_day = due.day
    audit_service.log(db, user.id, "create", "consumer_unit", unit.id, {"due_day": due.day, "quick": True})
    db.commit()
    when = "hoje" if due == due_service.local_today() else f"dia {due.day} de cada mês"
    flash(request, f"Ponto de energia {unit.number} cadastrado em {unit.store.code}. Vencimento: {when}.")
    return RedirectResponse(_safe_next(next), status_code=303)


@router.get("/api/due")
def api_due(user: User = Depends(alerts_required), db: Session = Depends(get_db)):
    items = due_service.due_items(db)
    return JSONResponse({"today": due_service.local_today().isoformat(), "items": [i.as_dict() for i in items],
                         "can_ack": True})


@router.post("/api/due/{unit_id}/ack", dependencies=[Depends(verify_csrf)])
def api_due_ack(unit_id: int, user: User = Depends(alerts_required), db: Session = Depends(get_db)):
    unit = db.get(ConsumerUnit, unit_id)
    if unit is None:
        raise HTTPException(404, "Unidade não encontrada.")
    occ = due_service.acknowledge(db, unit)
    audit_service.log(db, user.id, "due_ack", "consumer_unit", unit.id, {"due": occ.isoformat() if occ else None})
    db.commit()
    return JSONResponse({"ok": True, "due": occ.isoformat() if occ else None})
