"""Central de alertas: lê o histórico de contas e aponta o que foge do padrão da PRÓPRIA unidade.

Cada regra compara a conta mais recente de cada unidade com as até 6 contas anteriores dela (mín. 3 para comparar).
Alerta é aviso para conferir, não veredito: pode ser erro de leitura da IA ou fato real (tarifa, ultrapassagem, estimativa).
Quem confere marca "Conferido" e o alerta some (tabela `alert_acks`, chave `tipo:id-da-conta`).
"""
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import AlertAck, ConsumerUnit, EnergyBill
from app.utils import formatting as fmt
from app.utils.timezone import local_today

ORDER = {"alta": 0, "media": 1, "baixa": 2}
LABEL = {"alta": "Alta", "media": "Média", "baixa": "Baixa"}
HIST_MAX, HIST_MIN = 6, 3
SPIKE_MEDIUM, SPIKE_HIGH, DROP = 30.0, 50.0, -40.0     # % contra a média da unidade
DEMAND_TOLERANCE = 105.0                                # % da demanda contratada: acima disso costuma haver cobrança de ultrapassagem
PRICE_RISE = 20.0                                       # % no R$/kWh contra a mediana da unidade
ITEMS_GAP = 0.03                                        # itens lidos somam >3% diferente do total
RECENT_MONTHS = 3                                       # só contas dos últimos meses geram alerta


@dataclass
class Alert:
    key: str
    severity: str
    kind: str
    title: str
    detail: str
    store_code: str
    unit_id: int
    unit_number: str
    bill_id: int
    reference: date

    @property
    def severity_label(self) -> str:
        return LABEL[self.severity]


def _add_months(d: date, n: int) -> date:
    m = d.year * 12 + d.month - 1 + n
    return date(m // 12, m % 12 + 1, 1)


def _rs(v) -> str:
    return fmt.brl(v, 0)


def _measured_demand(b: EnergyBill) -> Decimal | None:
    vals = [v for v in (b.demand_hp, b.demand_hfp) if v is not None]
    return max(vals) if vals else None


def _unit_alerts(unit: ConsumerUnit, bills: list[EnergyBill], cutoff: date) -> list[Alert]:
    out: list[Alert] = []
    latest, hist = bills[-1], bills[:-1][-HIST_MAX:]
    if latest.reference < cutoff:
        return out
    ref = fmt.month_label(latest.reference)

    def mk(kind, severity, title, detail):
        out.append(Alert(f"{kind}:{latest.id}", severity, kind, title, detail, unit.store.code, unit.id, unit.number,
                         latest.id, latest.reference))

    total = latest.total_value or Decimal(0)
    if len(hist) >= HIST_MIN and total > 0:
        avg = sum((h.total_value for h in hist), Decimal(0)) / len(hist)
        if avg > 0:
            dev = float((total / avg - 1) * 100)
            base = f"{_rs(total)} contra média de {_rs(avg)} nas últimas {len(hist)} contas da unidade."
            if dev >= SPIKE_MEDIUM:
                mk("valor", "alta" if dev >= SPIKE_HIGH else "media", f"Conta de {ref} está {dev:.0f}% acima da média da unidade", base)
            elif dev <= DROP:
                mk("valor", "media", f"Conta de {ref} está {abs(dev):.0f}% abaixo da média da unidade",
                   base + " Pode ser leitura estimada ou lançamento incompleto.")
        # custo por kWh
        kwh = latest.consumption_total
        prices = [h.total_value / h.consumption_total for h in hist if h.consumption_total and h.consumption_total > 0]
        if kwh and kwh > 0 and len(prices) >= HIST_MIN:
            now_p, med = total / kwh, statistics.median(prices)
            if med > 0 and float((now_p / med - 1) * 100) >= PRICE_RISE:
                mk("tarifa", "media", f"Custo por kWh de {ref} subiu {float((now_p / med - 1) * 100):.0f}%",
                   f"{fmt.brl(now_p, 3)}/kWh contra mediana de {fmt.brl(med, 3)}. Pode ser mudança de tarifa, multa ou cobrança extra.")
    # demanda acima do contratado
    measured = _measured_demand(latest)
    if latest.contracted_demand and latest.contracted_demand > 0 and measured and measured > latest.contracted_demand:
        pct = float(measured / latest.contracted_demand * 100)
        if pct > DEMAND_TOLERANCE:
            mk("demanda", "alta" if pct >= 110 else "media", f"Demanda de {ref} acima do contratado ({pct:.0f}%)",
               f"Medido {measured:.0f} kW contra {latest.contracted_demand:.0f} kW contratados, acima da tolerância de 5%: "
               "costuma haver cobrança de ultrapassagem. Confira o item na fatura.")
        else:
            mk("demanda", "baixa", f"Demanda de {ref} no limite do contratado ({pct:.0f}%)",
               f"Medido {measured:.0f} kW contra {latest.contracted_demand:.0f} kW contratados, dentro da tolerância de 5%: "
               "em geral sem cobrança de ultrapassagem. Vale acompanhar.")
    # itens lidos que não fecham com o total (leitura por IA)
    items = [Decimal(str(i.get("value"))) for i in (latest.line_items or []) if isinstance(i, dict) and i.get("value") is not None]
    if latest.source == "import" and len(items) >= 2 and total > 0:
        soma = sum(items, Decimal(0))
        if abs(soma - total) / total > Decimal(str(ITEMS_GAP)):
            mk("itens", "baixa", f"Itens lidos da conta de {ref} não fecham com o total",
               f"Os itens somam {_rs(soma)} e o total é {_rs(total)}. Confira se a leitura pegou todos os itens.")
    # período de leitura estranho
    if latest.days is not None and (latest.days < 20 or latest.days > 40):
        mk("periodo", "baixa", f"Período de leitura de {latest.days} dias em {ref}", "Costuma ser perto de 30 dias; confira as datas de leitura.")
    return out


def _duplicate_invoices(bills: list[EnergyBill], units: dict[int, ConsumerUnit]) -> list[Alert]:
    by_nf: dict[str, list[EnergyBill]] = defaultdict(list)
    for b in bills:
        nf = (b.invoice_number or "").strip().lstrip("0")
        if nf:
            by_nf[nf].append(b)
    out = []
    for nf, group in by_nf.items():
        if len(group) < 2:
            continue
        newest = max(group, key=lambda b: (b.reference, b.id))
        u = units[newest.unit_id]
        out.append(Alert(f"nota:{newest.id}", "alta", "nota", f"Nota fiscal {nf} aparece em {len(group)} contas",
                         "A mesma nota fiscal em mais de uma conta indica duplicidade ou erro de leitura.",
                         u.store.code, u.id, u.number, newest.id, newest.reference))
    return out


def compute(db: Session, today: date | None = None, include_acked: bool = False) -> list[Alert]:
    today = today or local_today()
    first = today.replace(day=1)
    since = _add_months(first, -(RECENT_MONTHS + HIST_MAX + 1))
    bills = list(db.scalars(select(EnergyBill).options(joinedload(EnergyBill.unit).joinedload(ConsumerUnit.store))
                            .where(EnergyBill.reference >= since).order_by(EnergyBill.reference, EnergyBill.id)))
    units, per_unit = {}, defaultdict(list)
    for b in bills:
        u = b.unit
        if not u.active or not u.store.active:
            continue
        units[u.id] = u
        per_unit[u.id].append(b)
    cutoff = _add_months(first, -RECENT_MONTHS)
    alerts: list[Alert] = []
    for uid, lst in per_unit.items():
        alerts += _unit_alerts(units[uid], lst, cutoff)
    alerts += [a for a in _duplicate_invoices([b for bl in per_unit.values() for b in bl], units) if a.reference >= cutoff]
    if not include_acked:
        acked = set(db.scalars(select(AlertAck.key)))
        alerts = [a for a in alerts if a.key not in acked]
    alerts.sort(key=lambda a: (ORDER[a.severity], -a.reference.toordinal(), a.store_code))
    return alerts


_cache: dict = {"at": 0.0, "value": None}


def counts(db: Session, ttl: int = 90) -> dict:
    """Contagem para o selo do menu; guarda por `ttl` segundos para não recalcular a cada página."""
    now = time.monotonic()
    if _cache["value"] is None or now - _cache["at"] > ttl:
        al = compute(db)
        _cache.update(at=now, value={"count": len(al), "high": sum(1 for a in al if a.severity == "alta")})
    return _cache["value"]


def reset_cache() -> None:
    _cache.update(at=0.0, value=None)
