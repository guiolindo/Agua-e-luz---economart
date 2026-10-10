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
from app.utils.timezone import local_today


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


class _LegacyManual:
    """Lançamento manual antigo de um tipo que virou conta: expõe só o valor com a interface de EnergyBill."""

    def __init__(self, rec):
        self.total_value = rec.value
        self.reference = rec.reference

    def __getattr__(self, name):   # consumo, demanda, dias... não existem no lançamento manual
        return None


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


def month_of(reference: date, due: date | None, by: str) -> date:
    """Mês em que o registro entra nas tabelas: referência (competência) ou vencimento (como a planilha atual)."""
    return due.replace(day=1) if by == "due" and due else reference


def _fetch_range(start: date, end: date, by: str) -> tuple[date, date]:
    """Por vencimento, uma conta com referência fora do período pode vencer dentro dele: busca 1 mês a mais."""
    return (add_months(start, -1), add_months(end, 1)) if by == "due" else (start, end)


def default_range(db: Session, store_id: int | None, start: date | None, end: date | None) -> tuple[date, date]:
    if end is None:
        end = repo.latest_reference(db, store_id) or local_today().replace(day=1)
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
    categorical = ["#1b4f8a", "#f47920", "#4f9a94", "#8a6aa3", "#b08a3e", "#7a8f5a"]
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
        if not unit_id:   # tipo que já foi manual (CEMIG G&T): o histórico sem unidade aparece como "Sem unidade"
            for r in repo.manual_for_store(db, store.id, start, end, record_type.id):
                if r.unit_id is None:
                    rows[None][r.reference].append(_LegacyManual(r))
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
            "highlight": is_hl, "color": "#1b4f8a" if is_hl else color,
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
    colors = ["#1b4f8a", "#f47920", "#4f9a94", "#8a6aa3", "#b08a3e", "#7a8f5a"]
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


def store_summary(db: Session, store: Store, start: date | None = None, end: date | None = None,
                  by: str = "reference") -> dict:
    """Resumo mensal da loja: tipo x mês, com total e variação (equivale ao 'Resumo mensal' da planilha atual)."""
    start, end = default_range(db, store.id, start, end)
    months = month_range(start, end)
    idx = {m: i for i, m in enumerate(months)}
    types = {t.id: t for t in list_record_types(db, only_active=False)}
    per_type: dict[int, list] = defaultdict(lambda: [None] * len(months))
    qs, qe = _fetch_range(start, end, by)
    for b in repo.bills_for_units(db, [u.id for u in store.units], qs, qe):
        m = month_of(b.reference, b.due_date, by)
        if m in idx:
            c = per_type[b.record_type_id]
            c[idx[m]] = (c[idx[m]] or Decimal(0)) + b.total_value
    for r in repo.manual_for_store(db, store.id, qs, qe):
        m = month_of(r.reference, r.due_date, by)
        if m in idx:
            c = per_type[r.record_type_id]
            c[idx[m]] = (c[idx[m]] or Decimal(0)) + r.value
    rows = [{"type": types[tid], "values": vals, "total": sum((v for v in vals if v is not None), Decimal(0))}
            for tid, vals in sorted(per_type.items(), key=lambda kv: types[kv[0]].sort_order)]
    totals = [sum((r["values"][i] for r in rows if r["values"][i] is not None), Decimal(0)) if
              any(r["values"][i] is not None for r in rows) else None for i in range(len(months))]
    return {
        "by": by, "months": months, "rows": rows, "totals": totals,
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


def _sheet_kpis(months: list[date], totals: list, variations: list) -> list[dict]:
    """Indicadores resumidos do fornecedor na folha: total, média, maior e menor mês, última variação."""
    present = [(m, t) for m, t in zip(months, totals) if t]
    if not present:
        return []
    total = sum((t for _, t in present), Decimal(0))
    hi, lo = max(present, key=lambda p: p[1]), min(present, key=lambda p: p[1])
    last_var = next((v for v in reversed(variations) if v.pct is not None), None)
    return [
        {"label": "Total no período", "value": fmt.brl(total, 0), "sub": f"{len(present)} meses com dados"},
        {"label": "Média mensal", "value": fmt.brl(total / len(present), 0), "sub": ""},
        {"label": "Maior mês", "value": fmt.brl(hi[1], 0), "sub": fmt.month_label(hi[0])},
        {"label": "Menor mês", "value": fmt.brl(lo[1], 0), "sub": fmt.month_label(lo[0])},
        {"label": "Última variação", "value": last_var.text if last_var else "—", "sub": "vs. mês anterior", "dir": last_var.direction if last_var else None},
    ]


def report_data(db: Session, store: Store, start: date | None = None, end: date | None = None,
                by: str = "reference", type_id: int | None = None, all_types: bool = False) -> dict:
    """Folha de impressão: resumo de todos os fornecedores + UM fornecedor (gráfico, variação, tabela e dados da conta).
    `all_types=True` devolve um bloco por fornecedor (várias folhas)."""
    # "sheet" = como na planilha impressa da Economart: o RESUMO soma pelo mês de VENCIMENTO e o gráfico/tabela do imóvel
    # mostra o mês de REFERÊNCIA da conta. "due" e "reference" aplicam a mesma regra aos dois.
    by_sum = "due" if by in ("due", "sheet") else "reference"
    by = "due" if by == "due" else "reference"          # regra do gráfico/tabela do imóvel
    explicit_end = end is not None
    start, end = default_range(db, store.id, start, end)
    if by_sum == "due" and not explicit_end:
        end = add_months(end, 1)          # o vencimento da última conta cai no mês seguinte (colunas vazias são cortadas abaixo)
    months = month_range(start, end)
    idx = {m: i for i, m in enumerate(months)}
    types = {t.id: t for t in list_record_types(db, only_active=False)}
    units = {u.id: u for u in store.units}
    n = len(months)
    blocks: dict[int, dict] = {}

    def block(tid: int) -> dict:
        return blocks.setdefault(tid, {"type": types[tid], "rows": {}, "totals": [None] * n, "days": [None] * n,
                                       "cons": [None] * n, "dem": [None] * n,
                                       "days_conflict": False})

    qs, qe = _fetch_range(start, end, by)
    for b in repo.bills_for_units(db, list(units), qs, qe):
        m = month_of(b.reference, b.due_date, by)
        if m not in idx:
            continue
        blk = block(b.record_type_id)
        if blk.get("latest") is None or b.reference >= blk["latest"].reference:
            blk["latest"] = b
        i = idx[m]
        row = blk["rows"].setdefault(b.unit_id, [None] * n)
        row[i] = (row[i] or Decimal(0)) + b.total_value
        blk["totals"][i] = (blk["totals"][i] or Decimal(0)) + b.total_value
        if b.consumption_total is not None:
            blk["cons"][i] = (blk["cons"][i] or Decimal(0)) + b.consumption_total
        if b.demand_hfp is not None:
            blk["dem"][i] = max(blk["dem"][i] or Decimal(0), b.demand_hfp)
        if b.days is not None:
            blk["days_conflict"] |= blk["days"][i] not in (None, b.days)
            blk["days"][i] = b.days
    for r in repo.manual_for_store(db, store.id, qs, qe):
        m = month_of(r.reference, r.due_date, by)
        if m not in idx:
            continue
        blk = block(r.record_type_id)
        i = idx[m]
        key = r.unit_id
        row = blk["rows"].setdefault(key, [None] * n)
        row[i] = (row[i] or Decimal(0)) + r.value
        blk["totals"][i] = (blk["totals"][i] or Decimal(0)) + r.value

    ordered = sorted(blocks, key=lambda t: types[t].sort_order)
    available = [types[t] for t in ordered]
    selected = type_id if type_id in blocks else next((t for t in ordered if types[t].is_bill), ordered[0] if ordered else None)
    out = []
    for tid, blk in sorted(blocks.items(), key=lambda kv: types[kv[0]].sort_order):
        if not all_types and tid != selected:
            continue
        nz = [i for i, t in enumerate(blk["totals"]) if t is not None]
        lo, hi = (nz[0], nz[-1]) if nz else (0, n - 1)           # a folha do imóvel não mostra meses vazios nas pontas
        cut = slice(lo, hi + 1)
        bm, totals = months[cut], blk["totals"][cut]
        vars_ = [variation(totals[i - 1] if i else None, t) for i, t in enumerate(totals)]
        rows = [{"label": units[k].number if k in units else "Total lançado", "values": v[cut]}
                for k, v in sorted(blk["rows"].items(), key=lambda kv: (kv[0] is None, units[kv[0]].number if kv[0] in units else ""))]
        cons, dem, days = blk["cons"][cut], blk["dem"][cut], blk["days"][cut]
        out.append({
            "type": blk["type"], "rows": rows if len(rows) > 1 else [], "totals": totals, "variations": vars_,
            "latest": blk.get("latest"), "months": bm, "last_idx": len(bm) - 1,
            "rs_kwh": ([(t / c) if t is not None and c else None for t, c in zip(totals, cons)] if any(v for v in cons) else None),
            "cons": cons if any(v is not None for v in cons) else None,
            "dem": dem if any(v is not None for v in dem) else None,
            "kpis": _sheet_kpis(bm, totals, vars_),
            "days": None if blk["days_conflict"] or not any(d is not None for d in days) else days,
            "chart": {"labels": [fmt.month_short(m) for m in bm], "values": [float(t) if t is not None else None for t in totals],
                      "variation": [float(v.pct) if v.pct is not None else None for v in vars_]},
        })
    summ = store_summary(db, store, start, end, by_sum)
    nz = [i for i, t in enumerate(summ["totals"]) if t is not None]
    slo, shi = (nz[0], nz[-1]) if nz else (0, len(months) - 1)
    scut = slice(slo, shi + 1)
    summ = {**summ, "months": months[scut], "totals": summ["totals"][scut], "variations": summ["variations"][scut],
            "rows": [{**r, "values": r["values"][scut]} for r in summ["rows"]]}
    sum_months = summ["months"]
    grand = summ["grand_total"] or Decimal(0)
    for r in summ["rows"]:                                          # extras ao lado do Total (a planilha não tinha)
        n_with = sum(1 for v in r["values"] if v is not None)
        r["avg"] = (r["total"] / n_with) if n_with and r["total"] is not None else None
        r["pct"] = (r["total"] / grand * 100) if grand and r["total"] is not None else None
    n_tot = sum(1 for t in summ["totals"] if t is not None)
    summ["avg"] = (grand / n_tot) if n_tot else None
    last_idx = max((i for i, t in enumerate(summ["totals"]) if t), default=len(sum_months) - 1)   # último mês COM dados
    return {"months": months, "sum_months": sum_months, "start": start, "end": end, "blocks": out, "by": by, "by_sum": by_sum, "last_idx": last_idx, "type_id": selected, "available": available, "all_types": all_types,
            "summary": summ}


def bill_print_data(db: Session, bill, months_back: int = 11) -> dict:
    """Ficha de uma conta + séries dos últimos 12 meses da mesma unidade (mês da conta em destaque)."""
    end = bill.reference
    start = add_months(end, -months_back)
    months = month_range(start, end)
    idx = {m: i for i, m in enumerate(months)}
    n = len(months)
    series = {k: [None] * n for k in ("value", "hp", "hfp", "single", "dhp", "dhfp", "contracted")}
    for b in repo.bills_for_units(db, [bill.unit_id], start, end, bill.record_type_id):
        i = idx[b.reference]
        series["value"][i] = float(b.total_value)
        series["hp"][i] = float(b.consumption_hp) if b.consumption_hp is not None else None
        series["hfp"][i] = float(b.consumption_hfp) if b.consumption_hfp is not None else None
        series["single"][i] = float(b.consumption_kwh) if b.consumption_kwh is not None else None
        series["dhp"][i] = float(b.demand_hp) if b.demand_hp is not None else None
        series["dhfp"][i] = float(b.demand_hfp) if b.demand_hfp is not None else None
        series["contracted"][i] = float(b.contracted_demand) if b.contracted_demand is not None else None
    sel = idx[bill.reference]
    series["variation"] = [
        (lambda v: float(v.pct) if v.pct is not None else None)(
            variation(series["value"][i - 1] if i else None, series["value"][i])) for i in range(n)]
    prev = repo.bills_for_units(db, [bill.unit_id], None, add_months(end, -1), bill.record_type_id)
    prev_bill = prev[-1] if prev else None

    def kpi(label, ind_key):
        ind = next(i for i in BILL_INDICATORS if i.key == ind_key)
        cur = ind.getter(bill)
        return {"label": label, "text": ind.format(cur), "variation": variation(ind.getter(prev_bill) if prev_bill else None, cur)}

    return {
        "labels": [fmt.month_short(m) for m in months], "selected": sel, "series": series,
        "has_split": any(v is not None for v in series["hp"] + series["hfp"]),
        "has_single": any(v is not None for v in series["single"]),
        "has_demand": any(v is not None for v in series["dhp"] + series["dhfp"]),
        "kpis": [kpi("Valor da fatura", "total_value"), kpi("Consumo total", "consumption_total"),
                 kpi("Demanda HFP", "demand_hfp"), kpi("Dias", "days")],
        "prev_bill": prev_bill,
        "all_bills": repo.bills_for_units(db, [bill.unit_id], None, None, bill.record_type_id)[::-1],
    }
