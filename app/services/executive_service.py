"""Painel da diretoria: comparação entre lojas, tendência da empresa, mix por fornecedor, eficiência e demanda.

Tudo é calculado a partir dos mesmos registros (contas e lançamentos manuais) em UMA leitura por tabela. O agrupamento
pode ser pelo mês de referência (competência) ou pelo de vencimento, como no resto do sistema.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store
from app.services import dashboard_service
from app.services.calculation_service import add_months, month_range, variation
from app.services.chart_service import _fetch_range, month_of
from app.utils import formatting as fmt

PARTIAL_RATIO = 0.6   # mês com menos de 60% das lojas (vs. o melhor mês) é tratado como parcial
MIN_PREV_MONTHS = 3  # histórico mínimo de uma loja no período anterior para compará-la
TYPE_COLORS = ["#2f6f9f", "#d08c3a", "#5b9a6b", "#8a6aa3", "#4f9a94", "#b0605f", "#7f8b9b", "#a89a3d"]


def _f(v) -> float | None:
    return None if v is None else float(v)


def _var(prev, cur) -> dict:
    v = variation(prev, cur)
    return {"pct": _f(v.pct), "direction": v.direction, "text": v.text}


def default_period(db: Session, start: date | None, end: date | None) -> tuple[date, date]:
    from app.repositories.records import latest_reference

    end = (end or latest_reference(db) or date.today()).replace(day=1)
    start = (start or add_months(end, -11)).replace(day=1)
    if start > end:
        start, end = end, start
    return start, end


def build(db: Session, start: date | None = None, end: date | None = None, by: str = "reference",
          type_ids: list[int] | None = None, region: str | None = None) -> dict:
    start, end = default_period(db, start, end)
    months = month_range(start, end)
    n = len(months)
    prev_start, prev_end = add_months(start, -n), add_months(start, -1)
    prev_months = month_range(prev_start, prev_end)
    idx = {m: i for i, m in enumerate(months)}
    pidx = {m: i for i, m in enumerate(prev_months)}

    stores = list(db.scalars(select(Store).where(Store.active.is_(True)).order_by(Store.code)))
    if region:
        stores = [s for s in stores if (s.region or "").upper() == region.upper()]
    store_ids = {s.id for s in stores}
    types = list(db.scalars(select(RecordType).order_by(RecordType.sort_order, RecordType.name)))
    color_of = {t.id: TYPE_COLORS[i % len(TYPE_COLORS)] for i, t in enumerate(types)}
    use_types = set(type_ids) if type_ids else {t.id for t in types}

    qs, qe = _fetch_range(prev_start, end, by)
    bills = list(db.scalars(select(EnergyBill).options(joinedload(EnergyBill.unit))
                            .join(ConsumerUnit, ConsumerUnit.id == EnergyBill.unit_id)
                            .where(EnergyBill.reference >= qs, EnergyBill.reference <= qe)))
    manual = list(db.scalars(select(ManualRecord).where(ManualRecord.reference >= qs, ManualRecord.reference <= qe)))

    cur = defaultdict(lambda: defaultdict(Decimal))     # store -> mês -> valor (período atual)
    prev_total = defaultdict(Decimal)                    # store -> total do período anterior
    prev_months_with_data: dict[int, set] = defaultdict(set)
    by_type_month = defaultdict(lambda: [Decimal(0)] * n)
    mix = defaultdict(lambda: defaultdict(Decimal))      # store -> tipo -> valor
    eff = defaultdict(lambda: {"value": Decimal(0), "kwh": Decimal(0)})
    util = defaultdict(list)                             # store -> [demanda / contratada]

    def add(store_id: int, type_id: int, month: date, value: Decimal) -> None:
        if store_id not in store_ids or type_id not in use_types:
            return
        if month in idx:
            cur[store_id][month] += value
            by_type_month[type_id][idx[month]] += value
            mix[store_id][type_id] += value
        elif month in pidx:
            prev_total[store_id] += value
            prev_months_with_data[store_id].add(month)

    for b in bills:
        m = month_of(b.reference, b.due_date, by)
        add(b.unit.store_id, b.record_type_id, m, b.total_value)
        if m in idx and b.unit.store_id in store_ids and b.record_type_id in use_types:
            kwh = b.consumption_total
            if kwh and kwh > 0:
                eff[b.unit.store_id]["value"] += b.total_value
                eff[b.unit.store_id]["kwh"] += kwh
            if b.contracted_demand and b.contracted_demand > 0:
                measured = max(b.demand_hp or Decimal(0), b.demand_hfp or Decimal(0))
                if measured > 0:
                    util[b.unit.store_id].append(measured / b.contracted_demand)
    for r in manual:
        add(r.store_id, r.record_type_id, month_of(r.reference, r.due_date, by), r.value)

    # --- empresa por mês
    month_totals = [sum((cur[s.id].get(m, Decimal(0)) for s in stores), Decimal(0)) for m in months]
    total = sum(month_totals, Decimal(0))
    coverage = [sum(1 for s in stores if cur[s.id].get(m)) for m in months]       # lojas com dado em cada mês
    peak = max(coverage, default=0)
    # Mês parcial: poucas lojas já lançaram (ex.: começo do mês). Comparar com ele engana: vira "queda" falsa.
    partial = [bool(peak) and 0 < c < PARTIAL_RATIO * peak for c in coverage]
    month_totals_opt = [t if t else None for t in month_totals]
    with_data = [i for i, t in enumerate(month_totals) if t]
    complete = [i for i in with_data if not partial[i]]
    focus = (complete or with_data or [n - 1])[-1]          # último mês COMPLETO
    focus_prev = focus - 1

    # --- lojas
    rows = []
    for s in stores:
        vals = [cur[s.id].get(m) for m in months]
        stotal = sum((v for v in vals if v), Decimal(0))
        if stotal == 0 and prev_total.get(s.id, 0) == 0:
            continue
        last = vals[focus] if focus < n else None
        before = vals[focus_prev] if focus_prev >= 0 else None
        e = eff.get(s.id)
        u = util.get(s.id)
        n_cur = sum(1 for v in vals if v)
        n_prev = len(prev_months_with_data.get(s.id, ()))
        comparable = n_cur > 0 and n_prev >= min(MIN_PREV_MONTHS, n) and prev_total.get(s.id)
        avg_cur = stotal / n_cur if n_cur else None
        avg_prev = prev_total[s.id] / n_prev if comparable else None
        rows.append({
            "id": s.id, "n_months": n_cur, "avg_prev": _f(avg_prev), "code": s.code, "name": s.name or "", "region": s.region or "", "values": [_f(v) for v in vals],
            "total": _f(stotal), "share": _f(stotal / total * 100) if total else 0.0,
            "avg": _f(stotal / max(1, len([v for v in vals if v]))),
            "prev_total": _f(prev_total.get(s.id)) if prev_total.get(s.id) else None,
            "vs_prev_period": _var(avg_prev, avg_cur) if comparable else _var(None, None),
            "last": _f(last), "before": _f(before), "vs_last_month": _var(before, last),
            "rs_kwh": _f(e["value"] / e["kwh"]) if e and e["kwh"] else None,
            "kwh": _f(e["kwh"]) if e and e["kwh"] else None,
            "demand_use": _f(sum(u, Decimal(0)) / len(u) * 100) if u else None,
            "demand_over": sum(1 for x in (u or []) if x > 1),
            "mix": {str(t): _f(v) for t, v in mix[s.id].items()},
        })
    rows.sort(key=lambda r: r["total"], reverse=True)
    for r in rows:  # intensidade 0..1 por loja (mostra a sazonalidade de cada uma)
        present = [v for v in r["values"] if v is not None]
        lo, hi = (min(present), max(present)) if present else (0, 0)
        r["heat"] = [None if v is None else (0.5 if hi == lo else (v - lo) / (hi - lo)) for v in r["values"]]

    eff_value = sum((e["value"] for e in eff.values()), Decimal(0))
    eff_kwh = sum((e["kwh"] for e in eff.values()), Decimal(0))
    like_cur = sum((Decimal(str(r["avg"])) for r in rows if r["avg_prev"] is not None), Decimal(0))
    like_prev = sum((Decimal(str(r["avg_prev"])) for r in rows if r["avg_prev"] is not None), Decimal(0))
    comparable_stores = sum(1 for r in rows if r["avg_prev"] is not None)
    movers = [r for r in rows if r["vs_last_month"]["pct"] is not None]
    rise = max(movers, key=lambda r: r["vs_last_month"]["pct"], default=None)
    fall = min(movers, key=lambda r: r["vs_last_month"]["pct"], default=None)
    pend_month = months[focus] if months else end
    pending = dashboard_service.pending_items(db, pend_month, add_months(pend_month, -1)) if stores else []
    pending = [p for p in pending if p["store"].id in store_ids]

    regions = sorted({(s.region or "").upper() for s in db.scalars(select(Store).where(Store.active.is_(True))) if s.region})
    return {
        "start": start, "end": end, "by": by, "months": months, "labels": [fmt.month_short(m) for m in months],
        "focus_label": fmt.month_label(months[focus]) if months else "", "prev_label": fmt.month_label(months[focus_prev]) if focus_prev >= 0 else "",
        "region": region, "regions": regions, "types": types, "type_ids": sorted(use_types), "colors": color_of,
        "kpi": {
            "total": _f(total),
            "vs_prev": _var(like_prev, like_cur) if comparable_stores else _var(None, None),
            "comparable_stores": comparable_stores,
            "avg_month": _f(total / max(1, len(with_data))), "stores": len(rows),
            "last_month": _f(month_totals[focus]) if months else None,
            "last_vs_prev": _var(month_totals[focus_prev] if focus_prev >= 0 and not partial[focus_prev] else None,
                                 month_totals[focus] if months else None),
            "top": rows[0] if rows else None, "rise": rise, "fall": fall, "pending": len(pending),
            "rs_kwh": _f(eff_value / eff_kwh) if eff_kwh else None,
        },
        "month_totals": [_f(t) for t in month_totals_opt],
        "partial": partial, "coverage": coverage, "peak": peak,
        "partial_labels": [f"{fmt.month_label(months[i])} ({coverage[i]} de {peak} lojas)" for i in range(n) if partial[i]],
        "month_vars": [_var(month_totals_opt[i - 1] if i and not partial[i - 1] else None,
                            month_totals_opt[i] if not partial[i] else None) for i in range(n)],
        "by_type": [{"id": t.id, "name": t.name, "color": color_of[t.id], "values": [_f(v) or None for v in by_type_month[t.id]]}
                    for t in types if t.id in by_type_month and any(by_type_month[t.id])],
        "rows": rows, "pending_items": pending[:12],
    }


def client_payload(data: dict) -> dict:
    """Subconjunto serializável (JSON) usado pelos gráficos do navegador."""
    return {
        "labels": [l + "*" if p else l for l, p in zip(data["labels"], data["partial"])], "partial": data["partial"],
        "focus": data["focus_label"], "prev": data["prev_label"],
        "month_totals": data["month_totals"], "month_vars": [v["pct"] for v in data["month_vars"]],
        "by_type": data["by_type"],
        "types": {str(t.id): {"name": t.name, "color": data["colors"][t.id]} for t in data["types"]},
        "rows": [{k: r[k] for k in ("id", "code", "name", "region", "values", "total", "share", "last", "before", "rs_kwh",
                                    "demand_use", "demand_over", "mix")} | {"var_last": r["vs_last_month"]["pct"]}
                 for r in data["rows"]],
        "avg_rs_kwh": data["kpi"]["rs_kwh"],
    }
