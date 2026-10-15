"""Telas do Painel executivo além da visão geral: Gasto evitável, Contratos (demanda) e Ano.

Tudo vem só das contas (sem ERP). Onde o histórico ainda é curto, cada bloco diz quantos meses tem de base e, se não
houver o suficiente, a partir de quando fica disponível — nunca mostra 0% ou um número inventado.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store
from app.models.store import short_label
from app.services.calculation_service import add_months, month_range
from app.services.chart_service import _fetch_range, month_of
from app.utils import formatting as fmt

DEMAND_TOLERANCE = Decimal("1.05")   # REN ANEEL 1.000/2021: ultrapassagem acima de 5% da contratada
LOW_USE = Decimal("0.80")            # máxima medida abaixo de 80% da contratada em 12 meses: contrato talvez grande demais
MIN_CONTRACT_MONTHS = 6              # abaixo disso a situação do contrato é só "pouco histórico"
FULL_CONTRACT_MONTHS = 12            # recomendação firme só com um ano inteiro (sazonalidade)
MIN_YEAR_MONTHS = 12                 # projeção do ano e comparação com o ano anterior

# Itens da fatura que são gasto evitável. Cada distribuidora escreve de um jeito ("Demanda Reativa Exc.",
# "Cons.Real.Exc.NPonta", "UFER", "Juros de mora", "Multa por atraso", "Demanda Ultrapassagem"...): por palavras-chave.
CATEGORIES = (
    ("ultrapassagem", "Ultrapassagem de demanda", re.compile(r"ultrapass|dem\w*\.?\s*ultr")),
    ("reativo", "Energia reativa excedente", re.compile(r"reativ|\bufer\b|\bdmcr\b|real\.?\s*exc|exc\w*\.?\s*reat|fator de pot")),
    ("atraso", "Juros e multa por atraso", re.compile(r"juros|multa|\bmora\b|atualiza\w*\s*monet|acresc\w*\s*morat")),
)
CAT_LABEL = {k: label for k, label, _ in CATEGORIES}


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def classify(description: str | None) -> str | None:
    d = _plain(description or "")
    for key, _label, rx in CATEGORIES:
        if rx.search(d):
            return key
    return None


def _f(v) -> float | None:
    return None if v is None else float(v)


def _stores(db: Session, region: str | None) -> dict[int, Store]:
    stores = {s.id: s for s in db.scalars(select(Store).where(Store.active.is_(True)))}
    if region:
        stores = {k: s for k, s in stores.items() if (s.region or "").upper() == region.upper()}
    return stores


def _bills(db: Session, start: date, end: date, by: str, stores: dict, type_ids: list[int] | None):
    qs, qe = _fetch_range(start, end, by)
    stmt = (select(EnergyBill).options(joinedload(EnergyBill.unit))
            .join(ConsumerUnit, ConsumerUnit.id == EnergyBill.unit_id)
            .where(EnergyBill.reference >= qs, EnergyBill.reference <= qe))
    for b in db.scalars(stmt).unique():
        m = month_of(b.reference, b.due_date, by)
        if start <= m <= end and b.unit.store_id in stores and (not type_ids or b.record_type_id in type_ids):
            yield m, b


# ------------------------------------------------------------------ gasto evitável
def avoidable(db: Session, start: date, end: date, by: str = "reference", region: str | None = None,
              type_ids: list[int] | None = None) -> dict:
    stores = _stores(db, region)
    months = month_range(start, end)
    idx = {m: i for i, m in enumerate(months)}
    series = {k: [0.0] * len(months) for k, _, _ in CATEGORIES}
    per_store = defaultdict(lambda: defaultdict(Decimal))
    items = []
    with_items = bills_total = 0
    for m, b in _bills(db, start, end, by, stores, type_ids):
        bills_total += 1
        if not b.line_items:
            continue
        with_items += 1
        for it in b.line_items:
            if not isinstance(it, dict) or it.get("value") in (None, ""):
                continue
            key = classify(it.get("description"))
            try:
                value = Decimal(str(it["value"]))
            except Exception:  # noqa: BLE001 — valor ilegível no JSON da leitura: ignora o item
                continue
            if key is None or value <= 0:
                continue
            series[key][idx[m]] += float(value)
            per_store[b.unit.store_id][key] += value
            items.append({"bill_id": b.id, "store": stores[b.unit.store_id], "month": m, "unit": b.unit.number,
                          "description": it.get("description") or "", "key": key, "value": value})
    rows = []
    for sid, cats in per_store.items():
        st = stores[sid]
        total = sum(cats.values(), Decimal(0))
        rows.append({"id": sid, "label": short_label(st.code, st.name), "code": st.code, "region": st.region or "",
                     "total": total, **{k: cats.get(k, Decimal(0)) for k in CAT_LABEL}})
    rows.sort(key=lambda r: r["total"], reverse=True)
    totals = {k: sum((r[k] for r in rows), Decimal(0)) for k in CAT_LABEL}
    items.sort(key=lambda i: i["value"], reverse=True)
    return {"categories": [{"key": k, "label": lbl, "total": totals[k]} for k, lbl, _ in CATEGORIES],
            "total": sum(totals.values(), Decimal(0)), "rows": rows, "top_items": items[:15],
            "labels": [fmt.month_short(m) for m in months],
            "series": [{"key": k, "label": lbl, "data": series[k]} for k, lbl, _ in CATEGORIES],
            "bills": bills_total, "with_items": with_items}


# ------------------------------------------------------------------ contratos (demanda)
def contracts(db: Session, end: date, region: str | None = None) -> dict:
    """Por unidade com demanda contratada (média tensão), nos 12 meses até `end`."""
    stores = _stores(db, region)
    start = add_months(end, -(FULL_CONTRACT_MONTHS - 1))
    per_unit = defaultdict(list)
    for _m, b in _bills(db, start, end, "reference", stores, None):
        if b.contracted_demand and b.contracted_demand > 0:
            measured = max(b.demand_hp or Decimal(0), b.demand_hfp or Decimal(0))
            if measured > 0:
                per_unit[b.unit_id].append(b)
    rows = []
    for unit_id, bills in per_unit.items():
        bills.sort(key=lambda b: b.reference)
        unit = bills[-1].unit
        st = stores[unit.store_id]
        contracted = bills[-1].contracted_demand                       # contrato vigente = o da conta mais recente
        measured = [max(b.demand_hp or Decimal(0), b.demand_hfp or Decimal(0)) for b in bills]
        peak = max(measured)
        over = sum(1 for b, m in zip(bills, measured) if m > b.contracted_demand * DEMAND_TOLERANCE)
        n = len({b.reference for b in bills})
        use = peak / contracted * 100
        if n < MIN_CONTRACT_MONTHS:
            status, tone = f"Pouco histórico ({n} {'mês' if n == 1 else 'meses'})", "info"
        elif over:
            status, tone = "Avaliar aumento da demanda contratada", "bad"
        elif peak < contracted * LOW_USE:
            status, tone = "Avaliar redução da demanda contratada", "warn"
        else:
            status, tone = "Adequada", "ok"
        if n < FULL_CONTRACT_MONTHS and tone in ("bad", "warn"):
            status += " (indicativo: menos de 12 meses)"
        rows.append({"store_id": st.id, "label": short_label(st.code, st.name), "unit": unit.number, "unit_id": unit.id,
                     "modality": bills[-1].tariff_modality or "", "contracted": contracted, "peak": peak,
                     "avg": sum(measured, Decimal(0)) / len(measured), "use": use, "over": over, "months": n,
                     "status": status, "tone": tone,
                     "series": [{"m": fmt.month_short(b.reference), "measured": _f(m), "contracted": _f(b.contracted_demand)}
                                for b, m in zip(bills, measured)]})
    order = {"bad": 0, "warn": 1, "ok": 2, "info": 3}
    rows.sort(key=lambda r: (order[r["tone"]], -r["use"]))
    return {"rows": rows, "start": start, "end": end,
            "counts": {t: sum(1 for r in rows if r["tone"] == t) for t in order}}


# ------------------------------------------------------------------ ano e "por que mudou"
def _month_energy(db: Session, start: date, end: date, by: str, region: str | None, type_ids: list[int] | None):
    """Por mês: valor total (contas + lançamentos) e, só das contas de distribuidora com kWh, valor e kWh."""
    stores = _stores(db, region)
    gen = {t.id for t in db.scalars(select(RecordType).where(RecordType.code.in_(("cemig-geracao",))))}
    total = defaultdict(Decimal)
    energy = defaultdict(lambda: {"value": Decimal(0), "kwh": Decimal(0)})
    for m, b in _bills(db, start, end, by, stores, type_ids):
        total[m] += b.total_value
        kwh = b.consumption_total
        if b.record_type_id not in gen and kwh and kwh > 0:
            energy[m]["value"] += b.total_value
            energy[m]["kwh"] += kwh
    stmt = select(ManualRecord).where(ManualRecord.reference >= start, ManualRecord.reference <= end)
    for r in db.scalars(stmt):
        if r.store_id in stores and (not type_ids or r.record_type_id in type_ids):
            total[r.reference] += r.value
    return total, energy


def decompose(e0: dict, e1: dict) -> dict | None:
    """Variação das contas de distribuidora entre dois meses = efeito consumo + efeito preço (R$/kWh).
    consumo = (kWh1 − kWh0) × preço0 · preço = (preço1 − preço0) × kWh1 (soma exata da variação)."""
    if not (e0 and e1 and e0["kwh"] and e1["kwh"]):
        return None
    p0, p1 = e0["value"] / e0["kwh"], e1["value"] / e1["kwh"]
    vol = (e1["kwh"] - e0["kwh"]) * p0
    price = (p1 - p0) * e1["kwh"]
    return {"delta": e1["value"] - e0["value"], "volume": vol, "price": price,
            "kwh_pct": (e1["kwh"] - e0["kwh"]) / e0["kwh"] * 100, "price_pct": (p1 - p0) / p0 * 100,
            "kwh0": e0["kwh"], "kwh1": e1["kwh"], "p0": p0, "p1": p1}


def year_view(db: Session, focus: date, by: str = "reference", region: str | None = None,
              type_ids: list[int] | None = None) -> dict:
    year = focus.year
    jan = date(year, 1, 1)
    hist_start = add_months(focus, -35)
    total, energy = _month_energy(db, hist_start, date(year, 12, 1), by, region, type_ids)
    with_data = sorted(m for m, v in total.items() if v)
    first = with_data[0] if with_data else None
    history = len([m for m in with_data if m <= focus])
    ytd_months = month_range(jan, focus)
    ytd = sum((total.get(m, Decimal(0)) for m in ytd_months), Decimal(0))
    prev_months = [m.replace(year=year - 1) for m in ytd_months]
    prev_ok = all(total.get(m) for m in prev_months)
    ytd_prev = sum((total.get(m, Decimal(0)) for m in prev_months), Decimal(0)) if prev_ok else None
    ready = history >= MIN_YEAR_MONTHS and first is not None and first <= add_months(focus, -(MIN_YEAR_MONTHS - 1))
    available_from = add_months(first, MIN_YEAR_MONTHS - 1) if first else None
    projection = None
    if ready and focus.month < 12:
        rest = month_range(add_months(focus, 1), date(year, 12, 1))
        last_year_rest = [total.get(m.replace(year=year - 1)) for m in rest]
        if ytd_prev and all(last_year_rest):
            factor = ytd / ytd_prev                                  # ritmo deste ano sobre o mesmo período do ano passado
            projection = {"value": ytd + sum(last_year_rest, Decimal(0)) * factor, "method": "seasonal", "factor": factor}
        else:
            last12 = [total.get(add_months(focus, -i), Decimal(0)) for i in range(12)]
            avg = sum(last12, Decimal(0)) / 12
            projection = {"value": ytd + avg * len(rest), "method": "average", "avg": avg}
    elif ready:
        projection = {"value": ytd, "method": "closed"}
    months_year = month_range(jan, date(year, 12, 1))
    chart = {"labels": [fmt.month_short(m) for m in months_year],
             "cur": [_f(total.get(m)) if m <= focus and total.get(m) else None for m in months_year],
             "prev": [_f(total.get(m.replace(year=year - 1))) if total.get(m.replace(year=year - 1)) else None for m in months_year]}
    prev_m = add_months(focus, -1)
    return {
        "year": year, "focus": focus, "history": history, "ready": ready, "available_from": available_from,
        "ytd": ytd, "ytd_months": len(ytd_months), "ytd_prev": ytd_prev,
        "ytd_var": ((ytd - ytd_prev) / ytd_prev * 100) if ytd_prev else None,
        "projection": projection, "chart": chart, "has_prev_year": any(chart["prev"]),
        "mom": decompose(energy.get(prev_m), energy.get(focus)), "mom_label": (fmt.month_label(prev_m), fmt.month_label(focus)),
        "yoy": decompose(energy.get(focus.replace(year=year - 1)), energy.get(focus)),
        "yoy_label": (fmt.month_label(focus.replace(year=year - 1)), fmt.month_label(focus)),
    }


def decomposition_sentence(d: dict | None, before: str, after: str) -> dict | None:
    """Uma frase para os Destaques: quanto da variação veio do consumo e quanto do preço por kWh."""
    if not d or abs(d["delta"]) < 1:
        return None
    up = d["delta"] > 0
    parts = []
    for key, word, pct in (("volume", "consumo", d["kwh_pct"]), ("price", "custo por kWh", d["price_pct"])):
        v = d[key]
        if abs(v) >= 1:
            parts.append(f"{fmt.brl(abs(v), 0)} {'a mais' if v > 0 else 'a menos'} por {word} ({fmt.pct(pct, signed=True)})")
    if not parts:
        return None
    text = (f"Contas de distribuidora em {after}: {fmt.brl(abs(d['delta']), 0)} {'a mais' if up else 'a menos'} que em {before} — "
            + " e ".join(parts) + ".")
    return {"tone": "bad" if up else "good", "text": text}
