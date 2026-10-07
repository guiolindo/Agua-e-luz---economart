import re

from app.models import ConsumerUnit, EnergyBill, Import

UC = "12.060.073.018-19"


def _make_store(c, code="CD300", unit=UC):
    r = c.post("/stores", {"code": code, "name": "CD Ribeirão"})
    assert r.status_code == 303
    store_id = int(re.search(r"/stores/(\d+)/settings", r.headers["location"]).group(1))
    if unit:
        assert c.post(f"/stores/{store_id}/units", {"number": unit, "description": "Principal"}).status_code == 303
    return store_id


def _upload(c, png, store_id=""):
    r = c.post("/import", {"store_id": store_id}, files={"file": ("conta.png", png, "image/png")})
    assert r.status_code == 303, r.text
    return int(r.headers["location"].rsplit("/", 1)[1])


def _form_from_review(html):
    return dict(re.findall(r'name="([a-z_]+)"[^>]*value="([^"]*)"', html))


def test_requires_login(client):
    from fastapi.testclient import TestClient

    from app.main import app
    anon = TestClient(app)
    r = anon.get("/stores", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert anon.get("/documents/1", follow_redirects=False).status_code == 303


def test_csrf_is_enforced(client):
    r = client.tc.post("/stores", data={"code": "X"}, follow_redirects=False)
    assert r.status_code == 403


def test_rejects_fake_image(client):
    r = client.post("/import", files={"file": ("conta.png", b"<html>hack</html>", "image/png")})
    assert r.status_code == 400 and "conteúdo" in r.text


def test_full_import_flow_known_unit(client, png, db):
    store_id = _make_store(client)
    job_id = _upload(client, png)
    review = client.get(f"/import/{job_id}", follow_redirects=True)
    assert review.status_code == 200
    assert "Unidade encontrada no cadastro" in review.text and "CD300" in review.text
    assert 'value="20505,00"' in review.text and 'value="2026-09"' in review.text

    form = {**_form_from_review(review.text), "unit_mode": "matched", "notes": "ok"}
    r = client.post(f"/import/{job_id}/confirm", form)
    assert r.status_code == 303 and r.headers["location"].startswith(f"/stores/{store_id}?highlight=")

    db.expire_all()
    bill = db.query(EnergyBill).one()
    assert str(bill.total_value) == "20505.00" and bill.reference.month == 9 and bill.document_id
    assert bill.consumption_total == 63760 and len(bill.line_items) == 8 and bill.created_by
    assert db.get(Import, job_id).status == "confirmed"

    chart = client.get(f"/api/stores/{store_id}/chart?type_id={bill.record_type_id}&highlight={bill.unit_id}").json()
    assert chart["series"][0]["data"][-1] == 20505.0 and chart["series"][0]["highlight"]
    assert client.get(f"/documents/{bill.document_id}").headers["content-type"] == "image/png"
    assert client.get(f"/stores/{store_id}").status_code == 200 and client.get(f"/units/{bill.unit_id}").status_code == 200


def test_duplicate_requires_decision_then_replace(client, png, db):
    _make_store(client)
    first = _upload(client, png)
    html = client.get(f"/import/{first}/review").text
    form = {**_form_from_review(html), "unit_mode": "matched"}
    client.post(f"/import/{first}/confirm", form)

    second = _upload(client, png)
    html2 = client.get(f"/import/{second}/review").text
    assert "já está cadastrada" in html2
    form2 = {**_form_from_review(html2), "unit_mode": "matched", "total_value": "21000,00"}
    r = client.post(f"/import/{second}/confirm", form2)  # sem decisão -> não salva
    assert r.status_code == 409 and db.query(EnergyBill).count() == 1

    r = client.post(f"/import/{second}/confirm", {**form2, "duplicate_action": "replace"})
    assert r.status_code == 303
    db.expire_all()
    bills = db.query(EnergyBill).all()
    assert len(bills) == 1 and str(bills[0].total_value) == "21000.00"


def test_unknown_unit_can_be_registered_during_import(client, png, db):
    store_id = _make_store(client, unit=None)
    job_id = _upload(client, png)
    html = client.get(f"/import/{job_id}/review").text
    assert "Unidade consumidora não cadastrada" in html

    form = {**_form_from_review(html), "unit_mode": "new", "new_store_id": str(store_id), "new_number": UC}
    assert client.post(f"/import/{job_id}/confirm", form).status_code == 303
    db.expire_all()
    unit = db.query(ConsumerUnit).one()
    assert unit.store_id == store_id and db.query(EnergyBill).one().unit_id == unit.id


def test_confirm_validates_server_side(client, png, db):
    _make_store(client)
    job_id = _upload(client, png)
    form = {**_form_from_review(client.get(f"/import/{job_id}/review").text), "unit_mode": "matched", "total_value": "abc"}
    r = client.post(f"/import/{job_id}/confirm", form)
    assert r.status_code == 400 and "Número inválido" in r.text and db.query(EnergyBill).count() == 0


def test_manual_entries_and_dashboard(client, db):
    store_id = _make_store(client)
    from app.models import RecordType
    ll = db.query(RecordType).filter_by(code="ll-energia").one()
    r = client.post("/manual", {"store_id": store_id, "type_id": ll.id, "reference": "2026-09", "value": "1.500,50",
                                "f_consumo_kwh": "10.000"})
    assert r.status_code == 303
    dup = client.post("/manual", {"store_id": store_id, "type_id": ll.id, "reference": "2026-09", "value": "2"})
    assert dup.status_code == 409
    assert client.get("/?month=2026-09").status_code == 200
    page = client.get("/?month=2026-10").text
    assert "Lançado no mês anterior" in page  # recorrência pendente


def test_new_record_type_and_manual_entry(client, db):
    store_id = _make_store(client)
    assert client.post("/types", {"name": "Energia Solar", "fields": "Geração (kWh)"}).status_code == 303
    from app.models import RecordType
    solar = db.query(RecordType).filter_by(code="energia-solar").one()
    assert solar.fields == [{"key": "geracao", "label": "Geração", "unit": "kWh"}]
    r = client.post("/manual", {"store_id": store_id, "type_id": solar.id, "reference": "2026-01", "value": "10",
                                "f_geracao": "500"})
    assert r.status_code == 303
