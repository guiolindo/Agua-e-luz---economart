"""Formatação pt-BR usada nos templates."""
from datetime import date
from decimal import Decimal

from app.utils.parsing import MONTHS_PT


def _br(number: Decimal | float | int, places: int) -> str:
    s = f"{number:,.{places}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def brl(value, places: int = 2) -> str:
    if value is None:
        return "—"
    return "R$ " + _br(Decimal(value), places)


def num(value, places: int = 0) -> str:
    if value is None:
        return "—"
    return _br(Decimal(value), places)


def pct(value, signed: bool = False) -> str:
    if value is None:
        return "—"
    v = Decimal(value)
    s = _br(abs(v), 2) + "%"
    if signed:
        return ("+" if v > 0 else "−" if v < 0 else "") + s
    return s


def month_label(value: date | None) -> str:
    """date(2026, 9, 1) -> 'SET/2026'."""
    if value is None:
        return "—"
    return f"{MONTHS_PT[value.month - 1]}/{value.year}"


def month_short(value: date) -> str:
    """'SET/26' (rótulo de gráfico)."""
    return f"{MONTHS_PT[value.month - 1]}/{str(value.year)[2:]}"


def date_br(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def variation_arrow(direction: str | None) -> str:
    return {"up": "↑", "down": "↓", "flat": "→"}.get(direction or "", "")
