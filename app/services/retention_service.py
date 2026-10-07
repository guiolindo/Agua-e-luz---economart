"""Retenção de documentos: a foto/PDF original é removida do banco após `document_retention_days` (~6 meses).

Os dados lidos (conta, valores, JSON da IA) permanecem; só o arquivo some. O registro em `documents` fica com os
metadados (nome, hash, data) e `purged_at`, para a interface explicar que o original expirou.
"""
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import AuditLog, Document
from app.models.mixins import utcnow

log = logging.getLogger(__name__)


def purge_expired_documents(db: Session, retention_days: int | None = None) -> int:
    days = retention_days if retention_days is not None else get_settings().document_retention_days
    cutoff = utcnow() - timedelta(days=days)
    ids = list(db.scalars(select(Document.id).where(Document.data.is_not(None), Document.created_at < cutoff)))
    if not ids:
        return 0
    db.execute(update(Document).where(Document.id.in_(ids)).values(data=None, purged_at=utcnow()))
    db.add(AuditLog(action="purge", entity="document", entity_id=None,
                    details={"count": len(ids), "retention_days": days}))
    db.commit()
    log.info("Retenção: %d documento(s) removido(s) (mais de %d dias).", len(ids), days)
    return len(ids)


def _run_once() -> None:
    with SessionLocal() as db:
        purge_expired_documents(db)


async def retention_loop() -> None:
    """Roda na subida e depois a cada `retention_check_hours`. Falhas são logadas e nunca derrubam o app."""
    interval = max(1, get_settings().retention_check_hours) * 3600
    while True:
        try:
            await asyncio.to_thread(_run_once)
        except Exception:
            log.exception("Falha na rotina de retenção de documentos")
        await asyncio.sleep(interval)
