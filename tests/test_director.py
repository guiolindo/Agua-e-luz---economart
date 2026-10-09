import json
import re
from datetime import date
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store
from app.services import executive_service
from tests.conftest import Client
from tests.test_security import _create_user, _login, _new_client


def _t(db, code):
    return db.query(RecordType).filter_by(code=code).one()


def _world(db):
    """3 lojas: A (MG, 2 contas CEMIG + LL), B (MG, CEMIG), C (BA, Coelba). Jan/Fev 2026 + período anterior (Nov/Dez 2025)."""
    cemig, coelba, ll = _t(db, "cemig"), _t(db, "coelba"), _t(db, "ll-energia")
    out = {}
    for code, region, rtype, uc in (("A", "MG", cemig, "11"), ("B", "MG", cemig, "22"), ("C", "BA", coelba, "33")):
        s = Store(code=code, name=f"Loja {code}", region=region)
        db.add(s)
        db.flush()
        u = ConsumerUnit(store_id=s.id, number=uc, number_normalized=uc, record_type_id=rtype.id)
        db.add(u)
        db.flush()
        out[code] = (s, u, rtype)
    db.commit()

    def bill(code, ym, value, kwh=None, dem=None, contracted=None, due=None):
        s, u, rt = out[code]
        db.add(EnergyBill(unit_id=u.id, record_type_id=rt.id, reference=date(2026, ym, 1) if ym > 0 else date(2025, 12 + ym, 1),
                          total_value=D(value), consumption_hfp=D(kwh) if kwh else None, demand_hfp=D(dem) if dem else None,
                          contracted_demand=D(contracted) if contracted else None, due_date=due))

    bill("A", 1, 1000, kwh=10000, dem=90, contracted=100)
    bill("A", 2, 1500, kwh=10000, dem=120, contracted=100)        # 120% -> acima da contratada
    bill("A", 0, 800)                                              # dez/2025 (período anterior)
    bill("A", -1, 800)                                             # nov/2025
    bill("A", -2, 800)                                             # out/2025 (A tem 3 meses de histórico = comparável)
    bill("B", 1, 2000, kwh=20000, dem=50, contracted=100)
    bill("B", 2, 1000, kwh=20000, dem=50, contracted=100)
    bill("B", 0, 3000)
    bill("C", 1, 500)
    bill("C", 2, 500)
    s, _, _ = out["A"]
    db.add(ManualRecord(store_id=s.id, record_type_id=ll.id, reference=date(2026, 1, 1), value=D(200)))
    db.commit()
    return out


def test_company_totals_variation_and_period_comparison(db):
    _world(db)
    d = executive_service.build(db, date(2026, 1, 1), date(2026, 2, 1))
    assert d["kpi"]["total"] == 1000 + 1500 + 2000 + 1000 + 500 + 500 + 200 == 6700
    assert d["month_totals"] == [3700.0, 3000.0]
    assert d["kpi"]["last_month"] == 3000.0 and d["kpi"]["last_vs_prev"]["text"] == "↓ 18,92%"          # 3700 -> 3000
    # vs. período anterior: média/mês, só lojas COM histórico (A: os 2 meses do período anterior). A: 800/mês -> 1350/mês = +68,75%.
    # B tem 1 de 2 meses de histórico (insuficiente) e C nenhum: não entram, para não inventar "alta de 1000%".
    assert d["kpi"]["comparable_stores"] == 1 and d["kpi"]["vs_prev"]["text"] == "↑ 68,75%"
    rows = {r["code"]: r for r in d["rows"]}
    assert rows["A"]["vs_prev_period"]["text"] == "↑ 68,75%" and rows["B"]["vs_prev_period"]["pct"] is None


def test_store_ranking_share_and_last_month_movers(db):
    _world(db)
    d = executive_service.build(db, date(2026, 1, 1), date(2026, 2, 1))
    rows = {r["code"]: r for r in d["rows"]}
    assert [r["code"] for r in d["rows"]] == ["B", "A", "C"]                                  # B 3000, A 2700, C 1000
    assert rows["B"]["total"] == 3000.0 and round(rows["B"]["share"], 2) == round(3000 / 6700 * 100, 2)
    assert rows["A"]["vs_last_month"]["text"] == "↑ 25,00%" and rows["B"]["vs_last_month"]["text"] == "↓ 50,00%"
    assert rows["C"]["vs_last_month"]["direction"] == "flat"
    assert d["kpi"]["rise"]["code"] == "A" and d["kpi"]["fall"]["code"] == "B" and d["kpi"]["top"]["code"] == "B"
    assert rows["A"]["mix"][str(_t(db, "cemig").id)] == 2500.0 and rows["A"]["mix"][str(_t(db, "ll-energia").id)] == 200.0


def test_cost_per_kwh_and_demand_usage(db):
    _world(db)
    d = executive_service.build(db, date(2026, 1, 1), date(2026, 2, 1))
    rows = {r["code"]: r for r in d["rows"]}
    assert rows["A"]["rs_kwh"] == pytest.approx(2500 / 20000) and rows["B"]["rs_kwh"] == pytest.approx(3000 / 40000)
    assert rows["C"]["rs_kwh"] is None                                                         # sem consumo lido
    assert d["kpi"]["rs_kwh"] == pytest.approx((2500 + 3000) / 60000)                          # média ponderada da empresa
    assert rows["A"]["demand_use"] == pytest.approx(105.0) and rows["A"]["demand_over"] == 1  # (90% + 120%) / 2
    assert rows["B"]["demand_use"] == pytest.approx(50.0) and rows["B"]["demand_over"] == 0


def test_filters_region_supplier_and_due_month(db):
    _world(db)
    mg = executive_service.build(db, date(2026, 1, 1), date(2026, 2, 1), region="MG")
    assert {r["code"] for r in mg["rows"]} == {"A", "B"} and mg["kpi"]["total"] == 5700.0
    only_ll = executive_service.build(db, date(2026, 1, 1), date(2026, 2, 1), type_ids=[_t(db, "ll-energia").id])
    assert only_ll["kpi"]["total"] == 200.0 and [r["code"] for r in only_ll["rows"]] == ["A"]
    assert executive_service.build(db, date(2026, 1, 1), date(2026, 2, 1))["regions"] == ["BA", "MG"]
    # por vencimento: a conta A/jan vence em fevereiro -> sai de jan e entra em fev
    a = db.query(EnergyBill).join(ConsumerUnit).filter(ConsumerUnit.number == "11", EnergyBill.reference == date(2026, 1, 1)).one()
    a.due_date = date(2026, 2, 9)
    db.commit()
    due = executive_service.build(db, date(2026, 1, 1), date(2026, 2, 1), by="due")
    assert due["month_totals"] == [2700.0, 4000.0]


def test_empty_database_does_not_break(db):
    d = executive_service.build(db)
    assert d["rows"] == [] and d["kpi"]["total"] == 0.0 and d["kpi"]["top"] is None
    assert json.dumps(executive_service.client_payload(d))


# ---------------------------------------------------------------- acesso por perfil
def _user(admin: Client, name: str, role: str) -> Client:
    pw = _create_user(admin, name, role)
    c = _new_client()
    _login(c, name, pw)
    new = "Senha-forte-" + name[:3] + "-2026X"
    c.post("/account/password", {"current_password": pw, "new_password": new, "confirm": new})
    c.refresh()   # a sessão é recriada na troca de senha: novo token CSRF
    return c


def test_only_director_and_admin_see_the_executive_panel(client, db):
    _world(db)
    director, operator, viewer = (_user(client, "diretor1", "director"), _user(client, "func1", "operator"),
                                  _user(client, "consul1", "viewer"))
    assert client.get("/diretoria").status_code == 200                       # admin vê
    assert director.get("/diretoria").status_code == 200
    assert operator.get("/diretoria").status_code == 403 and viewer.get("/diretoria").status_code == 403
    assert TestClient(app).get("/diretoria", follow_redirects=False).status_code == 303   # anônimo -> login
    assert "Painel da diretoria" in director.get("/stores").text and "Painel da diretoria" not in operator.get("/stores").text


def test_director_lands_on_panel_and_is_read_only(client, db):
    _world(db)
    pw = _create_user(client, "diretor2", "director")
    d = _new_client()
    r = _login(d, "diretor2", pw)
    assert r.headers["location"] == "/account/password"                        # 1º acesso: troca a senha provisória
    new = "Diretor-Forte-2026"
    d.post("/account/password", {"current_password": pw, "new_password": new, "confirm": new})
    assert d.get("/", follow_redirects=False).headers["location"] == "/diretoria"
    d2 = _new_client()
    assert _login(d2, "diretor2", new).headers["location"] == "/diretoria"    # login já cai no painel
    for url in ("/import", "/manual", "/types", "/admin/users", "/stores/new"):
        assert d.get(url).status_code == 403, url
    assert d.post("/manual", {"store_id": "1"}).status_code == 403
    assert d.get("/stores/1").status_code == 200 and "Importar conta" not in d.get("/stores/1").text   # consulta e imprime


def test_panel_page_renders_all_blocks_and_safe_payload(client, db):
    _world(db)
    html = client.get("/diretoria?start=2026-01&end=2026-02").text
    for cid in ("c-month", "c-rank", "c-var", "c-mix", "c-line", "c-kwh", "c-util", "c-pair"):
        assert f'id="{cid}"' in html, cid
    for text in ("Total no período", "Mapa de calor", "Comparativo entre lojas", "Comparar duas lojas", "Custo por kWh"):
        assert text in html
    payload = json.loads(re.search(r'id="dir-data">(.*?)</script>', html, re.S).group(1))
    assert payload["labels"] == ["JAN/26", "FEV/26"] and [r["code"] for r in payload["rows"]] == ["B", "A", "C"]
    assert not re.search(r"\son(click|change|submit)\s*=", html) and all("nonce=" in t for t in re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*type=)[^>]*>", html))


def test_admin_roles_are_labelled_and_store_region_is_editable(client, db):
    html = client.get("/admin/users").text
    assert "Funcionário" in html and "Diretoria" in html and "Administrador" in html
    r = client.post("/stores", {"code": "Z9", "region": "ba"})
    assert r.status_code == 303 and db.query(Store).filter_by(code="Z9").one().region == "BA"


def test_partial_month_is_flagged_and_never_produces_a_fake_drop(db):
    w = _world(db)
    s, u, rt = w["A"]
    db.add(EnergyBill(unit_id=u.id, record_type_id=rt.id, reference=date(2026, 3, 1), total_value=D(900)))   # só 1 de 3 lojas lançou
    db.commit()
    d = executive_service.build(db, date(2026, 1, 1), date(2026, 3, 1))
    assert d["partial"] == [False, False, True] and d["coverage"] == [3, 3, 1] and d["peak"] == 3
    assert d["partial_labels"] == ["MAR/2026 (1 de 3 lojas)"]
    assert d["kpi"]["last_month"] == 3000.0 and d["focus_label"] == "FEV/2026"          # indicadores usam o último mês COMPLETO
    assert d["month_vars"][2]["pct"] is None                                              # sem "queda de 70%" por mês incompleto
    assert executive_service.client_payload(d)["labels"][2] == "MAR/26*"
    # quando as outras lojas lançam, o mês deixa de ser parcial e passa a valer
    for code in ("B", "C"):
        _, u2, rt2 = w[code]
        db.add(EnergyBill(unit_id=u2.id, record_type_id=rt2.id, reference=date(2026, 3, 1), total_value=D(700)))
    db.commit()
    d2 = executive_service.build(db, date(2026, 1, 1), date(2026, 3, 1))
    assert d2["partial"] == [False, False, False] and d2["focus_label"] == "MAR/2026" and d2["month_vars"][2]["pct"] is not None


def test_director_summary_in_plain_language(client, db):
    _world(db)
    d = _user(client, "diretor7", "director")
    html = d.get("/diretoria").text
    assert "Destaques de" in html and "a empresa gastou" in html
    assert "A loja que mais pesa no período é" in html


def _store_with_bills(db, code, series):
    """series: {(ano, mês): valor} em contas CEMIG de uma unidade nova."""
    cemig = _t(db, "cemig")
    s = Store(code=code, name=f"Loja {code}", region="MG")
    db.add(s)
    db.flush()
    u = ConsumerUnit(store_id=s.id, number=code, number_normalized=code, record_type_id=cemig.id)
    db.add(u)
    db.flush()
    for (y, m), v in series.items():
        db.add(EnergyBill(unit_id=u.id, record_type_id=cemig.id, reference=date(y, m, 1), total_value=D(v)))
    db.commit()


def test_year_over_year_compares_same_month_only_stores_with_both(db):
    _store_with_bills(db, "Y1", {(2025, 8): 1000, (2026, 5): 900, (2026, 6): 950, (2026, 7): 980, (2026, 8): 1300})
    _store_with_bills(db, "NOVA", {(2026, 7): 500, (2026, 8): 500})              # sem ago/2025: não entra no comparativo
    d = executive_service.build(db, date(2026, 1, 1), date(2026, 8, 1))
    y = d["kpi"]["yoy"]
    assert y and y["label"] == "AGO/2025" and y["stores"] == 1 and y["cur"] == 1300 and y["prev"] == 1000
    assert round(y["var"]["pct"], 1) == 30.0
    assert any("AGO/2025" in i["text"] and "a mais" in i["text"] for i in executive_service.insights(d))


def test_store_far_from_its_own_pattern_is_flagged(db):
    _store_with_bills(db, "OSC", {(2026, 1): 1000, (2026, 2): 1000, (2026, 3): 1000, (2026, 4): 1000, (2026, 5): 1500})
    _store_with_bills(db, "OK", {(2026, 1): 800, (2026, 2): 800, (2026, 3): 800, (2026, 4): 800, (2026, 5): 810})
    d = executive_service.build(db, date(2026, 1, 1), date(2026, 5, 1))
    txt = " ".join(i["text"] for i in executive_service.insights(d))
    assert "Fora do próprio padrão" in txt and "OSC +50,00%" in txt and "OK +" not in txt


def test_director_csv_export_and_copy_button(client, db):
    _world(db)
    d = _user(client, "diretor8", "director")
    r = d.get("/diretoria/export.csv?start=2026-01&end=2026-02")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    body = r.content.decode("utf-8")
    assert body.startswith("﻿Loja;Nome;Região;Total no período (R$)") and "\r\nA;Loja A;MG;" in body
    assert "data-copy-insights" in d.get("/diretoria").text and "/diretoria/export.csv" in d.get("/diretoria").text
    viewer = _user(client, "consul8", "viewer")
    assert viewer.get("/diretoria/export.csv").status_code == 403


def test_director_print_has_report_header_with_user_and_period(client, db):
    _world(db)
    html = _user(client, "diretor9", "director").get("/diretoria?start=2026-01&end=2026-02").text
    assert 'class="print-head"' in html and "Impresso por diretor9" in html and "JAN/2026 a FEV/2026" in html
    assert "size: A4 landscape" in html


def test_entry_screens_open_with_the_brand_hero(client, db):
    _world(db)
    home = client.get("/").text
    assert 'class="hero no-print"' in home and "Painel" in home and ("Bom dia" in home or "Boa tarde" in home or "Boa noite" in home)
    assert 'href="/import"' in home and "Importar conta" in home
    d = _user(client, "diretor10", "director").get("/diretoria").text
    assert 'class="hero no-print"' in d and "Painel da diretoria" in d and "Baixar planilha" in d
    viewer = _user(client, "consul10", "viewer").get("/").text
    assert 'class="hero no-print"' in viewer and 'href="/import"' not in viewer.split("</section>", 1)[0]
