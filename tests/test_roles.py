import re

from app.models import AuditLog, ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store
from tests.test_app_flow import _make_store
from tests.test_director import _user


def _seed_bill(client, db, store_id):
    unit = db.query(ConsumerUnit).filter_by(store_id=store_id).first()
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    client.post("/manual", {"store_id": store_id, "unit_id": unit.id, "type_id": cemig.id, "reference": "2026-08",
                            "total_value": "1000", "days": "30"})
    return db.query(EnergyBill).one()


def test_employee_is_fully_responsible_for_energy_registers(client, db):
    """Funcionário: lojas/filiais, unidades, fornecedores, contas, lançamentos, correções e exclusões."""
    func = _user(client, "func1", "operator")
    r = func.post("/stores", {"code": "FIL-9", "name": "Filial Nova", "region": "ba", "aliases": "Filial 9"})
    assert r.status_code == 303
    store = db.query(Store).filter_by(code="FIL-9").one()
    assert store.region == "BA"
    assert func.get(f"/stores/{store.id}/settings").status_code == 200
    assert func.post(f"/stores/{store.id}/edit", {"name": "Filial Nove", "active": "1"}).status_code == 303
    assert func.post(f"/stores/{store.id}/units", {"number": "11.222.333-4", "description": "Principal"}).status_code == 303
    unit = db.query(ConsumerUnit).one()
    assert func.post(f"/units/{unit.id}/edit", {"number": "11.222.333-4", "description": "Principal 2", "active": "1"}).status_code == 303
    assert func.post("/types", {"name": "ENERGISA", "kind": "bill"}).status_code == 303
    assert db.query(RecordType).filter_by(code="energisa").one().is_bill
    bill = _seed_bill(func, db, store.id)
    assert func.post(f"/manual/bills/{bill.id}/delete", {}).status_code == 303                  # corrige/exclui o que lançou errado
    ll = db.query(RecordType).filter_by(code="ll-energia").one()
    assert func.post("/manual/lote", {"store_ids": [str(store.id)], "type_id": ll.id, "reference": "2026-08", "value": "10"}).status_code == 303
    rec = db.query(ManualRecord).one()
    assert func.post(f"/manual/records/{rec.id}/delete", {}).status_code == 303
    assert db.query(EnergyBill).count() == 0 and db.query(ManualRecord).count() == 0


def test_admin_role_is_access_management_and_audit(client, db):
    html = client.get("/admin/users").text
    assert "Funcionário · gestão das contas" in html and "acessos e auditoria" in html
    func = _user(client, "func2", "operator")
    nav = func.get("/stores").text
    assert "Tipos de registro" in nav and 'href="/admin/users"' not in nav and 'href="/admin/audit"' not in nav
    assert "Auditoria" in client.get("/stores").text and 'href="/admin/users"' in client.get("/stores").text
    helptxt = func.get("/ajuda").text
    assert "Cadastros: lojas, unidades e tipos" in helptxt and "Usuários e acessos" not in helptxt     # funcionário vê os cadastros, não a administração
    assert "Usuários e acessos" in client.get("/ajuda").text and "quem pode entrar" in client.get("/ajuda").text


def test_read_only_profiles_cannot_register_or_delete_anything(client, db):
    store_id = _make_store(client)
    bill = _seed_bill(client, db, store_id)
    for name, role in (("dir1", "director"), ("con1", "viewer")):
        c = _user(client, name, role)
        for url in ("/stores/new", "/types", f"/stores/{store_id}/settings", "/points/new"):
            assert c.get(url).status_code == 403, (role, url)
        assert c.post("/stores", {"code": "Z"}).status_code == 403
        assert c.post(f"/stores/{store_id}/units", {"number": "999"}).status_code == 403
        assert c.post("/types", {"name": "Algo"}).status_code == 403
        assert c.post(f"/manual/bills/{bill.id}/delete", {}).status_code == 403
        page = c.get(f"/units/{bill.unit_id}").text
        assert "Excluir" not in page and "Cadastro" not in c.get(f"/stores/{store_id}").text


def test_employee_actions_are_traceable_in_the_audit_page(client, db):
    func = _user(client, "func3", "operator")
    func.post("/stores", {"code": "RASTRO"})
    func.post("/types", {"name": "Solar Teste", "kind": "manual"})
    html = client.get("/admin/audit").text                                                      # o admin supervisiona
    assert "func3" in html and re.search(r"Criação · loja</span>", html) and "Criação · tipo de registro" in html
    assert db.query(AuditLog).filter(AuditLog.entity == "store", AuditLog.action == "create").count() == 1


def test_first_login_screen_shows_only_what_works(client):
    """Quem ainda usa a senha provisória só pode criar a senha: sem menu, sino ou botões que redirecionariam de volta."""
    pin = re.search(r"<code[^>]*>(.*?)</code>", client.post("/admin/users", {"username": "novato", "role": "operator"}).text).group(1)
    from tests.test_security import _login, _new_client
    c = _new_client()
    _login(c, "novato", pin)
    page = c.get("/account/password").text
    assert "Crie a sua senha" in page or "Defina uma nova senha" in page
    for hidden in ("data-open-point", 'id="bell"', 'class="nav"', "Importar conta", 'href="/stores"'):
        assert hidden not in page, hidden
    assert "Sair" in page and 'action="/logout"' in page                         # ainda dá para sair
    ok = c.post("/account/password", {"current_password": pin, "new_password": "Energia-Da-Empresa-26", "confirm": "Energia-Da-Empresa-26"})
    assert ok.status_code == 303
    c.refresh()
    after = c.get("/stores").text
    assert 'id="bell"' in after and "data-open-point" in after and 'class="nav"' in after


def test_help_is_tailored_to_each_role(client, db):
    admin = client.get("/ajuda").text
    assert "O que o administrador faz" in admin and "Google Authenticator" in admin and "Verificar integridade" in admin
    assert "O que o funcionário faz" not in admin
    func = _user(client, "func9", "operator").get("/ajuda").text
    assert "O que o funcionário faz" in func and "Enviar uma conta" in func and "Lançar à mão" in func
    assert "Google Authenticator" not in func and "Como ler o Painel da diretoria" not in func and "Usuários e acessos" not in func
    director = _user(client, "dir9", "director").get("/ajuda").text
    assert "O que a diretoria faz" in director and "Como ler o Painel da diretoria" in director
    assert "Enviar uma conta" not in director and "Usuários e acessos" not in director
    viewer = _user(client, "con9", "viewer").get("/ajuda").text
    assert "O que a consulta faz" in viewer and "Achar, abrir e imprimir uma conta" in viewer
    assert "Enviar uma conta" not in viewer and "Como ler o Painel da diretoria" not in viewer and "Dúvidas comuns" in viewer


def test_deleting_a_bill_that_came_from_an_import_releases_the_import(client, db):
    """Excluir uma conta vinda de importação não pode deixar a importação apontando para ela (violaria a FK no Postgres)."""
    from app.models import Document
    from app.models.import_job import Import

    store_id = _make_store(client)
    bill = _seed_bill(client, db, store_id)
    doc = Document(filename="a.pdf", content_type="application/pdf", size=1, sha256="x" * 64, data=b"x")
    db.add(doc)
    db.flush()
    imp = Import(document_id=doc.id, status="confirmed", bill_id=bill.id)
    db.add(imp)
    db.commit()
    imp_id = imp.id
    assert client.post(f"/manual/bills/{bill.id}/delete", {}).status_code == 303
    db.expire_all()
    assert db.query(EnergyBill).count() == 0 and db.get(Import, imp_id).bill_id is None
