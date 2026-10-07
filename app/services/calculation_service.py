from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Variation:
    pct: Decimal | None  # arredondado a 2 casas; None quando não há base de comparação
    direction: str | None  # up | down | flat | None

    @property
    def arrow(self) -> str:
        return {"up": "↑", "down": "↓", "flat": "→"}.get(self.direction or "", "")

    @property
    def text(self) -> str:
        """'↑ 4,96%' / '↓ 8,21%' / '→ 0,00%' / '—' (nunca depende só de cor)."""
        if self.pct is None:
            return "—"
        s = f"{abs(self.pct):.2f}".replace(".", ",")
        return f"{self.arrow} {s}%"


def variation(previous, current) -> Variation:
    """Variação percentual de `previous` para `current`."""
    if previous is None or current is None:
        return Variation(None, None)
    prev, cur = Decimal(previous), Decimal(current)
    if prev == 0:
        return Variation(None, None)
    pct = ((cur - prev) / abs(prev) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    direction = "flat" if pct == 0 else ("up" if pct > 0 else "down")
    return Variation(pct, direction)


def add_months(d: date, n: int) -> date:
    idx = d.year * 12 + (d.month - 1) + n
    return date(idx // 12, idx % 12 + 1, 1)


def month_range(start: date, end: date) -> list[date]:
    """Todos os meses (dia 1) de start a end, inclusive."""
    start, end = start.replace(day=1), end.replace(day=1)
    out, cur = [], start
    while cur <= end:
        out.append(cur)
        cur = add_months(cur, 1)
    return out
