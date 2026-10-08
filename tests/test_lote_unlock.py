import re
from datetime import date
from decimal import Decimal

from app.middleware import reset_rate_limits
from app.models import AuditLog, ManualRecord, RecordType, User
from tests.test_app_flow import _make_store
from tests.test_security import LOCKED, _create_user, _login, _new_client


# ------------------------------------------------------------------ desbloquear
def _lock(client, name):
    pin = _create_user(client, name, "operator")
    c = _new_client()
    for _ in range(3):                                    # senha provisória: bloqueia na 3ª
        _login(c, name, "errada-errada-1")
    assert LOCKED in _login(c, name, pin).text
    reset_rate_limits()
    return pin


def test_admin_sees_who_is_locked_and_unlocks(client, db):
    pin = _lock(client, "bia")
    html = client.get("/admin/users").text
    assert "Bloqueado até" in html and "Desbloquear" in html
    uid = db.query(User).filter_by(username="bia").one().id
    r = client.post(f"/admin/users/{uid}/unlock")
    assert r.status_code == 303
    assert "desbloqueado" in client.get("/admin/users").text
    assert "Bloqueado até" not in client.get("/admin/users").text
    assert _login(_new_client(), "bia", pin).status_code == 303          # entra de novo com o mesmo PIN
    db.expire_all()
    assert db.query(AuditLog).filter_by(action="account_unlocked").count() == 1


def test_unlock_on_a_user_that_is_not_locked_changes_nothing(client, db):
    _create_user(client, "caio", "operator")
    uid = db.query(User).filter_by(username="caio").one().id
    client.post(f"/admin/users/{uid}/unlock")
    assert "não está bloqueado" in client.get("/admin/users").text
    db.expire_all()
    assert db.query(AuditLog).filter_by(action="account_unlocked").count() == 0


def test_only_admin_can_unlock(client, db):
    _lock(client, "dani")
    pw_op = _create_user(client, "edu", "operator")
    op = _new_client()
    assert _login(op, "edu", pw_op).status_code == 303
    uid = db.query(User).filter_by(username="dani").one().id
    assert op.post(f"/admin/users/{uid}/unlock").status_code in (303, 403)
    db.expire_all()
    assert db.query(User).filter_by(username="dani").one().blocked_until is not None     # continua bloqueada


# ------------------------------------------------------------------ lote
def _stores(client, *codes):
    return [_make_store(client, code=c, unit=None) for c in codes]


def _ll(db):
    return db.query(RecordType).filter_by(code="ll-energia").one()


def test_manual_page_asks_what_to_do_first_and_the_form_opens_after_choosing(client, db):
    ll = _ll(db)
    choose = client.get("/manual").text
    assert "LL Energia · várias lojas" in choose and "Lançamento de uma loja" in choose and "mode-ll" in choose
    assert 'id="mf"' not in choose and 'name="store_id"' not in choose              # nenhum formulário antes de escolher
    assert 'href="/manual?modo=loja"' in choose and 'href="/manual/lote?type=ll-energia"' in choose
    assert "Lançamentos recentes" in choose                                   # o histórico continua à mão
    single = client.get("/manual?modo=loja").text                                    # escolheu "uma loja": abre o formulário
    assert 'id="mf"' in single and f'<option value="{ll.id}"' not in single and 'data-bill="0"' in single   # LL fora da lista
    assert "Trocar tipo de lançamento" in single and 'class="modes' not in single      # só o formulário, sem a escolha por cima
    a, = _stores(client, "F1")
    assert 'id="mf"' in client.get(f"/manual?store_id={a}").text                     # veio de uma loja: já abre o formulário


def test_form_errors_stay_on_the_form_not_on_the_chooser(client, db):
    r = client.post("/manual", {"type_id": "", "store_id": "", "reference": "", "value": ""})
    assert r.status_code == 400 and 'id="mf"' in r.text


def test_batch_page_for_ll_has_fixed_type_and_the_mode_switcher(client, db):
    ll = _ll(db)
    batch = client.get("/manual/lote?type=ll-energia").text
    assert f'name="type_id" value="{ll.id}"' in batch and 'id="type" name="type_id" required' not in batch   # tipo fixo, sem select
    assert "LL Energia · várias lojas" in batch and "Trocar tipo de lançamento" in batch and 'class="modes' not in batch
    assert client.get("/manual/lote").status_code == 200


def test_single_form_refuses_ll_and_points_to_the_batch_screen(client, db):
    a, = _stores(client, "R1")
    r = client.post("/manual", {"store_id": str(a), "type_id": str(_ll(db).id), "reference": "2026-09", "value": "100,00"})
    assert r.status_code == 400 and "várias lojas" in r.text and db.query(ManualRecord).count() == 0


def test_existing_ll_record_can_still_be_corrected_one_store_at_a_time(client, db):
    a, b = _stores(client, "E1", "E2")
    client.post("/manual/lote", {"type_id": str(_ll(db).id), "reference": "2026-09", "value": "1000,00", "store_ids": [str(a), str(b)]})
    rec = db.query(ManualRecord).filter_by(store_id=a).one()
    page = client.get(f"/manual?record={rec.id}")
    assert page.status_code == 200 and f'<option value="{_ll(db).id}"' in page.text      # ao editar, o tipo aparece
    r = client.post("/manual", {"edit_record": str(rec.id), "store_id": str(a), "type_id": str(_ll(db).id),
                                "reference": "2026-09", "value": "1100,00", "notes": ""})
    assert r.status_code == 303
    db.expire_all()
    assert {x.store_id: x.value for x in db.query(ManualRecord)} == {a: Decimal("1100.00"), b: Decimal("1000.00")}


def test_dashboard_pending_for_ll_links_straight_to_the_batch_screen(client, db):
    a, = _stores(client, "P1")
    db.add(ManualRecord(store_id=a, record_type_id=_ll(db).id, reference=date(2026, 8, 1), value=Decimal("900.00"), data={}))
    db.commit()
    html = client.get("/?month=2026-09").text
    assert "/manual/lote?type=ll-energia" in html


def test_one_entry_becomes_many_records(client, db):
    a, b, c = _stores(client, "L1", "L2", "L3")
    r = client.post("/manual/lote", {"type_id": str(_ll(db).id), "reference": "2026-09", "value": "1.200,00",
                                     "due_date": "2026-10-10", "store_ids": [str(a), str(c)], "notes": "contrato 2026"})
    assert r.status_code == 303 and "/notas?" in r.headers["location"]
    db.expire_all()
    recs = db.query(ManualRecord).order_by(ManualRecord.store_id).all()
    assert [x.store_id for x in recs] == [a, c]                                # a loja L2 ficou de fora
    assert all(x.value == Decimal("1200.00") and x.reference == date(2026, 9, 1) and x.unit_id is None for x in recs)
    assert all(x.due_date == date(2026, 10, 10) and x.notes == "contrato 2026" for x in recs)
    flash = client.get("/notas").text
    assert "em 2 loja(s)" in flash and "R$ 1.200,00" in flash
    batches = {a_.details["batch"] for a_ in db.query(AuditLog).filter_by(entity="manual_record", action="create")}
    assert len(batches) == 1                                                   # auditoria agrupa o lote


def test_batch_validation(client, db):
    a, = _stores(client, "V1")
    base = {"type_id": str(_ll(db).id), "reference": "2026-09", "value": "100,00", "store_ids": [str(a)]}
    for bad, field in [({"store_ids": []}, "Marque pelo menos uma loja"), ({"value": ""}, "Informe o valor"),
                       ({"reference": ""}, "Informe o mês"), ({"value": "abc"}, "Informe o valor"),
                       ({"store_ids": ["99999"]}, "loja inválida"), ({"due_date": "31/02/xx"}, "Data inválida"),
                       ({"type_id": str(db.query(RecordType).filter_by(code="cemig").one().id)}, "Selecione o tipo"),
                       ({"type_id": str(db.query(RecordType).filter_by(code="manutencao-gerador").one().id)}, "Selecione o tipo")]:
        r = client.post("/manual/lote", {**base, **bad})
        assert r.status_code == 400 and field in r.text, (bad, r.text[:200])
    assert db.query(ManualRecord).count() == 0                                 # nada gravado em erro


def test_inactive_store_cannot_receive_a_batch_entry(client, db):
    a, b = _stores(client, "A1", "A2")
    from app.models import Store
    db.get(Store, b).active = False
    db.commit()
    r = client.post("/manual/lote", {"type_id": str(_ll(db).id), "reference": "2026-09", "value": "10", "store_ids": [str(a), str(b)]})
    assert r.status_code == 400 and db.query(ManualRecord).count() == 0


def test_duplicates_must_be_decided_then_skip_or_replace(client, db):
    a, b = _stores(client, "D1", "D2")
    form = {"type_id": str(_ll(db).id), "reference": "2026-09", "value": "1000,00", "store_ids": [str(a)]}
    assert client.post("/manual/lote", form).status_code == 303
    both = {**form, "value": "1500,00", "store_ids": [str(a), str(b)]}
    r = client.post("/manual/lote", both)                                      # D1 já tem: pergunta antes de gravar
    assert r.status_code == 409 and "D1" in r.text and "O que fazer" in r.text and db.query(ManualRecord).count() == 1
    assert 'value="' + str(a) + '" checked' in r.text                           # seleção preservada
    r = client.post("/manual/lote", {**both, "duplicate_action": "skip"})
    assert r.status_code == 303
    db.expire_all()
    vals = {x.store_id: x.value for x in db.query(ManualRecord)}
    assert vals == {a: Decimal("1000.00"), b: Decimal("1500.00")}              # D1 mantida, D2 criada
    assert client.post("/manual/lote", {**both, "duplicate_action": "replace"}).status_code == 303
    db.expire_all()
    assert {x.store_id: x.value for x in db.query(ManualRecord)} == {a: Decimal("1500.00"), b: Decimal("1500.00")}
    assert db.query(ManualRecord).count() == 2                                 # substituiu, não duplicou


def test_batch_records_feed_the_store_summary(client, db):
    from app.models import Store
    from app.services import chart_service
    a, b = _stores(client, "S1", "S2")
    client.post("/manual/lote", {"type_id": str(_ll(db).id), "reference": "2026-09", "value": "700,00", "store_ids": [str(a), str(b)]})
    db.expire_all()
    for sid in (a, b):
        summary = chart_service.store_summary(db, db.get(Store, sid), date(2026, 9, 1), date(2026, 9, 1))
        row = next(r for r in summary["rows"] if r["type"].code == "ll-energia")
        assert [str(v) for v in row["values"]] == ["700.00"]


def test_viewer_cannot_use_batch(client, db):
    pw = _create_user(client, "gil", "viewer")
    v = _new_client()
    assert _login(v, "gil", pw).status_code == 303
    assert v.get("/manual/lote", follow_redirects=False).status_code in (303, 403)
