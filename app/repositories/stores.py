from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import ConsumerUnit, RecordType, Store


def list_stores(db: Session, only_active: bool = False) -> list[Store]:
    stmt = select(Store).options(selectinload(Store.units)).order_by(Store.code)
    if only_active:
        stmt = stmt.where(Store.active.is_(True))
    return list(db.scalars(stmt))


def get_store_by_code(db: Session, code: str) -> Store | None:
    return db.scalar(select(Store).where(func.lower(Store.code) == code.strip().lower()))


def list_units(db: Session, store_id: int | None = None, only_active: bool = False) -> list[ConsumerUnit]:
    stmt = select(ConsumerUnit).order_by(ConsumerUnit.number)
    if store_id:
        stmt = stmt.where(ConsumerUnit.store_id == store_id)
    if only_active:
        stmt = stmt.where(ConsumerUnit.active.is_(True))
    return list(db.scalars(stmt))


def list_record_types(db: Session, only_active: bool = True) -> list[RecordType]:
    stmt = select(RecordType).order_by(RecordType.sort_order, RecordType.name)
    if only_active:
        stmt = stmt.where(RecordType.active.is_(True))
    return list(db.scalars(stmt))


def default_bill_type(db: Session) -> RecordType | None:
    return db.scalar(select(RecordType).where(RecordType.kind == "bill", RecordType.active.is_(True))
                     .order_by(RecordType.sort_order))
