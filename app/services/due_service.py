"""Vencimentos: lembretes de "vence hoje" por ponto de energia (unidade consumidora).

Cada ponto tem um dia de vencimento mensal (due_day). A ocorrência do mês cai no último dia quando o mês é mais curto
(dia 31 em fevereiro -> 28/29). Uma ocorrência fica pendente até alguém marcar como tratada (due_ack).
"""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import ConsumerUnit, EnergyBill, Store

TZ = ZoneInfo("America/Sao_Paulo")   # "hoje" é o dia do usuário no Brasil, não o do servidor (UTC)
OVERDUE_DAYS = 15                    # vencimentos não tratados continuam aparecendo por até 15 dias
SOON_DAYS = 3


def local_today() -> date:
    return datetime.now(TZ).date()


def occurrence(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, monthrange(year, month)[1]))


def latest_occurrence(due_day: int, today: date) -> date:
    """Vencimento mais recente que já chegou (<= hoje)."""
    occ = occurrence(today.year, today.month, due_day)
    if occ <= today:
        return occ
    py, pm = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return occurrence(py, pm, due_day)


def next_occurrence(due_day: int, today: date) -> date:
    """Próximo vencimento depois de hoje."""
    occ = occurrence(today.year, today.month, due_day)
    if occ > today:
        return occ
    ny, nm = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return occurrence(ny, nm, due_day)


@dataclass
class DueItem:
    unit: ConsumerUnit
    store: Store
    due: date
    status: str                 # today | overdue | soon
    days: int                   # dias de atraso (overdue) ou até o vencimento (soon)
    bill: EnergyBill | None     # conta lançada com este vencimento, se existir

    def as_dict(self) -> dict:
        b = self.bill
        return {
            "unit_id": self.unit.id, "store_id": self.store.id, "store": self.store.code, "number": self.unit.number,
            "description": self.unit.description or "", "supplier": self.unit.record_type.name if self.unit.record_type else "",
            "due": self.due.isoformat(), "status": self.status, "days": self.days,
            "value": float(b.total_value) if b else None, "bill_id": b.id if b else None,
            "label": {"today": "Vence hoje", "overdue": f"Venceu há {self.days} dia{'s' if self.days != 1 else ''}",
                      "soon": "Vence amanhã" if self.days == 1 else f"Vence em {self.days} dias"}[self.status],
        }


def due_items(db: Session, today: date | None = None) -> list[DueItem]:
    today = today or local_today()
    units = db.scalars(
        select(ConsumerUnit).options(joinedload(ConsumerUnit.store), joinedload(ConsumerUnit.record_type))
        .join(Store, Store.id == ConsumerUnit.store_id)
        .where(ConsumerUnit.active.is_(True), Store.active.is_(True), ConsumerUnit.due_day.is_not(None))
        .order_by(Store.code, ConsumerUnit.number)).all()
    items: list[DueItem] = []
    for u in units:
        past = latest_occurrence(u.due_day, today)
        handled = u.due_ack is not None and u.due_ack >= past
        age = (today - past).days
        if not handled and age <= OVERDUE_DAYS:
            items.append(DueItem(u, u.store, past, "today" if age == 0 else "overdue", age, _bill_for(db, u.id, past)))
            continue
        nxt = next_occurrence(u.due_day, today)
        if (nxt - today).days <= SOON_DAYS:
            items.append(DueItem(u, u.store, nxt, "soon", (nxt - today).days, _bill_for(db, u.id, nxt)))
    order = {"today": 0, "overdue": 1, "soon": 2}
    items.sort(key=lambda i: (order[i.status], i.due, i.store.code))
    return items


def _bill_for(db: Session, unit_id: int, due: date) -> EnergyBill | None:
    return db.scalar(select(EnergyBill).where(EnergyBill.unit_id == unit_id, EnergyBill.due_date == due).limit(1))


def acknowledge(db: Session, unit: ConsumerUnit, today: date | None = None) -> date | None:
    """Marca o vencimento mais recente como tratado (pago/visto). Devolve a data tratada."""
    if unit.due_day is None:
        return None
    occ = latest_occurrence(unit.due_day, today or local_today())
    unit.due_ack = occ
    return occ


def upcoming(db: Session, days: int = 30, today: date | None = None) -> list[dict]:
    """Próximos vencimentos (para a lista do sino e a visão do mês)."""
    today = today or local_today()
    out = []
    for u in db.scalars(select(ConsumerUnit).options(joinedload(ConsumerUnit.store))
                        .where(ConsumerUnit.active.is_(True), ConsumerUnit.due_day.is_not(None))):
        d = next_occurrence(u.due_day, today)
        if (d - today).days <= days:
            out.append({"store": u.store.code, "number": u.number, "due": d, "in_days": (d - today).days})
    return sorted(out, key=lambda x: x["due"])


