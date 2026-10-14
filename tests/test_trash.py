"""Lixeira, barreira contra exclusão em massa e limite de acesso por IP."""
from app.models import AuditLog, Document, EnergyBill, ManualRecord, RecordType, TrashItem
from tests.test_app_flow import _form_from_review, _make_store, _upload
from tests.test_director import _user


def _imported_bill(client, png, db):
    _make_store(client)
    job_id = _upload(client, png)
    review = client.get(f"/import/{job_id}", follow_redirects=True)
    client.post(f"/import/{job_id}/confirm", {**_form_from_review(review.text), "unit_mode": "matched"})
    db.expire_all()
    return db.query(EnergyBill).one()


def test_deleted_bill_goes_to_trash_and_admin_restores_it_with_the_original(client, png, db):
    bill = _imported_bill(client, png, db)
    bill_id, doc_id, total, unit_id = bill.id, bill.document_id, bill.total_value, bill.unit_id
    r = client.post(f"/manual/bills/{bill_id}/delete", {})
    assert r.status_code == 303
    db.expire_all()
    assert db.get(EnergyBill, bill_id) is None
    item = db.query(TrashItem).one()
    assert item.kind == "energy_bill" and item.original_id == bill_id and "CD300" in item.summary
    assert db.get(Document, doc_id).data is not None                     # o original não é apagado na exclusão
    page = client.get("/lixeira").text
    assert item.summary in page and "Restaurar" in page
    assert client.post(f"/lixeira/{item.id}/restaurar", {}).status_code == 303
    db.expire_all()
    back = db.get(EnergyBill, bill_id)
    assert back is not None and back.total_value == total and back.document_id == doc_id and back.unit_id == unit_id
    assert back.line_items and back.reference.month == 9                 # a linha inteira volta, não só o valor
    assert db.get(TrashItem, item.id).restored_at is not None
    assert client.get(f"/documents/{doc_id}").status_code == 200
    assert db.query(AuditLog).filter_by(action="restore", entity="energy_bill").count() == 1


def test_restore_refuses_when_the_month_was_relaunched(client, png, db):
    bill = _imported_bill(client, png, db)
    client.post(f"/manual/bills/{bill.id}/delete", {})
    item = db.query(TrashItem).one()
    r = client.post("/manual", {"store_id": bill.unit.store_id, "unit_id": bill.unit_id, "type_id": bill.record_type_id,
                                "reference": bill.reference.strftime("%Y-%m"), "total_value": "10", "days": "30"})
    assert r.status_code == 303, r.text[:300]
    r = client.post(f"/lixeira/{item.id}/restaurar", {})
    assert "já foi lançada de novo" in client.get(r.headers["location"]).text
    assert "Lançada de novo" in client.get("/lixeira").text                       # admin vê marcado, sem botão
    db.expire_all()
    assert db.get(TrashItem, item.id).restored_at is None


def test_mass_deletion_is_blocked_and_admin_undoes_everything(client, db, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "max_deletes_per_hour", 3)
    store_id = _make_store(client, unit=None)
    ll = db.query(RecordType).filter_by(code="ll-energia").one()
    for m in range(1, 6):
        client.post("/manual/lote", {"store_ids": [str(store_id)], "type_id": ll.id, "reference": f"2026-0{m}", "value": str(100 * m)})
    ids = [r.id for r in db.query(ManualRecord).order_by(ManualRecord.id)]
    func = _user(client, "vingativo", "operator")
    for rid in ids[:3]:
        assert func.post(f"/manual/records/{rid}/delete", {}).status_code == 303
    r = func.post(f"/manual/records/{ids[3]}/delete", {})
    assert "Exclusão bloqueada" in func.get(r.headers["location"]).text
    db.expire_all()
    assert db.query(ManualRecord).count() == 2 and db.query(TrashItem).count() == 3
    assert "Exclusão em massa barrada" in client.get("/admin").text
    uid = db.query(TrashItem).first().deleted_by
    page = client.get(f"/lixeira?por={uid}").text
    assert "Restaurar tudo de vingativo" in page and "vingativo tentou excluir mais de 3" in page
    client.post("/lixeira/restaurar-de", {"deleted_by": uid})                      # sem senha: nada
    db.expire_all()
    assert db.query(ManualRecord).count() == 2
    client.post("/lixeira/restaurar-de", {"deleted_by": uid, "confirm_password": "admin-pass-123"})
    db.expire_all()
    assert db.query(ManualRecord).count() == 5
    assert sorted(str(r.value) for r in db.query(ManualRecord)) == ["100.00", "200.00", "300.00", "400.00", "500.00"]


def test_admin_is_not_limited_and_operator_cannot_open_trash(client, db, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "max_deletes_per_hour", 1)
    store_id = _make_store(client, unit=None)
    ll = db.query(RecordType).filter_by(code="ll-energia").one()
    for m in (1, 2):
        client.post("/manual/lote", {"store_ids": [str(store_id)], "type_id": ll.id, "reference": f"2026-0{m}", "value": "1"})
    for r in db.query(ManualRecord).all():
        client.post(f"/manual/records/{r.id}/delete", {})
    db.expire_all()
    assert db.query(ManualRecord).count() == 0
    func = _user(client, "func2", "operator")
    assert func.post("/lixeira/restaurar-de", {"deleted_by": 1}).status_code == 403
    assert "Nada na sua lixeira" in func.get("/lixeira").text                     # não vê o que o admin excluiu
    item = db.query(TrashItem).first()
    r = func.post(f"/lixeira/{item.id}/restaurar", {})
    assert "não está na sua lixeira" in func.get(r.headers["location"]).text
    viewer = _user(client, "cons1", "viewer")
    assert viewer.get("/lixeira", follow_redirects=False).status_code == 403
    assert client.get("/admin/lixeira?por=2", follow_redirects=False).headers["location"] == "/lixeira?por=2"


def test_editing_a_manual_record_keeps_the_previous_value(client, db):
    store_id = _make_store(client, unit=None)
    ll = db.query(RecordType).filter_by(code="ll-energia").one()
    client.post("/manual/lote", {"store_ids": [str(store_id)], "type_id": ll.id, "reference": "2026-08", "value": "100"})
    rec = db.query(ManualRecord).one()
    client.post("/manual", {"store_id": store_id, "type_id": ll.id, "reference": "2026-08", "value": "999",
                            "edit_record": rec.id})
    log = db.query(AuditLog).filter_by(action="update", entity="manual_record").one()
    from decimal import Decimal
    assert Decimal(log.details["before"]["value"]) == 100 and Decimal(log.details["value"]) == 999


def test_page_flood_from_one_ip_is_cut(client):
    codes = [client.get("/login").status_code for _ in range(301)]
    assert 429 in codes and codes.index(429) >= 295                      # o login do teste já usou 2-3 acessos
    r = client.get("/login", headers={"Accept": "text/html"})
    assert r.status_code == 429 and "Aguarde" in r.text
    assert client.get("/static/css/app.css").status_code == 200           # arquivos do sistema não contam


def _ll_records(client, db, n=2):
    store_id = _make_store(client, unit=None)
    ll = db.query(RecordType).filter_by(code="ll-energia").one()
    for m in range(1, n + 1):
        client.post("/manual/lote", {"store_ids": [str(store_id)], "type_id": ll.id, "reference": f"2026-0{m}", "value": str(10 * m)})
    return store_id, ll


def test_person_undoes_own_mistake_right_away(client, db):
    store_id, ll = _ll_records(client, db)
    func = _user(client, "func3", "operator")
    rec = db.query(ManualRecord).order_by(ManualRecord.id).first()
    r = func.post(f"/manual/records/{rec.id}/delete", {})
    page = func.get(r.headers["location"]).text
    assert "Lançamento excluído:" in page and "Desfazer" in page                  # o aviso já traz o botão
    item = db.query(TrashItem).one()
    assert item.summary in func.get("/lixeira").text                               # lixeira pessoal
    r = func.post(f"/lixeira/{item.id}/restaurar", {"next": f"/stores/{store_id}"})
    assert r.headers["location"] == f"/stores/{store_id}"
    db.expire_all()
    assert db.query(ManualRecord).count() == 2
    assert "Desfazer" not in func.get(f"/stores/{store_id}").text                 # aparece uma vez só


def test_after_30_days_only_the_admin_restores(client, db):
    from datetime import timedelta

    from app.models.mixins import utcnow
    _ll_records(client, db, 1)
    func = _user(client, "func4", "operator")
    func.post(f"/manual/records/{db.query(ManualRecord).one().id}/delete", {})
    item = db.query(TrashItem).one()
    func.get("/")                                                                  # consome o aviso "Desfazer"
    item.deleted_at = utcnow() - timedelta(days=31)
    db.commit()
    assert "Nada na sua lixeira" in func.get("/lixeira").text
    func.post(f"/lixeira/{item.id}/restaurar", {})
    db.expire_all()
    assert db.query(ManualRecord).count() == 0
    assert item.summary in client.get("/lixeira").text                             # continua na do administrador
    client.post(f"/lixeira/{item.id}/restaurar", {})
    db.expire_all()
    assert db.query(ManualRecord).count() == 1


def test_relaunched_month_leaves_the_personal_trash_and_comes_back_if_needed(client, db):
    store_id, ll = _ll_records(client, db, 1)
    func = _user(client, "func5", "operator")
    r = func.post(f"/manual/records/{db.query(ManualRecord).one().id}/delete", {})
    func.get(r.headers["location"])                                                # viu o aviso de exclusão
    item = db.query(TrashItem).one()
    func.post("/manual/lote", {"store_ids": [str(store_id)], "type_id": ll.id, "reference": "2026-01", "value": "77"})
    assert item.summary not in func.get("/lixeira").text                           # lançou de novo: some da lixeira
    r = func.post(f"/lixeira/{item.id}/restaurar", {})                             # tentou mesmo assim (aba antiga)
    assert "já foi lançada de novo" in func.get(r.headers["location"]).text
    db.expire_all()
    assert [str(r.value) for r in db.query(ManualRecord)] == ["77.00"]             # nada duplicado nem sobrescrito
    r = func.post(f"/manual/records/{db.query(ManualRecord).one().id}/delete", {})  # excluiu a nova: a antiga volta a valer
    func.get(r.headers["location"])
    page = func.get("/lixeira").text
    assert item.summary in page and f"/lixeira/{item.id}/restaurar" in page
