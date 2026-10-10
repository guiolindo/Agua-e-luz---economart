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
from app.utils.timezone import local_today

NO_OWN_KWH_TYPES = {"cemig-geracao"}   # compra de energia: os kWh já estão na conta da distribuição (não somar 2x)
PARTIAL_RATIO = 0.6   # mês com menos de 60% das lojas (vs. o melhor mês) é tratado como parcial
DEMAND_TOLERANCE = 1.05   # REN ANEEL 1.000/2021 (Grupo A): ultrapassagem só passa a contar acima de 5% da demanda contratada
MIN_PREV_MONTHS = 3  # histórico mínimo de uma loja no período anterior para compará-la
TYPE_COLORS = ["#1b4f8a", "#f47920", "#4f9a94", "#8a6aa3", "#b08a3e", "#7a8f5a", "#7f8b9b", "#b0605f"]


def _f(v) -> float | None:
    return None if v is None else float(v)


def _var(prev, cur) -> dict:
    v = variation(prev, cur)
    return {"pct": _f(v.pct), "direction": v.direction, "text": v.text}


def default_period(db: Session, start: date | None, end: date | None) -> tuple[date, date]:
    from app.repositories.records import latest_reference

    end = (end or latest_reference(db) or local_today()).replace(day=1)
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
    type_code = {t.id: t.code for t in types}

    qs, qe = _fetch_range(prev_start, end, by)
    bills = list(db.scalars(select(EnergyBill).options(joinedload(EnergyBill.unit))
                            .join(ConsumerUnit, ConsumerUnit.id == EnergyBill.unit_id)
                            .where(EnergyBill.reference >= qs, EnergyBill.reference <= qe)))
    manual = list(db.scalars(select(ManualRecord).where(ManualRecord.reference >= qs, ManualRecord.reference <= qe)))

    cur = defaultdict(lambda: defaultdict(Decimal))     # store -> mês -> valor (período atual)
    prev_total = defaultdict(Decimal)                    # store -> total do período anterior
    prev_months_with_data: dict[int, set] = defaultdict(set)
    prev_cell = defaultdict(lambda: defaultdict(Decimal))   # store -> mês (janela anterior) -> valor
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
            prev_cell[store_id][month] += value

    for b in bills:
        m = month_of(b.reference, b.due_date, by)
        add(b.unit.store_id, b.record_type_id, m, b.total_value)
        if m in idx and b.unit.store_id in store_ids and b.record_type_id in use_types:
            kwh = b.consumption_total
            if kwh and kwh > 0 and type_code.get(b.record_type_id) not in NO_OWN_KWH_TYPES:
                eff[b.unit.store_id]["value"] += b.total_value
                eff[b.unit.store_id]["kwh"] += kwh
            if b.contracted_demand and b.contracted_demand > 0:
                measured = max(b.demand_hp or Decimal(0), b.demand_hfp or Decimal(0))
                if measured > 0:
                    util[b.unit.store_id].append(measured / b.contracted_demand)
    for r in manual:
        add(r.store_id, r.record_type_id, month_of(r.reference, None, by), r.value)

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
    yoy = None                                   # mesmo mês do ano anterior, só com as lojas que têm dado nos dois
    if months and not partial[focus]:
        ym = add_months(months[focus], -12)
        pairs = []
        for st in stores:
            a = cur[st.id].get(months[focus])
            b = cur[st.id].get(ym) if ym in idx else prev_cell[st.id].get(ym)
            if a and b:
                pairs.append((a, b))
        if pairs:
            ca, cb = sum((a for a, _ in pairs), Decimal(0)), sum((b for _, b in pairs), Decimal(0))
            yoy = {"label": fmt.month_label(ym), "stores": len(pairs), "cur": _f(ca), "prev": _f(cb), "var": _var(cb, ca)}

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
            "last": _f(last), "before": _f(before), "vs_last_month": _var(before, last), "abs_last_month": _f(last - before) if last is not None and before is not None else None,
            "rs_kwh": _f(e["value"] / e["kwh"]) if e and e["kwh"] else None,
            "kwh": _f(e["kwh"]) if e and e["kwh"] else None,
            "demand_use": _f(sum(u, Decimal(0)) / len(u) * 100) if u else None,
            "demand_over": sum(1 for x in (u or []) if x > DEMAND_TOLERANCE),
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
    rise = max((r for r in movers if r["vs_last_month"]["pct"] > 0), key=lambda r: r["vs_last_month"]["pct"], default=None)
    fall = min((r for r in movers if r["vs_last_month"]["pct"] < 0), key=lambda r: r["vs_last_month"]["pct"], default=None)
    pend_month = months[focus] if months else end
    pending = dashboard_service.pending_items(db, pend_month, add_months(pend_month, -1)) if stores else []
    pending = [p for p in pending if p["store"].id in store_ids]

    regions = sorted({(s.region or "").upper() for s in db.scalars(select(Store).where(Store.active.is_(True))) if s.region})
    return {
        "start": start, "end": end, "by": by, "months": months, "labels": [fmt.month_short(m) for m in months],
        "focus_idx": focus, "focus_label": fmt.month_label(months[focus]) if months else "", "prev_label": fmt.month_label(months[focus_prev]) if focus_prev >= 0 else "",
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
            "yoy": yoy,
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


def insights(data: dict) -> list[dict]:
    """Resumo em linguagem simples para quem não quer ler gráficos: frases curtas, com o que merece atenção.
    Cada item: {"tone": "good"|"bad"|"info", "text": str}. Só afirma o que os números sustentam."""
    k, rows, out = data["kpi"], data["rows"], []
    if not rows:
        return out
    focus, prev = data["focus_label"], data["prev_label"]

    def names(codes):
        n = len(codes) - 6
        return ", ".join(codes[:6]) + (f" e outras {n}" if n > 1 else " e mais 1" if n == 1 else "")

    def reais(v):
        return fmt.brl(v, 0)

    lv = k["last_vs_prev"]
    if k["last_month"] is not None and focus:
        if lv and lv["pct"] is not None and prev:
            verb = "a mais" if lv["pct"] > 0 else "a menos"
            tone = "bad" if lv["pct"] > 5 else "good" if lv["pct"] < -5 else "info"
            out.append({"tone": tone, "text": f"Em {focus} a empresa gastou {reais(k['last_month'])}, {fmt.pct(abs(lv['pct']))} {verb} que em {prev}."})
        else:
            out.append({"tone": "info", "text": f"Em {focus} a empresa gastou {reais(k['last_month'])}."})
    y = k.get("yoy")
    if y and y["var"]["pct"] is not None:
        verb = "a mais" if y["var"]["pct"] > 0 else "a menos"
        tone = "bad" if y["var"]["pct"] > 5 else "good" if y["var"]["pct"] < -5 else "info"
        out.append({"tone": tone, "text": f"Contra {y['label']} (mesmo mês do ano anterior, {y['stores']} {'loja com dado' if y['stores'] == 1 else 'lojas com dado'} nos dois): {fmt.pct(abs(y['var']['pct']))} {verb}."})
    if k["top"]:
        out.append({"tone": "info", "text": f"Maior participação no gasto do período: {k['top']['code']}, com {fmt.pct(k['top']['share'])} do total."})
    for key, word, tone in (("rise", "alta", "bad"), ("fall", "queda", "good")):
        r = k.get(key)
        if r and r["vs_last_month"]["pct"] is not None and abs(r["vs_last_month"]["pct"]) >= 5:
            out.append({"tone": tone, "text": f"Maior {word} em {focus}: {r['code']} ({fmt.pct(r['vs_last_month']['pct'], signed=True)})."
                        + (" Vale conferir o motivo: consumo, demanda ou tarifa." if key == "rise" else "")})
    fi, part = data.get("focus_idx"), data.get("partial") or []
    odd = []
    for r in rows:
        dev = _own_deviation(r, fi, part)
        if dev is not None and abs(dev) >= 25:
            odd.append((abs(dev), r["code"], dev))
    if odd:
        odd.sort(reverse=True)
        out.append({"tone": "bad" if any(d > 0 for _, _, d in odd[:3]) else "info",
                    "text": f"Fora do próprio padrão em {focus} (contra a média dos meses anteriores da loja): "
                            + ", ".join(f"{c} {fmt.pct(d, signed=True)}" for _, c, d in odd[:3]) + "."})
    over = [r["code"] for r in rows if (r.get("demand_over") or 0) > 0]
    if over:
        out.append({"tone": "bad", "text": f"{len(over)} {'loja ultrapassou' if len(over) == 1 else 'lojas ultrapassaram'} a demanda contratada em algum mês do período (pode gerar cobrança por ultrapassagem): {names(over)}."})
    low = [r["code"] for r in rows if r.get("demand_use") is not None and r["demand_use"] < 60]
    if low:
        out.append({"tone": "info", "text": f"Usam menos de 60% da demanda contratada (pode haver contrato maior que o necessário): {names(low)}."})
    avg = k.get("rs_kwh")
    if avg:
        dear = [r["code"] for r in rows if r.get("rs_kwh") and r["rs_kwh"] > avg * 1.15]
        if dear:
            out.append({"tone": "bad", "text": f"Custo por kWh acima da média da empresa ({fmt.brl(avg, 3)}) em mais de 15%: {names(dear)}."})
    if k["pending"]:
        out.append({"tone": "info", "text": f"{'Falta' if k['pending'] == 1 else 'Faltam'} {k['pending']} {'conta ou lançamento' if k['pending'] == 1 else 'contas ou lançamentos'} de {focus} (veja a lista de pendências no fim da página)."})
    return out


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


def _own_deviation(row: dict, fi: int | None, partial: list) -> float | None:
    """Desvio (%) do mês em foco contra a média dos até 6 meses completos anteriores da própria loja (mín. 3 meses)."""
    if fi is None:
        return None
    vals = row["values"]
    cur_v = vals[fi] if fi < len(vals) else None
    hist = [v for i, v in enumerate(vals[:fi]) if v and not (i < len(partial) and partial[i])][-6:]
    if not cur_v or len(hist) < 3:
        return None
    return (cur_v / (sum(hist) / len(hist)) - 1) * 100


def store_profile(data: dict, store_id: int) -> dict | None:
    """Ficha executiva de UMA loja dentro da empresa: posição, custo por kWh contra a média, demanda e frases de destaque."""
    rows = data["rows"]
    row = next((r for r in rows if r["id"] == store_id), None)
    if row is None:
        return None
    order = [r["id"] for r in sorted(rows, key=lambda r: r["total"] or 0, reverse=True)]
    rank, n = order.index(store_id) + 1, len(rows)
    focus, prev = data["focus_label"], data["prev_label"]
    avg = data["kpi"].get("rs_kwh")
    kwh_diff = ((row["rs_kwh"] / avg - 1) * 100) if row.get("rs_kwh") and avg else None
    out = []
    lv = row["vs_last_month"]
    if row.get("last") is not None and focus:
        if lv and lv["pct"] is not None and prev:
            verb = "a mais" if lv["pct"] > 0 else "a menos"
            out.append({"tone": "bad" if lv["pct"] > 5 else "good" if lv["pct"] < -5 else "info",
                        "text": f"Em {focus} gastou {fmt.brl(row['last'], 0)}, {fmt.pct(abs(lv['pct']))} {verb} que em {prev}."})
        else:
            out.append({"tone": "info", "text": f"Em {focus} gastou {fmt.brl(row['last'], 0)}."})
    out.append({"tone": "info", "text": f"É a {rank}ª de {n} lojas em gasto no período, com {fmt.pct(row['share'])} do total da empresa."})
    dev = _own_deviation(row, data.get("focus_idx"), data.get("partial") or [])
    if dev is not None and abs(dev) >= 25:
        out.append({"tone": "bad" if dev > 0 else "info", "text": f"Fora do próprio padrão em {focus}: {fmt.pct(dev, signed=True)} contra a média dos meses anteriores da loja."})
    if kwh_diff is not None and abs(kwh_diff) >= 5:
        out.append({"tone": "bad" if kwh_diff > 0 else "good",
                    "text": f"Paga {fmt.brl(row['rs_kwh'], 3)}/kWh, {fmt.pct(abs(kwh_diff))} {'acima' if kwh_diff > 0 else 'abaixo'} da média da empresa ({fmt.brl(avg, 3)})."})
    if row.get("demand_use") is not None:
        txt = f"Usa {fmt.pct(row['demand_use'])} da demanda contratada"
        if row.get("demand_over"):
            out.append({"tone": "bad", "text": txt + f" e ultrapassou o contratado em {row['demand_over']} mês(es) (pode gerar cobrança de ultrapassagem)."})
        elif row["demand_use"] < 60:
            out.append({"tone": "info", "text": txt + ": o contrato pode estar maior que o necessário."})
    return {"rank": rank, "n": n, "row": row, "kwh_diff": kwh_diff, "avg_kwh": avg, "focus_label": focus, "prev_label": prev, "insights": out}
