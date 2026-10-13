"""Painel do administrador: quem está on-line, quem lançou e exportou por último, quem abriu a apresentação."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, EnergyBill, Import, ManualRecord, User
from app.models.mixins import utcnow

ONLINE_MINUTES = 5            # atividade nos últimos 5 min = on-line
FAILED_LOGINS = ("login_failed", "login_2fa_failed", "login_blocked", "account_locked")
ROLE_LABELS = {"admin": "Administrador", "operator": "Funcionário", "user": "Funcionário", "director": "Diretoria",
               "viewer": "Consulta"}


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)      # SQLite devolve sem fuso


def ago(dt: datetime | None, now: datetime | None = None) -> str:
    """"agora", "há 3 min", "há 2 h", "ontem", "há 5 dias"."""
    dt = _aware(dt)
    if dt is None:
        return "nunca"
    secs = ((now or utcnow()) - dt).total_seconds()
    if secs < 60:
        return "agora"
    if secs < 3600:
        return f"há {int(secs // 60)} min"
    if secs < 86400:
        return f"há {int(secs // 3600)} h"
    days = int(secs // 86400)
    return "ontem" if days == 1 else f"há {days} dias"


def is_online(user: User, now: datetime | None = None) -> bool:
    seen = _aware(user.last_seen_at)
    return bool(user.active and seen and (now or utcnow()) - seen <= timedelta(minutes=ONLINE_MINUTES))


def _last_entry(db: Session) -> dict | None:
    """Última conta ou lançamento salvo no sistema (pela data em que foi gravado)."""
    bill = db.scalar(select(EnergyBill).order_by(EnergyBill.created_at.desc(), EnergyBill.id.desc()).limit(1))
    rec = db.scalar(select(ManualRecord).order_by(ManualRecord.created_at.desc(), ManualRecord.id.desc()).limit(1))
    cands = []
    if bill is not None:
        cands.append({"at": _aware(bill.created_at), "by": bill.created_by, "store": bill.unit.store if bill.unit else None,
                      "reference": bill.reference, "value": bill.total_value, "what": "Conta" if bill.source == "import" else "Conta (manual)",
                      "href": f"/bills/{bill.id}/print", "unit": bill.unit.number if bill.unit else None})
    if rec is not None:
        cands.append({"at": _aware(rec.created_at), "by": rec.created_by, "store": rec.store, "reference": rec.reference,
                      "value": rec.value, "what": "Lançamento manual", "href": f"/stores/{rec.store_id}", "unit": None})
    return max(cands, key=lambda c: c["at"]) if cands else None


def build(db: Session) -> dict:
    now = utcnow()
    users = list(db.scalars(select(User).order_by(User.username)))
    names = {u.id: u.username for u in users}

    views = list(db.scalars(select(AuditLog).where(AuditLog.action == "view", AuditLog.entity == "presentation")
                            .order_by(AuditLog.id.desc()).limit(500)))
    last_view: dict[int, datetime] = {}
    for v in views:
        last_view.setdefault(v.user_id, _aware(v.at))

    exports = list(db.scalars(select(AuditLog).where(AuditLog.action == "export").order_by(AuditLog.id.desc()).limit(5)))
    day_ago, week_ago = now - timedelta(days=1), now - timedelta(days=7)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def count_since(model, since):
        return db.scalar(select(func.count()).select_from(model).where(model.created_at >= since)) or 0

    people = []
    for u in users:
        people.append({"user": u, "role": ROLE_LABELS.get(u.role, u.role), "online": is_online(u, now),
                       "last_login": _aware(u.last_login), "last_seen": _aware(u.last_seen_at),
                       "seen_presentation": last_view.get(u.id)})
    people.sort(key=lambda p: (not p["online"], -(p["last_seen"] or p["last_login"] or datetime.min.replace(tzinfo=timezone.utc)).timestamp()))

    return {
        "now": now,
        "online": [p for p in people if p["online"]],
        "people": people,
        "names": names,
        "last_entry": _last_entry(db),
        "exports": exports,
        "presentation_views": views[:6],
        "presentation_seen": len(last_view),
        "presentation_missing": [u for u in users if u.active and u.id not in last_view],
        "entries_today": count_since(EnergyBill, today_start) + count_since(ManualRecord, today_start),
        "entries_week": count_since(EnergyBill, week_ago) + count_since(ManualRecord, week_ago),
        "imports_week": count_since(Import, week_ago),
        "failed_logins": db.scalar(select(func.count()).select_from(AuditLog)
                                   .where(AuditLog.action.in_(FAILED_LOGINS), AuditLog.at >= day_ago)) or 0,
        "active_users": sum(1 for u in users if u.active),
        "recent": list(db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(12))),
    }
