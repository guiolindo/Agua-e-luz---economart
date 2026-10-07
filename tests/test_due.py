from datetime import date, datetime, timedelta
from decimal import Decimal as D

from app.models import AuditLog, ConsumerUnit, EnergyBill, RecordType, Store
from app.services import due_service as ds
from tests.test_app_flow import _form_from_review, _make_store, _upload
from tests.test_director import _user


def _unit(db, due_day, code="L1", number="1", active=True):
    store = db.query(Store).filter_by(code=code).first() or Store(code=code)
    db.add(store)
    db.flush()
    u = ConsumerUnit(store_id=store.id, number=number, number_normalized=number, due_day=due_day, active=active,
                     record_type_id=db.query(RecordType).filter_by(code="cemig").one().id)
    db.add(u)
    db.commit()
    return u


# ---------------------------------------------------------------- datas
def test_occurrence_clamps_to_last_day_of_short_months():
    assert ds.occurrence(2026, 2, 31) == date(2026, 2, 28) and ds.occurrence(2028, 2, 31) == date(2028, 2, 29)
    assert ds.occurrence(2026, 4, 31) == date(2026, 4, 30) and ds.occurrence(2026, 1, 31) == date(2026, 1, 31)


def test_latest_and_next_occurrence_cross_month_and_year():
    assert ds.latest_occurrence(9, date(2026, 10, 9)) == date(2026, 10, 9)                  # hoje
    assert ds.latest_occurrence(9, date(2026, 10, 8)) == date(2026, 9, 9)                   # ainda não chegou: o de setembro
    assert ds.latest_occurrence(20, date(2026, 1, 5)) == date(2025, 12, 20)                 # virada de ano
    assert ds.next_occurrence(9, date(2026, 10, 9)) == date(2026, 11, 9)
    assert ds.next_occurrence(15, date(2026, 12, 20)) == date(2027, 1, 15)
    assert ds.latest_occurrence(31, date(2026, 3, 1)) == date(2026, 2, 28)                  # dia 31 em fevereiro


def test_today_is_the_brazilian_day_not_the_server_utc_day():
    assert ds.local_today() == datetime.now(ds.TZ).date()
    assert ds.TZ.key == "America/Sao_Paulo"


# ---------------------------------------------------------------- itens de vencimento
def test_due_today_overdue_soon_and_expiry_window(db):
    today = date(2026, 10, 9)
    hoje, ontem, antigo, amanha, longe = (_unit(db, 9, number="1"), _unit(db, 8, number="2"), _unit(db, 20, number="3"),
                                          _unit(db, 10, number="4"), _unit(db, 22, number="5"))
    got = {i.unit.number: i for i in ds.due_items(db, today)}
    assert got["1"].status == "today" and got["1"].days == 0 and got["1"].as_dict()["label"] == "Vence hoje"
    assert got["2"].status == "overdue" and got["2"].days == 1 and got["2"].as_dict()["label"] == "Venceu há 1 dia"
    assert got["4"].status == "soon" and got["4"].as_dict()["label"] == "Vence amanhã"
    assert "3" not in got and "5" not in got            # dia 20 venceu há 19 dias e dia 22 há 17 (> 15); próximos só em 11/13 dias
    assert [i.unit.number for i in ds.due_items(db, today)][:2] == ["1", "2"]        # hoje antes de atrasados antes de próximos
    assert {hoje, ontem, antigo, amanha, longe}


def test_acknowledging_clears_only_that_occurrence(db):
    u = _unit(db, 9)
    assert ds.due_items(db, date(2026, 10, 9))[0].status == "today"
    assert ds.acknowledge(db, u, date(2026, 10, 9)) == date(2026, 10, 9)
    db.commit()
    assert [i for i in ds.due_items(db, date(2026, 10, 9)) if i.status != "soon"] == []   # baixa dada
    assert [i for i in ds.due_items(db, date(2026, 10, 10)) if i.status != "soon"] == []
    assert ds.due_items(db, date(2026, 11, 9))[0].status == "today"                       # no mês seguinte volta a avisar


def test_inactive_unit_or_store_and_units_without_due_day_are_ignored(db):
    _unit(db, 9, number="1", active=False)
    _unit(db, None, number="2")
    s = _unit(db, 9, number="3", code="L2")
    s.store.active = False
    db.commit()
    assert ds.due_items(db, date(2026, 10, 9)) == []


def test_item_links_the_bill_with_that_due_date(db):
    u = _unit(db, 9)
    db.add(EnergyBill(unit_id=u.id, record_type_id=u.record_type_id, reference=date(2026, 9, 1), due_date=date(2026, 10, 9),
                      total_value=D("20505.00")))
    db.commit()
    d = ds.due_items(db, date(2026, 10, 9))[0].as_dict()
    assert d["value"] == 20505.0 and d["bill_id"] and d["store"] == "L1"
    assert ds.due_items(db, date(2026, 11, 9))[0].as_dict()["value"] is None         # mês sem conta lançada


# ---------------------------------------------------------------- cadastro rápido de ponto de energia
def _today_iso():
    return ds.local_today().isoformat()


def test_quick_add_point_creates_unit_with_due_day_and_audit(client, db):
    store_id = _make_store(client, unit=None)
    r = client.post("/points", {"store_id": store_id, "number": "12.345.678-9", "due_date": "2026-11-17",
                                "description": "Padaria", "next": "/stores"})
    assert r.status_code == 303 and r.headers["location"] == "/stores"
    u = db.query(ConsumerUnit).one()
    assert u.due_day == 17 and u.number_normalized == "123456789" and u.description == "Padaria" and u.store_id == store_id
    assert u.record_type.is_bill and db.query(AuditLog).filter_by(entity="consumer_unit", action="create").count() >= 1
    assert "dia 17 de cada mês" in client.get("/stores").text                       # confirmação ao usuário


def test_quick_add_existing_unit_only_updates_due_day(client, db):
    store_id = _make_store(client, unit="12.060.073.018-19")
    r = client.post("/points", {"store_id": store_id, "number": "1206007301819", "due_date": "2026-11-05"})
    assert r.status_code == 303 and db.query(ConsumerUnit).count() == 1
    db.expire_all()
    assert db.query(ConsumerUnit).one().due_day == 5


def test_quick_add_validation_and_open_redirect_protection(client, db):
    store_id = _make_store(client, unit=None)
    bad = client.post("/points", {"store_id": store_id, "number": "--", "due_date": "31/31/2026"})
    assert bad.status_code == 400 and "Informe a data de vencimento" in bad.text and "Informe o número" in bad.text
    ok = client.post("/points", {"store_id": store_id, "number": "55", "due_date": "2026-11-05", "next": "https://evil.example/"})
    assert ok.headers["location"] == "/"                                            # next externo é descartado
    assert client.post("/points", {"store_id": "9999", "number": "6", "due_date": "2026-11-05"}).status_code == 400
    assert client.post("/points", {"store_id": store_id, "number": "", "due_date": "2026-11-05"}).status_code == 422    # campo obrigatório


def test_quick_add_available_to_employee_not_to_director_or_viewer(client, db):
    store_id = _make_store(client, unit=None)
    func, diretor, consulta = _user(client, "func9", "operator"), _user(client, "dir9", "director"), _user(client, "con9", "viewer")
    assert func.post("/points", {"store_id": store_id, "number": "77", "due_date": "2026-11-05"}).status_code == 303
    for c in (diretor, consulta):
        assert c.get("/points/new").status_code == 403
        assert c.post("/points", {"store_id": store_id, "number": "78", "due_date": "2026-11-05"}).status_code == 403
    assert "data-open-point" in func.get("/stores").text and "data-open-point" not in diretor.get("/diretoria").text


# ---------------------------------------------------------------- API do aviso/sino
def test_api_due_lists_today_and_ack_removes_it(client, db):
    func = _user(client, "func5", "operator")
    u = _unit(db, ds.local_today().day)
    data = func.get("/api/due").json()
    item = next(i for i in data["items"] if i["unit_id"] == u.id)
    assert item["status"] == "today" and item["label"] == "Vence hoje" and data["can_ack"] is True and data["today"] == _today_iso()
    assert func.post(f"/api/due/{u.id}/ack").json()["ok"] is True
    assert not [i for i in func.get("/api/due").json()["items"] if i["unit_id"] == u.id and i["status"] != "soon"]
    assert db.query(AuditLog).filter_by(action="due_ack", entity_id=u.id).count() == 1


def test_only_the_employee_is_notified_not_admin_director_or_viewer(client, db):
    u = _unit(db, ds.local_today().day)
    func = _user(client, "func6", "operator")
    assert any(i["unit_id"] == u.id for i in func.get("/api/due").json()["items"])
    assert 'id="bell"' in func.get("/stores").text and 'aria-label="Vencimentos' in func.get("/stores").text
    for who in (client, _user(client, "dir8", "director"), _user(client, "con8", "viewer")):       # admin, diretoria, consulta
        assert who.get("/api/due").status_code == 403
        assert who.post(f"/api/due/{u.id}/ack").status_code == 403
        assert 'id="bell"' not in who.get("/stores").text and "Vencimentos" not in who.get("/stores").text.split("<main")[1].split("<h1")[0]


def test_api_due_requires_login_and_csrf(client, db):
    from fastapi.testclient import TestClient

    from app.main import app
    u = _unit(db, 9)
    assert TestClient(app).get("/api/due", follow_redirects=False).status_code == 303
    assert client.tc.post(f"/api/due/{u.id}/ack", follow_redirects=False).status_code == 403          # sem CSRF


def test_bill_import_teaches_the_unit_its_due_day(client, png, db):
    _make_store(client)
    job = _upload(client, png)
    assert db.query(ConsumerUnit).one().due_day is None
    client.post(f"/import/{job}/confirm", {**_form_from_review(client.get(f"/import/{job}/review").text), "unit_mode": "matched"})
    db.expire_all()
    assert db.query(ConsumerUnit).one().due_day == 9                                  # vencimento 09/10/2026 -> todo dia 9


def test_help_page_is_role_aware(client):
    html = client.get("/ajuda").text
    assert "Novo ponto de energia" in html and "Administração" in html and "Painel da diretoria" in html
    assert "Ir para o conteúdo" in client.get("/").text                                  # link de acessibilidade
    assert timedelta(0) is not None
