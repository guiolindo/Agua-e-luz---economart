"""Auditoria com cadeia de integridade (à prova de adulteração).

Cada evento grava `row_hash = HMAC(chave, prev_hash | conteúdo)`, onde `prev_hash` é o hash do evento anterior. Alterar,
apagar ou inserir um evento no meio do histórico (inclusive direto no banco) quebra a cadeia dali em diante, e
`verify_chain` aponta o primeiro evento adulterado. A chave vem de PSEUDONYM_KEY/SECRET_KEY: sem ela não dá para
recalcular a cadeia depois de editar. Limite conhecido: apagar os eventos mais recentes (o rabo) não quebra elo nenhum;
para isso, guarde cópias periódicas do hash final mostrado em /admin/audit.
"""
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import timezone

from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog
from app.models.mixins import utcnow

_LOCK_KEY = 7461001   # advisory lock do PostgreSQL: serializa quem escreve na cadeia (evita bifurcação)


def log(db: Session, user_id: int | None, action: str, entity: str, entity_id: int | None, details: dict | None = None):
    db.add(AuditLog(user_id=user_id, action=action, entity=entity, entity_id=entity_id, details=details))


def _key() -> bytes:
    from app import security

    s = get_settings()
    return (s.pseudonym_key or s.secret_key or security._runtime_secret or "dev").encode() + b":audit-chain"


def _canon(row: AuditLog) -> str:
    at = row.at
    if at.tzinfo is not None:
        at = at.astimezone(timezone.utc).replace(tzinfo=None)   # SQLite devolve sem fuso; Postgres com fuso
    return json.dumps([at.isoformat(timespec="microseconds"), row.user_id, row.action, row.entity, row.entity_id,
                       row.details], sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, row: AuditLog) -> str:
    return hmac.new(_key(), (prev_hash + "|" + _canon(row)).encode(), hashlib.sha256).hexdigest()


@event.listens_for(Session, "before_flush")
def _chain_new_events(session: Session, flush_context, instances) -> None:
    new = [o for o in session.new if isinstance(o, AuditLog)]
    if not new:
        return
    new.sort(key=lambda o: inspect(o).insert_order)
    with session.no_autoflush:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
        prev = session.scalar(select(AuditLog.row_hash).where(AuditLog.row_hash.is_not(None))
                              .order_by(AuditLog.id.desc()).limit(1)) or ""
    for row in new:
        if row.at is None:
            row.at = utcnow()
        row.prev_hash = prev
        row.row_hash = prev = compute_hash(prev, row)


@dataclass
class ChainReport:
    ok: bool
    protected: int = 0          # eventos dentro da cadeia
    legacy: int = 0             # eventos anteriores à proteção (não verificáveis)
    broken_id: int | None = None
    reason: str = ""
    head: str = ""              # hash do último evento (guarde cópias para detectar truncamento)


def verify_chain(db: Session, batch: int = 2000) -> ChainReport:
    report = ChainReport(ok=True)
    prev, last_id, started = "", 0, False
    while True:
        rows = db.execute(select(AuditLog.id, AuditLog.at, AuditLog.user_id, AuditLog.action, AuditLog.entity,
                                 AuditLog.entity_id, AuditLog.details, AuditLog.prev_hash, AuditLog.row_hash)
                          .where(AuditLog.id > last_id).order_by(AuditLog.id).limit(batch)).all()   # colunas: não toca a sessão
        if not rows:
            break
        for r in rows:
            last_id = r.id
            if r.row_hash is None:
                if started:
                    return ChainReport(False, report.protected, report.legacy, r.id,
                                       "evento sem selo no meio da cadeia (inserido ou editado fora do sistema)")
                report.legacy += 1
                continue
            started = True
            if (r.prev_hash or "") != prev:
                return ChainReport(False, report.protected, report.legacy, r.id,
                                   "encadeamento quebrado (evento removido ou inserido antes deste)")
            if not hmac.compare_digest(compute_hash(prev, r), r.row_hash):
                return ChainReport(False, report.protected, report.legacy, r.id, "conteúdo alterado depois de gravado")
            prev = r.row_hash
            report.protected += 1
    report.head = prev
    return report
