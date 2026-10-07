from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import EnergyBill, ManualRecord


def find_bill_duplicates(
    db: Session,
    unit_id: int,
    reference: date | None,
    invoice_number: str | None = None,
    exclude_id: int | None = None,
) -> list[EnergyBill]:
    """Mesma unidade + mesmo mês, ou mesma unidade + mesmo número de nota."""
    conditions = []
    if reference is not None:
        conditions.append(EnergyBill.reference == reference.replace(day=1))
    if invoice_number:
        conditions.append(EnergyBill.invoice_number == invoice_number)
    if not conditions:
        return []
    stmt = select(EnergyBill).where(EnergyBill.unit_id == unit_id, or_(*conditions))
    if exclude_id:
        stmt = stmt.where(EnergyBill.id != exclude_id)
    return list(db.scalars(stmt.order_by(EnergyBill.reference)))


def find_manual_duplicates(
    db: Session, store_id: int, unit_id: int | None, record_type_id: int, reference: date, exclude_id: int | None = None
) -> list[ManualRecord]:
    stmt = select(ManualRecord).where(
        ManualRecord.store_id == store_id,
        ManualRecord.record_type_id == record_type_id,
        ManualRecord.reference == reference.replace(day=1),
        ManualRecord.unit_id.is_(None) if unit_id is None else ManualRecord.unit_id == unit_id,
    )
    if exclude_id:
        stmt = stmt.where(ManualRecord.id != exclude_id)
    return list(db.scalars(stmt))
