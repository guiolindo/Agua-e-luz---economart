"""Monta os dados dos gráficos e tabelas de histórico (sem HTML: devolve estruturas serializáveis)."""
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import ConsumerUnit, RecordType, Store
from app.repositories import records as repo
from app.repositories.stores import list_record_types
from app.services.calculation_service import add_months, month_range, variation
from app.utils import formatting as fmt


@dataclass(frozen=True)
class Indicator:
    key: str
    label: str
    kind: str  # brl | kwh | kw | days | number
    getter: Callable
    additive: bool = False  # somar quando houver mais de um registro no mesmo mês

    def format(self, v) -> str:
        if v is None:
            return "—"
        if self.kind == "brl":
            return fmt.brl(v)
        suffix = {"kwh": " kWh", "kw": " kW"}.get(self.kind, "")
        return fmt.num(v, 0 if self.kind in ("days", "kwh", "kw") else 2) + suffix


BILL_INDICATORS = [
    Indicator("total_value", "Valor da fatura", "brl", lambda b: b.total_value, True),
    Indicator("consumption_total", "Consumo total", "kwh", lambda b: b.consumption_total, True),
    Indicator("consumption_hp", "Consumo HP (ponta)", "kwh", lambda b: b.consumption_hp, True),
    Indicator("consumption_hfp", "Consumo HFP (fora ponta)", "kwh", lambda b: b.consumption_hfp, True),
    Indicator("demand_hp", "Demanda HP", "kw", lambda b: b.demand_hp),
    Indicator("demand_hfp", "Demanda HFP", "kw", lambda b: b.demand_hfp),
    Indicator("days", "Dias", "days", lambda b: b.days),
]


def indicators_for_type(rt: RecordType) -> list[Indicator]:
    if rt.is_bill:
        return BILL_INDICATORS
    inds = [Indicator("value", "Valor", "brl", lambda r: r.value, True)]
    for f in rt.fields or []:
        key, unit = f["key"], f.get("unit", "")
        kind = "kwh" if unit == "kWh" else "kw" if unit == "kW" else "number"
        inds.append(Indicator(key, f["label"], kind, (lambda k: lambda r: _num(r.data.get(k)))(key), True))
    return inds


def _num(v) -> Decimal | None:
    try:
        return None if v in (None, "") else Decimal(str(v))
    except Exception:
        return None


def tooltip_lines(rt: RecordType, rec) -> list[str]:
    """Linhas extras exibidas ao passar o mouse sobre um mês."""
    lines = []
    for ind in indicators_for_type(rt):
        v = ind.getter(rec)
        if v is not None:
            lines.append(f"{ind.label}: {ind.format(v)}")
    return lines


def default_range(db: Session, store_id: int | None, start: date | None, end: date | None) -> tuple[date, date]:
    if end is None:
        end = repo.latest_reference(db, store_id) or date.today().replace(day=1)
    if start is None:
        start = add_months(end, -11)
        first = repo.earliest_reference(db, store_id) if store_id else None
        if first and first > start:  # não desperdiça o gráfico com meses anteriores ao primeiro dado
            start = min(first, end)
    if start > end:
        start, end = end, start
    return start, end


def _palette(n: int, highlight_present: bool) -> list[str]:
    neutral = ["#9aa5b4", "#b7c0cc", "#7f8b9b", "#cdd4dd", "#6b7787", "#aeb8c5"]
    categorical = ["#2f6f9f", "#7a8f5a", "#b08a3e", "#8a6aa3", "#4f9a94", "#a35d5d"]
    base = neutral if highlight_present else categorical
    return [base[i % len(base)] for i in range(n)]


def build_chart(db: Session, store: Store, *, record_type: RecordType | None, indicator_key: str | None,
                view: str = "units", start: date | None = None, end: date | None = None,
                highlight_unit_id: int | None = None, unit_id: int | None = None) -> dict:
    start, end = default_range(db, store.id, start, end)
    months = month_range(start, end)
    idx = {m: i for i, m in enumerate(months)}
    types = {t.id: t for t in list_record_types(db, only_active=False)}

    if view == "types":
        return _chart_by_type(db, store, types, months, idx, start, end)

    if record_type is None:
        return {"months": [], "labels": [], "series": [], "indicator": None, "view": view, "empty": True}
    inds = indicators_for_type(record_type)
    ind = next((i for i in inds if i.key == indicator_key), inds[0])

    unit_ids = [u.id for u in store.units]
    if unit_id:
        unit_ids = [unit_id]
    rows: dict[tuple, dict[date, list]] = defaultdict(lambda: defaultdict(list))  # (unit_id|None) -> mês -> registros
    if record_type.is_bill:
        for b in repo.bills_for_units(db, unit_ids, start, end, record_type.id):
            rows[b.unit_id][b.reference].append(b)
    else:
        for r in repo.manual_for_store(db, store.id, start, end, record_type.id):
            if unit_id and r.unit_id != unit_id:
                continue
            rows[r.unit_id][r.reference].append(r)

    unit_by_id = {u.id: u for u in store.units}
    ordered = sorted(rows, key=lambda k: (k is None, unit_by_id[k].number if k in unit_by_id else ""))
    colors = _palette(len(ordered), highlight_unit_id is not None)
    series = []
    for color, key in zip(colors, ordered):
        by_month = rows[key]
        data: list = [None] * len(months)
        lines: list = [None] * len(months)
        for m, recs in by_month.items():
            vals = [ind.getter(r) for r in recs if ind.getter(r) is not None]
            if vals:
                data[idx[m]] = float(sum(vals, Decimal(0)) if ind.additive else vals[-1])
            lines[idx[m]] = tooltip_lines(record_type, recs[-1])
        variations = []
        for i, v in enumerate(data):
            prev = data[i - 1] if i > 0 else None
            var = variation(prev, v)
            variations.append({"text": var.text, "direction": var.direction})
        is_hl = highlight_unit_id is not None and key == highlight_unit_id
        series.append({
            "id": key, "label": unit_by_id[key].number if key in unit_by_id else "Sem unidade",
            "sublabel": unit_by_id[key].description if key in unit_by_id else None,
            "highlight": is_hl, "color": "#0b5cab" if is_hl else color,
            "data": data, "variations": variations, "lines": lines,
        })
    return {
        "view": view, "empty": not series,
        "start": start.strftime("%Y-%m"), "end": end.strftime("%Y-%m"),
        "months": [m.strftime("%Y-%m") for m in months], "labels": [fmt.month_short(m) for m in months],
        "indicator": {"key": ind.key, "label": ind.label, "kind": ind.kind},
        "indicators": [{"key": i.key, "label": i.label} for i in inds],
        "type": {"id": record_type.id, "name": record_type.name},
        "series": series,
    }


def _chart_by_type(db, store, types, months, idx, start, end) -> dict:
    """Barras empilhadas: total mensal da loja por tipo de registro (valor R$)."""
    totals: dict[int, list] = defaultdict(lambda: [None] * len(months))
    for b in repo.bills_for_units(db, [u.id for u in store.units], start, end):
        cur = totals[b.record_type_id]
        cur[idx[b.reference]] = (cur[idx[b.reference]] or 0) + float(b.total_value)
    for r in repo.manual_for_store(db, store.id, start, end):
        cur = totals[r.record_type_id]
        cur[idx[r.reference]] = (cur[idx[r.reference]] or 0) + float(r.value)
    colors = ["#2f6f9f", "#7a8f5a", "#b08a3e", "#8a6aa3", "#4f9a94", "#a35d5d"]
    series = []
    for i, (tid, data) in enumerate(sorted(totals.items(), key=lambda kv: types[kv[0]].sort_order)):
        series.append({"id": tid, "label": types[tid].name, "highlight": False, "color": colors[i % len(colors)],
                       "data": data,
                       "variations": [{"text": variation(data[j - 1] if j else None, v).text,
                                       "direction": variation(data[j - 1] if j else None, v).direction}
                                      for j, v in enumerate(data)],
                       "lines": [None] * len(months)})
    return {"view": "types", "empty": not series, "start": start.strftime("%Y-%m"), "end": end.strftime("%Y-%m"),
            "months": [m.strftime("%Y-%m") for m in months],
            "labels": [fmt.month_short(m) for m in months], "stacked": True,
            "indicator": {"key": "value", "label": "Total por tipo", "kind": "brl"}, "series": series}


def store_summary(db: Session, store: Store, start: date | None = None, end: date | None = None) -> dict:
    """Resumo mensal da loja: tipo x mês, com total e variação (equivale ao 'Resumo mensal' da planilha atual)."""
    start, end = default_range(db, store.id, start, end)
    months = month_range(start, end)
    idx = {m: i for i, m in enumerate(months)}
    types = {t.id: t for t in list_record_types(db, only_active=False)}
    per_type: dict[int, list] = defaultdict(lambda: [None] * len(months))
    for b in repo.bills_for_units(db, [u.id for u in store.units], start, end):
        c = per_type[b.record_type_id]
        c[idx[b.reference]] = (c[idx[b.reference]] or Decimal(0)) + b.total_value
    for r in repo.manual_for_store(db, store.id, start, end):
        c = per_type[r.record_type_id]
        c[idx[r.reference]] = (c[idx[r.reference]] or Decimal(0)) + r.value
    rows = [{"type": types[tid], "values": vals, "total": sum((v for v in vals if v is not None), Decimal(0))}
            for tid, vals in sorted(per_type.items(), key=lambda kv: types[kv[0]].sort_order)]
    totals = [sum((r["values"][i] for r in rows if r["values"][i] is not None), Decimal(0)) if
              any(r["values"][i] is not None for r in rows) else None for i in range(len(months))]
    return {
        "months": months, "rows": rows, "totals": totals,
        "variations": [variation(totals[i - 1] if i else None, t) for i, t in enumerate(totals)],
        "grand_total": sum((t for t in totals if t is not None), Decimal(0)),
    }


def unit_overview(db: Session, unit: ConsumerUnit) -> dict:
    """Indicadores da última conta da unidade vs. mês anterior."""
    bills = repo.bills_for_units(db, [unit.id])
    if not bills:
        return {"bills": [], "last": None}
    last = bills[-1]
    prev = bills[-2] if len(bills) > 1 else None

    def kpi(label, ind: Indicator):
        cur = ind.getter(last)
        return {"label": label, "text": ind.format(cur),
                "variation": variation(ind.getter(prev) if prev else None, cur)}

    by_key = {i.key: i for i in BILL_INDICATORS}
    return {
        "bills": bills, "last": last,
        "kpis": [kpi("Valor da fatura", by_key["total_value"]), kpi("Consumo total", by_key["consumption_total"]),
                 kpi("Demanda fora ponta", by_key["demand_hfp"]), kpi("Dias", by_key["days"])],
        "history": [{"bill": b, "variation": variation(bills[i - 1].total_value if i else None, b.total_value)}
                    for i, b in enumerate(bills)][::-1],
    }
