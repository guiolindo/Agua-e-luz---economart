from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ConsumerUnit, EnergyBill, Import, ManualRecord, Store
from app.repositories import records as repo
from app.repositories.stores import list_record_types
from app.services.calculation_service import add_months


def overview(db: Session, month: date | None = None) -> dict:
    month = (month or repo.latest_reference(db) or date.today().replace(day=1)).replace(day=1)
    prev = add_months(month, -1)

    stores = db.scalar(select(func.count()).select_from(Store).where(Store.active.is_(True))) or 0
    units = db.scalar(select(func.count()).select_from(ConsumerUnit).where(ConsumerUnit.active.is_(True))) or 0
    bills_in_month = db.scalar(select(func.count()).select_from(EnergyBill).where(EnergyBill.reference == month)) or 0
    manual_in_month = db.scalar(select(func.count()).select_from(ManualRecord)
                                .where(ManualRecord.reference == month)) or 0

    pending = pending_items(db, month, prev)
    last_import = db.scalar(select(Import).where(Import.status == "confirmed").order_by(Import.updated_at.desc()).limit(1))
    last_store = None
    if last_import and last_import.bill_id:
        bill = db.get(EnergyBill, last_import.bill_id)
        if bill:
            last_store = bill.unit.store
    return {
        "month": month, "stores": stores, "units": units, "records_in_month": bills_in_month + manual_in_month,
        "pending": pending, "last_import": last_import, "last_store": last_store,
    }


def pending_items(db: Session, month: date, prev: date) -> list[dict]:
    """Pendências do mês: unidades de conta sem conta lançada + lançamentos recorrentes do mês anterior sem repetição."""
    items: list[dict] = []
    have_bill = set(db.scalars(select(EnergyBill.unit_id).where(EnergyBill.reference == month)))
    types = {t.id: t for t in list_record_types(db, only_active=False)}
    default_bill_type = next((t for t in types.values() if t.is_bill), None)
    units = db.scalars(select(ConsumerUnit).join(Store).where(ConsumerUnit.active.is_(True), Store.active.is_(True))
                       .order_by(Store.code, ConsumerUnit.number))
    for u in units:
        rt = types.get(u.record_type_id) if u.record_type_id else default_bill_type
        if rt is not None and rt.is_bill and u.id not in have_bill:
            items.append({"store": u.store, "unit": u, "type": rt, "text": "Conta do mês não lançada"})

    cur = {(r.store_id, r.unit_id, r.record_type_id) for r in
           db.scalars(select(ManualRecord).where(ManualRecord.reference == month))}
    for r in db.scalars(select(ManualRecord).where(ManualRecord.reference == prev)):
        if (r.store_id, r.unit_id, r.record_type_id) not in cur and types[r.record_type_id].active:
            items.append({"store": r.store, "unit": r.unit, "type": r.record_type,
                          "text": "Lançado no mês anterior; falta este mês"})
    return items
