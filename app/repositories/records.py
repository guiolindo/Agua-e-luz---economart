"""Consultas de registros (contas e lançamentos manuais) por período."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import ConsumerUnit, EnergyBill, ManualRecord


def bills_for_units(db: Session, unit_ids: list[int], start: date | None = None, end: date | None = None,
                    record_type_id: int | None = None) -> list[EnergyBill]:
    if not unit_ids:
        return []
    stmt = select(EnergyBill).where(EnergyBill.unit_id.in_(unit_ids))
    if start:
        stmt = stmt.where(EnergyBill.reference >= start)
    if end:
        stmt = stmt.where(EnergyBill.reference <= end)
    if record_type_id:
        stmt = stmt.where(EnergyBill.record_type_id == record_type_id)
    return list(db.scalars(stmt.order_by(EnergyBill.reference, EnergyBill.id)))


def manual_for_store(db: Session, store_id: int, start: date | None = None, end: date | None = None,
                     record_type_id: int | None = None) -> list[ManualRecord]:
    stmt = select(ManualRecord).options(joinedload(ManualRecord.unit)).where(ManualRecord.store_id == store_id)
    if start:
        stmt = stmt.where(ManualRecord.reference >= start)
    if end:
        stmt = stmt.where(ManualRecord.reference <= end)
    if record_type_id:
        stmt = stmt.where(ManualRecord.record_type_id == record_type_id)
    return list(db.scalars(stmt.order_by(ManualRecord.reference, ManualRecord.id)))


def latest_reference(db: Session, store_id: int | None = None) -> date | None:
    """Mês mais recente com algum dado (conta ou lançamento)."""
    q1 = select(EnergyBill.reference)
    q2 = select(ManualRecord.reference)
    if store_id:
        q1 = q1.join(ConsumerUnit, ConsumerUnit.id == EnergyBill.unit_id).where(ConsumerUnit.store_id == store_id)
        q2 = q2.where(ManualRecord.store_id == store_id)
    refs = [db.scalar(q1.order_by(EnergyBill.reference.desc()).limit(1)),
            db.scalar(q2.order_by(ManualRecord.reference.desc()).limit(1))]
    refs = [r for r in refs if r]
    return max(refs) if refs else None


def earliest_reference(db: Session, store_id: int) -> date | None:
    q1 = (select(EnergyBill.reference).join(ConsumerUnit, ConsumerUnit.id == EnergyBill.unit_id)
          .where(ConsumerUnit.store_id == store_id).order_by(EnergyBill.reference).limit(1))
    q2 = select(ManualRecord.reference).where(ManualRecord.store_id == store_id).order_by(ManualRecord.reference).limit(1)
    refs = [r for r in (db.scalar(q1), db.scalar(q2)) if r]
    return min(refs) if refs else None
