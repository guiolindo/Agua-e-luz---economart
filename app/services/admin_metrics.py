"""Métricas do painel do administrador: ranking de quem lançou contas, atividade por dia, funil das importações e a
ficha de cada usuário (contas por mês, lojas, horário de uso, acessos e linha do tempo).

Tudo é contado no horário de Brasília: "hoje", "o mês" e "a hora" são os de quem usa o sistema, não os do servidor.
Conta lançada = conta de energia salva (pela IA ou à mão) + lançamento manual (LL Energia, gerador...), pela data em
que foi gravada no sistema (não o mês de referência da conta).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import AuditLog, ConsumerUnit, EnergyBill, Import, ManualRecord, User
from app.services.calculation_service import add_months
from app.utils import formatting as fmt

TZ = ZoneInfo("America/Sao_Paulo")
LOGIN_ACTIONS = ("login", "login_2fa")
SOURCES = (("ia", "Importadas pela IA"), ("mao", "Lançadas à mão"))
IMPORT_STAGES = (("confirmed", "Salvas"), ("ready", "Aguardando conferência"), ("processing", "Lendo"),
                 ("rejected", "Barradas (não eram conta)"), ("failed", "Com erro"), ("cancelled", "Descartadas"))


def local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(TZ)


def month_bounds(month: date) -> tuple[datetime, datetime]:
    """Início e fim (exclusivo) do mês no horário de Brasília, em UTC (para comparar com o banco)."""
    start = datetime(month.year, month.month, 1, tzinfo=TZ)
    end = datetime(add_months(month, 1).year, add_months(month, 1).month, 1, tzinfo=TZ)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def this_month() -> date:
    now = datetime.now(TZ)
    return date(now.year, now.month, 1)


@dataclass
class Entry:
    """Uma conta ou lançamento gravado no sistema."""
    at: datetime            # horário de Brasília
    by: int | None
    source: str             # "ia" | "mao"
    store_id: int | None
    store_label: str
    reference: date
    value: object
    unit: str | None
    href: str


def _entries(db: Session, since: datetime, until: datetime, user_id: int | None = None) -> list[Entry]:
    bills = select(EnergyBill).options(joinedload(EnergyBill.unit).joinedload(ConsumerUnit.store)).where(
        EnergyBill.created_at >= since, EnergyBill.created_at < until)
    recs = select(ManualRecord).options(joinedload(ManualRecord.store)).where(
        ManualRecord.created_at >= since, ManualRecord.created_at < until)
    if user_id is not None:
        bills, recs = bills.where(EnergyBill.created_by == user_id), recs.where(ManualRecord.created_by == user_id)
    out = []
    for b in db.scalars(bills).unique():
        st = b.unit.store if b.unit else None
        out.append(Entry(local(b.created_at), b.created_by, "ia" if b.source == "import" else "mao", st.id if st else None,
                         st.short_label if st else "—", b.reference, b.total_value, b.unit.number if b.unit else None,
                         f"/bills/{b.id}/print"))
    for r in db.scalars(recs).unique():
        out.append(Entry(local(r.created_at), r.created_by, "mao", r.store_id, r.store.short_label if r.store else "—",
                         r.reference, r.value, None, f"/stores/{r.store_id}"))
    out.sort(key=lambda e: e.at, reverse=True)
    return out


def _stacked(labels: list[str], counts: dict[str, list[int]]) -> dict:
    """Configuração de gráfico de barras empilhadas IA × à mão (o admin.js desenha)."""
    return {"labels": labels, "series": [{"key": k, "label": name, "data": counts[k]} for k, name in SOURCES]}


def ranking(db: Session, month: date) -> dict:
    """Quem lançou mais contas no mês, separando IA e à mão."""
    since, until = month_bounds(month)
    entries = _entries(db, since, until)
    users = {u.id: u for u in db.scalars(select(User))}
    per = defaultdict(lambda: Counter())
    for e in entries:
        per[e.by][e.source] += 1
    rows, unassigned = [], 0
    for uid, c in per.items():
        if uid is None or uid not in users:          # carga inicial / sem autor: fica fora do ranking (contado à parte)
            unassigned += c["ia"] + c["mao"]
            continue
        u = users.get(uid)
        rows.append({"user": u, "name": u.username if u else "sistema", "id": uid, "ia": c["ia"], "mao": c["mao"],
                     "total": c["ia"] + c["mao"]})
    rows.sort(key=lambda r: (-r["total"], r["name"]))
    total = sum(r["total"] for r in rows) + unassigned
    for r in rows:
        r["share"] = r["total"] / total * 100 if total else 0
    prev_since, prev_until = month_bounds(add_months(month, -1))
    prev_total = len(_entries(db, prev_since, prev_until))
    chart = _stacked([r["name"] for r in rows], {"ia": [r["ia"] for r in rows], "mao": [r["mao"] for r in rows]})
    chart["links"] = [f"/admin/usuarios/{r['id']}" if r["id"] else "" for r in rows]
    return {"rows": rows, "total": total, "prev_total": prev_total, "chart": chart, "unassigned": unassigned,
            "ia": sum(c["ia"] for c in per.values()), "mao": sum(c["mao"] for c in per.values())}


def daily(db: Session, month: date, user_id: int | None = None) -> dict:
    """Contas lançadas em cada dia do mês (IA × à mão)."""
    since, until = month_bounds(month)
    days = (add_months(month, 1) - month).days
    counts = {k: [0] * days for k, _ in SOURCES}
    for e in _entries(db, since, until, user_id):
        counts[e.source][e.at.day - 1] += 1
    return _stacked([f"{d:02d}" for d in range(1, days + 1)], counts)


def imports_funnel(db: Session, month: date, user_id: int | None = None) -> dict:
    since, until = month_bounds(month)
    stmt = select(Import.status).where(Import.created_at >= since, Import.created_at < until)
    if user_id is not None:
        stmt = stmt.where(Import.created_by == user_id)
    c = Counter(db.scalars(stmt))
    total = sum(c.values())
    stages = [{"key": k, "label": name, "n": c.get(k, 0), "pct": c.get(k, 0) / total * 100 if total else 0}
              for k, name in IMPORT_STAGES if c.get(k, 0) or k in ("confirmed", "rejected", "failed", "cancelled")]
    return {"total": total, "stages": stages, "saved_pct": c.get("confirmed", 0) / total * 100 if total else None}


def logins_by_day(db: Session, days: int = 30, user_id: int | None = None) -> dict:
    end = datetime.now(TZ).date()
    start = end - timedelta(days=days - 1)
    since = datetime(start.year, start.month, start.day, tzinfo=TZ).astimezone(timezone.utc)
    stmt = select(AuditLog).where(AuditLog.action.in_(LOGIN_ACTIONS), AuditLog.at >= since)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    per_day, people = Counter(), defaultdict(set)
    for a in db.scalars(stmt):
        d = local(a.at).date()
        per_day[d] += 1
        people[d].add(a.user_id)
    labels, data, uniq = [], [], []
    for i in range(days):
        d = start + timedelta(days=i)
        labels.append(d.strftime("%d/%m"))
        data.append(per_day.get(d, 0))
        uniq.append(len(people.get(d, ())))
    return {"labels": labels, "series": [{"key": "login", "label": "Acessos", "data": data}],
            "active_days": sum(1 for v in data if v), "unique": uniq}


# ------------------------------------------------------------------ ficha do usuário
def user_profile(db: Session, user: User, month: date) -> dict:
    now = datetime.now(TZ)
    first = date(now.year, now.month, 1)
    months = [add_months(first, -i) for i in range(11, -1, -1)]
    since12 = month_bounds(months[0])[0]
    all_entries = _entries(db, since12, month_bounds(first)[1], user.id)

    by_month = {k: [0] * 12 for k, _ in SOURCES}
    idx = {(m.year, m.month): i for i, m in enumerate(months)}
    stores = Counter()
    for e in all_entries:
        i = idx.get((e.at.year, e.at.month))
        if i is not None:
            by_month[e.source][i] += 1
        stores[e.store_label] += 1
    top_stores = stores.most_common(8)

    m_since, m_until = month_bounds(month)
    p_since, p_until = month_bounds(add_months(month, -1))
    month_entries = [e for e in _entries(db, m_since, m_until, user.id)]
    prev_n = len(_entries(db, p_since, p_until, user.id))

    actions = list(db.scalars(select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.id.desc()).limit(400)))
    hours = [0] * 24
    since30 = datetime.now(timezone.utc) - timedelta(days=30)
    for a in actions:
        at = a.at if a.at.tzinfo else a.at.replace(tzinfo=timezone.utc)
        if at >= since30:
            hours[local(at).hour] += 1
    busiest = max(range(24), key=lambda h: hours[h]) if any(hours) else None

    views = [a for a in actions if a.action == "view" and a.entity == "presentation"]
    exports = [a for a in actions if a.action == "export"]
    total_ever = (db.query(EnergyBill).filter(EnergyBill.created_by == user.id).count()
                  + db.query(ManualRecord).filter(ManualRecord.created_by == user.id).count())

    timeline = defaultdict(list)
    for a in actions[:120]:
        timeline[local(a.at).date()].append(a)

    return {
        "month_n": len(month_entries), "month_ia": sum(1 for e in month_entries if e.source == "ia"),
        "prev_n": prev_n, "total_ever": total_ever,
        "by_month": _stacked([fmt.month_short(m) for m in months], by_month),
        "stores": {"labels": [s for s, _ in top_stores], "series": [{"key": "lojas", "label": "Contas lançadas",
                                                                   "data": [n for _, n in top_stores]}]},
        "hours": {"labels": [f"{h}h" for h in range(24)], "series": [{"key": "h", "label": "Ações", "data": hours}]},
        "busiest": busiest,
        "logins": logins_by_day(db, 30, user.id),
        "funnel": imports_funnel(db, month, user.id),
        "recent_entries": _entries(db, since12, month_bounds(first)[1], user.id)[:20],
        "timeline": sorted(timeline.items(), reverse=True),
        "last_view": local(views[0].at) if views else None,
        "exports": len(exports), "last_export": exports[0] if exports else None,
    }
