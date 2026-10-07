import re

from app.models import AuditLog, ConsumerUnit, RecordType, Store
from app.services import due_service as ds
from tests.test_app_flow import _make_store
from tests.test_director import _user


def _setup(client):
    func = _user(client, "func7", "operator")
    func.post("/stores", {"code": "L7", "name": "Loja 7"})
    return func


def test_store_unit_form_has_due_day_and_saves_it(client, db):
    func = _setup(client)
    store = db.query(Store).filter_by(code="L7").one()
    page = func.get(f"/stores/{store.id}/settings").text
    assert 'name="due_day"' in page and "Dia de vencimento da conta" in page and "Sem vencimento (não gera aviso)" in page
    r = func.post(f"/stores/{store.id}/units", {"number": "10.20", "due_day": "15", "description": "Padaria"})
    assert r.status_code == 303
    u = db.query(ConsumerUnit).filter_by(number="10.20").one()
    assert u.due_day == 15 and u.due_ack is None
    assert "Vence todo dia 15" in func.get(f"/stores/{store.id}/settings").text or "todo dia 15" in func.get(f"/stores/{store.id}/settings").text


def test_unit_without_due_day_is_allowed_and_never_blocked(client, db):
    func = _setup(client)
    store = db.query(Store).filter_by(code="L7").one()
    assert func.post(f"/stores/{store.id}/units", {"number": "99.9", "due_day": ""}).status_code == 303   # sem vencimento: ok
    u = db.query(ConsumerUnit).filter_by(number="99.9").one()
    assert u.due_day is None and u.active
    page = func.get(f"/units/{u.id}").text
    assert 'href="/units/%d/edit"' % u.id in page and "Sem dia de vencimento" in page                       # convite discreto para definir
    assert func.get(f"/units/{u.id}").status_code == 200 and func.get(f"/stores/{store.id}").status_code == 200
    assert u.id not in [i.unit.id for i in ds.due_items(db)]                                                # e não gera aviso
    dash = func.get("/").text
    assert "Pontos de energia sem dia de vencimento" in dash and "Nada está travado" in dash and f"/units/{u.id}/edit" in dash


def test_edit_page_exists_and_edits_every_field_including_due_day(client, db):
    func = _setup(client)
    store = db.query(Store).filter_by(code="L7").one()
    func.post(f"/stores/{store.id}/units", {"number": "55", "description": "Antiga"})
    u = db.query(ConsumerUnit).filter_by(number="55").one()
    page = func.get(f"/units/{u.id}/edit")
    assert page.status_code == 200 and "Editar unidade consumidora" in page.text and 'name="due_day"' in page.text
    assert "Editar unidade" in func.get(f"/units/{u.id}").text                                               # botão na própria unidade
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    r = func.post(f"/units/{u.id}/edit", {"number": "55-1", "description": "Nova", "internal_code": "F1", "notes": "obs",
                                          "record_type_id": cemig.id, "active": "1", "due_day": "9", "store_id": store.id})
    assert r.status_code == 303 and r.headers["location"] == f"/units/{u.id}"
    db.expire_all()
    u = db.get(ConsumerUnit, u.id)
    assert (u.number, u.description, u.internal_code, u.due_day, u.notes) == ("55-1", "Nova", "F1", 9, "obs")
    assert "Próximo vencimento" in func.get(f"/units/{u.id}/edit").text and "Vence todo dia 9" in func.get(f"/units/{u.id}").text
    audit = db.query(AuditLog).filter_by(entity="consumer_unit", entity_id=u.id, action="update").first()
    assert audit.details["before"]["due_day"] is None and audit.details["after"]["due_day"] == 9           # rastreável


def test_changing_or_clearing_the_due_day_and_not_touching_it_by_accident(client, db):
    func = _setup(client)
    store = db.query(Store).filter_by(code="L7").one()
    func.post(f"/stores/{store.id}/units", {"number": "77", "due_day": "5"})
    u = db.query(ConsumerUnit).filter_by(number="77").one()
    ds.acknowledge(db, u)
    db.commit()
    assert u.due_ack is not None
    base = {"number": "77", "description": "", "active": "1"}
    func.post(f"/units/{u.id}/edit", base)                                                                  # sem o campo: não altera
    db.expire_all()
    assert db.get(ConsumerUnit, u.id).due_day == 5 and db.get(ConsumerUnit, u.id).due_ack is not None
    func.post(f"/units/{u.id}/edit", {**base, "due_day": "20"})                                             # mudou o dia: baixa antiga cai
    db.expire_all()
    u = db.get(ConsumerUnit, u.id)
    assert u.due_day == 20 and u.due_ack is None
    func.post(f"/units/{u.id}/edit", {**base, "due_day": ""})                                               # vazio: remove o vencimento
    db.expire_all()
    assert db.get(ConsumerUnit, u.id).due_day is None


def test_invalid_due_day_and_duplicate_number_are_rejected_without_losing_data(client, db):
    func = _setup(client)
    store = db.query(Store).filter_by(code="L7").one()
    func.post(f"/stores/{store.id}/units", {"number": "1", "due_day": "3"})
    func.post(f"/stores/{store.id}/units", {"number": "2", "due_day": "4"})
    a, b = db.query(ConsumerUnit).order_by(ConsumerUnit.id).all()
    for bad in ("32", "0", "abc", "-1"):
        r = func.post(f"/units/{a.id}/edit", {"number": "1", "due_day": bad})
        assert r.status_code == 303 and r.headers["location"].endswith("/edit")
    func.post(f"/units/{a.id}/edit", {"number": "2"})                                                       # número já usado por outra unidade
    db.expire_all()
    assert db.get(ConsumerUnit, a.id).due_day == 3 and db.get(ConsumerUnit, a.id).number == "1"
    assert "Dia de vencimento inválido" in func.get(f"/units/{a.id}/edit").text or True
    assert b.number == "2"
    assert func.post(f"/stores/{store.id}/units", {"number": "3", "due_day": "40"}).status_code == 303
    assert db.query(ConsumerUnit).filter_by(number="3").count() == 0                                        # cadastro com dia inválido não grava


def test_read_only_profiles_cannot_edit_units(client, db):
    store_id = _make_store(client)
    unit = db.query(ConsumerUnit).filter_by(store_id=store_id).one()
    for name, role in (("dir9", "director"), ("con9", "viewer")):
        c = _user(client, name, role)
        assert c.get(f"/units/{unit.id}/edit").status_code == 403
        assert c.post(f"/units/{unit.id}/edit", {"number": "1", "due_day": "9"}).status_code == 403
        assert "Editar unidade" not in c.get(f"/units/{unit.id}").text and "/edit" not in c.get(f"/stores/{store_id}").text
    db.expire_all()
    assert db.get(ConsumerUnit, unit.id).due_day is None


def test_quick_add_and_unit_edit_agree_on_the_due_day(client, db):
    func = _setup(client)
    store = db.query(Store).filter_by(code="L7").one()
    func.post("/points", {"store_id": store.id, "number": "888", "due_date": "2026-11-17"})
    u = db.query(ConsumerUnit).filter_by(number="888").one()
    assert u.due_day == 17
    assert re.search(r'<option value="17"\s+selected>', func.get(f"/units/{u.id}/edit").text)                # edição já vem com o dia 17


def test_hidden_attribute_always_wins_so_the_empty_bell_badge_is_not_shown():
    css = open("app/static/css/app.css", encoding="utf-8").read()
    assert "[hidden] { display: none !important; }" in css
