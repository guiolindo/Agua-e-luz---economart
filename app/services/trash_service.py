"""Lixeira: excluir uma conta ou lançamento guarda a linha inteira; o administrador restaura com um clique.

Também barra a exclusão em massa: quem não é administrador pode excluir até `max_deletes_per_hour` itens por hora.
Passou disso (ex.: alguém apagando tudo antes de sair da empresa), a exclusão é recusada, fica registrada na
auditoria e aparece no Painel admin e na Lixeira.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, EnergyBill, Import, ManualRecord, RecordType, TrashItem, User
from app.models.mixins import utcnow
from app.services import audit_service
from app.utils import formatting as fmt

KINDS = {"energy_bill": EnergyBill, "manual_record": ManualRecord}
KIND_LABELS = {"energy_bill": "Conta", "manual_record": "Lançamento manual"}


class TrashError(ValueError):
    pass


def _dump(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


def _load(col, v):
    if v is None:
        return None
    if isinstance(col.type, DateTime):
        return datetime.fromisoformat(v)
    if isinstance(col.type, Date):
        return date.fromisoformat(v)
    if isinstance(col.type, Numeric):
        return Decimal(v)
    return v


def _summary(db: Session, obj) -> tuple[str, int | None]:
    if isinstance(obj, EnergyBill):
        store = obj.unit.store if obj.unit else None
        rtype = db.get(RecordType, obj.record_type_id)
        parts = [store.short_label if store else "—", rtype.name if rtype else "Conta", f"UC {obj.unit.number}" if obj.unit else None,
                 fmt.month_label(obj.reference), fmt.brl(obj.total_value)]
        return " · ".join(p for p in parts if p), store.id if store else None
    parts = [obj.store.short_label if obj.store else "—", obj.record_type.name if obj.record_type else "Lançamento",
             fmt.month_label(obj.reference), fmt.brl(obj.value)]
    return " · ".join(parts), obj.store_id


def deletes_last_hour(db: Session, user_id: int) -> int:
    since = utcnow() - timedelta(hours=1)
    return db.scalar(select(func.count()).select_from(TrashItem)
                     .where(TrashItem.deleted_by == user_id, TrashItem.deleted_at >= since)) or 0


def check_can_delete(db: Session, user: User) -> None:
    """Barra exclusão em massa (administrador fica de fora: é quem restaura)."""
    limit = get_settings().max_deletes_per_hour
    if user.is_admin or limit <= 0:
        return
    if deletes_last_hour(db, user.id) >= limit:
        audit_service.log(db, user.id, "delete_blocked", "trash", None, {"limit_per_hour": limit})
        db.commit()
        raise TrashError(f"Exclusão bloqueada: foram {limit} exclusões na última hora. Por segurança, o sistema "
                         "pausa novas exclusões; se for uma correção grande, peça ao administrador.")


def move_to_trash(db: Session, obj, user: User) -> TrashItem:
    kind = next(k for k, m in KINDS.items() if isinstance(obj, m))
    summary, store_id = _summary(db, obj)
    payload = {c.name: _dump(getattr(obj, c.key)) for c in obj.__table__.columns}
    item = TrashItem(kind=kind, original_id=obj.id, store_id=store_id, summary=summary[:300], payload=payload,
                     deleted_by=user.id)
    db.add(item)
    if kind == "energy_bill":
        db.execute(update(Import).where(Import.bill_id == obj.id).values(bill_id=None))   # FK no Postgres
    db.flush()
    audit_service.log(db, user.id, "delete", kind, obj.id, {"trash_id": item.id, "resumo": summary})
    db.delete(obj)
    return item


def _conflict(db: Session, model, values: dict):
    if model is EnergyBill:
        return db.scalar(select(EnergyBill).where(EnergyBill.unit_id == values["unit_id"],
                                                  EnergyBill.record_type_id == values["record_type_id"],
                                                  EnergyBill.reference == values["reference"]).limit(1))
    stmt = select(ManualRecord).where(ManualRecord.store_id == values["store_id"],
                                      ManualRecord.record_type_id == values["record_type_id"],
                                      ManualRecord.reference == values["reference"])
    stmt = stmt.where(ManualRecord.unit_id == values["unit_id"]) if values.get("unit_id") else stmt.where(ManualRecord.unit_id.is_(None))
    return db.scalar(stmt.limit(1))


def _values(item: TrashItem) -> tuple[type, dict, dict]:
    model = KINDS[item.kind]
    cols = {c.name: c for c in model.__table__.columns}
    return model, cols, {name: _load(cols[name], v) for name, v in item.payload.items() if name in cols}


def relaunched(db: Session, item: TrashItem):
    """O mesmo mês (mesma unidade/loja e tipo) foi lançado de novo depois da exclusão: não há o que restaurar."""
    model, _, values = _values(item)
    return _conflict(db, model, values)


def personal_cutoff() -> datetime:
    return utcnow() - timedelta(days=get_settings().trash_personal_days)


def can_restore(user: User, item: TrashItem) -> bool:
    """Quem excluiu desfaz sozinho por `trash_personal_days` (30); depois disso, e para itens de outras pessoas,
    só o administrador (até `trash_days`)."""
    if user.is_admin:
        return True
    deleted_at = item.deleted_at if item.deleted_at.tzinfo else item.deleted_at.replace(tzinfo=timezone.utc)
    return item.deleted_by == user.id and deleted_at >= personal_cutoff()


def restore(db: Session, item: TrashItem, user: User):
    if item.restored_at is not None:
        raise TrashError("Este item já foi restaurado.")
    model, cols, values = _values(item)
    if _conflict(db, model, values) is not None:
        raise TrashError(f"Não precisa restaurar: {item.summary.rsplit(' · ', 1)[0]} já foi lançada de novo.")
    if db.get(model, values["id"]) is not None:      # número reaproveitado pelo banco: volta com um número novo
        values.pop("id")
    obj = model(**{cols[n].key: v for n, v in values.items()})
    db.add(obj)
    item.restored_at, item.restored_by = utcnow(), user.id
    db.flush()
    audit_service.log(db, user.id, "restore", item.kind, obj.id, {"trash_id": item.id, "resumo": item.summary})
    return obj


def purge_old(db: Session, days: int | None = None) -> int:
    """Itens com mais de `trash_days` na lixeira saem de vez (a auditoria continua com o resumo)."""
    days = days if days is not None else get_settings().trash_days
    cutoff = utcnow() - timedelta(days=days)
    old = list(db.scalars(select(TrashItem).where(TrashItem.deleted_at < cutoff)))
    for it in old:
        doc_id = (it.payload or {}).get("document_id") if it.kind == "energy_bill" and it.restored_at is None else None
        db.delete(it)
        if doc_id and db.scalar(select(EnergyBill.id).where(EnergyBill.document_id == doc_id)) is None:
            # conta excluída de vez: a foto/PDF sai junto (a privacidade de antes da lixeira continua valendo)
            db.execute(update(Document).where(Document.id == doc_id, Document.data.is_not(None))
                       .values(data=None, purged_at=utcnow()))
    if old:
        audit_service.log(db, None, "purge", "trash", None, {"count": len(old), "trash_days": days})
        db.commit()
    return len(old)


def recent_blocks(db: Session, days: int = 7):
    from app.models import AuditLog
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return list(db.scalars(select(AuditLog).where(AuditLog.action == "delete_blocked", AuditLog.at >= since)
                           .order_by(AuditLog.id.desc()).limit(20)))
