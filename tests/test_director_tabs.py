"""Painel executivo em abas: Gasto evitável, Contratos e Ano (só com dados das contas)."""
from datetime import date
from decimal import Decimal as D

from app.models import ConsumerUnit, EnergyBill, RecordType
from app.services import director_extra as extra
from tests.test_app_flow import _make_store


def _bill(db, unit, rtype, ref, value, kwh=None, contracted=None, demand=None, items=None):
    b = EnergyBill(unit_id=unit.id, record_type_id=rtype.id, source="manual", reference=ref, total_value=D(value),
                   consumption_kwh=D(kwh) if kwh else None, contracted_demand=D(contracted) if contracted else None,
                   demand_hfp=D(demand) if demand else None, line_items=items)
    db.add(b)
    return b


def test_classify_line_items_from_different_distributors():
    assert extra.classify("Demanda Reativa Exc.") == "reativo"
    assert extra.classify("Cons.Real.Exc.NPonta") == "reativo"                     # COELBA abrevia "reativo excedente"
    assert extra.classify("UFER Fora Ponta") == "reativo"
    assert extra.classify("Demanda Ultrapassagem HFP") == "ultrapassagem"
    assert extra.classify("Multa por atraso") == "atraso" and extra.classify("Juros de Mora") == "atraso"
    assert extra.classify("Atualização Monetária") == "atraso"
    assert extra.classify("Uso Sistema Fio") is None and extra.classify("Consumo em kWh") is None
    assert extra.classify("Componente Encargo HFP") is None and extra.classify(None) is None


def test_avoidable_sums_positive_items_per_store(client, db):
    _make_store(client)
    unit = db.query(ConsumerUnit).one()
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    _bill(db, unit, cemig, date(2026, 8, 1), "1000", items=[{"description": "Multa por atraso", "value": 20},
                                                             {"description": "Demanda Reativa Exc.", "value": 0}])
    _bill(db, unit, cemig, date(2026, 9, 1), "1200", items=[{"description": "UFER", "value": 150.5},
                                                             {"description": "Consumo", "value": 900}])
    _bill(db, unit, cemig, date(2026, 7, 1), "900")                                 # sem itens: não entra, mas é contada
    db.commit()
    a = extra.avoidable(db, date(2026, 7, 1), date(2026, 9, 1))
    assert a["total"] == D("170.5") and a["bills"] == 3 and a["with_items"] == 2
    assert {c["key"]: c["total"] for c in a["categories"]} == {"ultrapassagem": 0, "reativo": D("150.5"), "atraso": 20}
    assert a["rows"][0]["code"] == "CD300" and a["top_items"][0]["description"] == "UFER"
    html = client.get("/diretoria?start=2026-07&end=2026-09&aba=evitavel").text
    assert 'data-aba="evitavel"' in html and "R$ 170" in html and "Gasto evitável" in html


def test_contracts_flags_overshoot_and_short_history(client, db):
    _make_store(client)
    unit = db.query(ConsumerUnit).one()
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    for m in range(1, 4):
        _bill(db, unit, cemig, date(2026, m, 1), "1000", contracted=100, demand=90)
    db.commit()
    c = extra.contracts(db, date(2026, 3, 1))
    assert c["rows"][0]["tone"] == "info" and "Pouco histórico (3 meses)" in c["rows"][0]["status"]
    for m in range(4, 10):
        _bill(db, unit, cemig, date(2026, m, 1), "1000", contracted=100, demand=112 if m == 6 else 95)
    db.commit()
    r = extra.contracts(db, date(2026, 9, 1))["rows"][0]
    assert r["tone"] == "bad" and r["over"] == 1 and r["peak"] == 112 and "indicativo" in r["status"]   # 9 meses < 12


def test_year_waits_for_twelve_months_and_explains_the_change(client, db):
    _make_store(client)
    unit = db.query(ConsumerUnit).one()
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    _bill(db, unit, cemig, date(2026, 8, 1), "1000", kwh=2000)                      # R$ 0,50/kWh
    _bill(db, unit, cemig, date(2026, 9, 1), "1320", kwh=2200)                      # R$ 0,60/kWh
    db.commit()
    y = extra.year_view(db, date(2026, 9, 1))
    assert not y["ready"] and y["projection"] is None and y["available_from"] == date(2027, 7, 1)
    assert y["ytd"] == 2320 and y["ytd_prev"] is None
    d = y["mom"]
    assert d["delta"] == 320 and d["volume"] == 100 and d["price"] == 220           # 200 kWh × 0,50 + 0,10 × 2200
    s = extra.decomposition_sentence(d, *y["mom_label"])
    assert "R$ 100 a mais por consumo" in s["text"] and "R$ 220 a mais por custo por kWh" in s["text"]
    html = client.get("/diretoria?start=2026-08&end=2026-09&aba=ano").text
    assert "Disponível a partir de JUL/2027" in html and "Por que o gasto mudou?" in html


def test_year_projection_appears_with_a_full_year(client, db):
    _make_store(client)
    unit = db.query(ConsumerUnit).one()
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    for i in range(12):
        m = date(2025 + (9 + i) // 12, (9 + i) % 12 + 1, 1)                          # out/2025 a set/2026
        _bill(db, unit, cemig, m, "1000")
    db.commit()
    y = extra.year_view(db, date(2026, 9, 1))
    assert y["ready"] and y["projection"]["method"] == "average" and y["projection"]["value"] == 9000 + 3 * 1000


def test_tabs_are_links_that_keep_the_filters(client, db):
    _make_store(client)
    html = client.get("/diretoria?start=2026-01&end=2026-09&region=MG").text
    for key in ("geral", "lojas", "evitavel", "ano"):
        assert f'data-aba-link="{key}"' in html
    assert 'data-aba-link="contratos"' not in html                                  # sem conta com demanda, sem a aba
    assert 'href="?start=2026-01&amp;end=2026-09&amp;region=MG&amp;aba=lojas"' in html
    assert 'data-aba="geral"' in html
    assert 'data-aba="geral"' in client.get("/diretoria?aba=invalida").text


def test_demand_screens_only_appear_when_some_bill_has_demand(client, db):
    from app.services import demand_flag

    _make_store(client)
    unit = db.query(ConsumerUnit).one()
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    _bill(db, unit, cemig, date(2026, 9, 1), "1000", kwh=2000)                      # loja de baixa tensão: sem demanda
    db.commit()
    html = client.get("/diretoria?start=2026-09&end=2026-09").text
    assert 'data-aba-link="contratos"' not in html and "c-util" not in html and "Demanda usada" not in html
    assert 'data-aba="geral"' in client.get("/diretoria?aba=contratos").text            # aba que não existe: volta à visão geral
    assert "Demanda contratada usada" not in client.get(f"/stores/{unit.store_id}").text
    assert "Demanda usada" not in client.get("/diretoria/export.csv?start=2026-09&end=2026-09").text
    _bill(db, unit, cemig, date(2026, 8, 1), "1000", kwh=2000, contracted=100, demand=90)
    db.commit()
    demand_flag.reset()
    html = client.get("/diretoria?start=2026-08&end=2026-09").text
    assert 'data-aba-link="contratos"' in html and "c-util" in html and "Demanda usada" in html
    assert "Demanda usada" in client.get("/diretoria/export.csv?start=2026-08&end=2026-09").text
