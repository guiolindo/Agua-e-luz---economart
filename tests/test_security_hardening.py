"""Pentest interno (2026-10-10): cada teste cobre um achado real da revisão de segurança."""
import asyncio

from app.models import Document, EnergyBill, Import, User
from app.services import totp_service
from tests.test_app_flow import _form_from_review, _make_store, _upload
from tests.test_director import _user
from tests.test_security import _create_user, _login, _new_client


def _review_confirm(client, job):
    html = client.get(f"/import/{job}/review").text
    form = {**_form_from_review(html), "unit_mode": "matched"}
    assert client.post(f"/import/{job}/confirm", form).status_code == 303


# ---------------------------------------------------------- documentos: visibilidade por estado, não só por login
def test_viewer_cannot_see_a_document_still_in_review(client, db, png):
    """Antes de a conta ser confirmada, a foto é material de conferência: só quem lança contas a vê."""
    _make_store(client)
    job = _upload(client, png)
    doc_id = db.query(Import).filter_by(id=job).one().document_id
    viewer = _user(client, "vis1", "viewer")
    director = _user(client, "dir1", "director")
    assert viewer.get(f"/documents/{doc_id}").status_code == 403
    assert director.get(f"/documents/{doc_id}").status_code == 403
    assert client.get(f"/documents/{doc_id}").status_code == 200        # quem importou (writer) continua vendo


def test_viewer_sees_the_document_once_the_bill_is_confirmed(client, db, png):
    _make_store(client)
    job = _upload(client, png)
    _review_confirm(client, job)
    bill = db.query(EnergyBill).one()
    viewer = _user(client, "vis2", "viewer")
    assert viewer.get(f"/documents/{bill.document_id}").status_code == 200


# ---------------------------------------------------------- excluir conta apaga o arquivo (sem outra referência)
def test_deleting_a_bill_purges_its_document(client, db, png):
    _make_store(client)
    job = _upload(client, png)
    _review_confirm(client, job)
    bill = db.query(EnergyBill).one()
    doc_id = bill.document_id
    assert client.get(f"/documents/{doc_id}").status_code == 200
    assert client.post(f"/manual/bills/{bill.id}/delete", {}).status_code == 303
    db.expire_all()
    assert db.get(Document, doc_id).data is None
    assert client.get(f"/documents/{doc_id}").status_code == 410


# ---------------------------------------------------------- limite de corpo sem Content-Length
def test_body_size_limit_enforced_without_content_length_header():
    """Antes, sem Content-Length (chunked) size ficava 0 e o limite nunca disparava: o corpo era lido inteiro."""
    from app.middleware import BodySizeLimitMiddleware

    chunk = b"x" * (1024 * 1024)
    calls = {"n": 0}

    async def receive():
        calls["n"] += 1
        return {"type": "http.request", "body": chunk, "more_body": True}   # nunca termina (ataque)

    async def downstream(scope, receive, send):
        total = 0
        while True:
            msg = await receive()
            total += len(msg.get("body") or b"")
            if not msg.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})

    sent = []

    async def send(msg):
        sent.append(msg)

    mw = BodySizeLimitMiddleware(downstream)
    scope = {"type": "http", "method": "POST", "path": "/login", "headers": []}
    asyncio.run(mw(scope, receive, send))

    assert sent and sent[0]["type"] == "http.response.start" and sent[0]["status"] == 413
    assert calls["n"] < 5                                                   # abortou cedo, não "bebeu" o ataque inteiro


def test_body_size_limit_lets_small_requests_through():
    from app.middleware import BodySizeLimitMiddleware

    async def receive():
        return {"type": "http.request", "body": b"ok", "more_body": False}

    async def downstream(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})

    sent = []

    async def send(msg):
        sent.append(msg)

    mw = BodySizeLimitMiddleware(downstream)
    asyncio.run(mw({"type": "http", "method": "POST", "path": "/login", "headers": []}, receive, send))
    assert sent[0]["status"] == 200


# ---------------------------------------------------------- confirmação de senha para ações de privilégio de admin
def test_creating_an_admin_requires_the_caller_own_password(client, db):
    r = client.post("/admin/users", {"username": "novoadm", "role": "admin", "confirm_password": "senha-errada"})
    assert r.status_code == 303
    assert not db.query(User).filter_by(username="novoadm").first()
    assert "Senha incorreta" in client.get("/admin/users").text
    r = client.post("/admin/users", {"username": "novoadm", "role": "admin", "confirm_password": "admin-pass-123"})
    assert r.status_code == 200 and "Senha provisória" in r.text
    assert db.query(User).filter_by(username="novoadm", role="admin").one()


def test_promoting_to_admin_requires_the_caller_own_password(client, db):
    _create_user(client, "func9", "operator")
    target = db.query(User).filter_by(username="func9").one()
    bad = client.post(f"/admin/users/{target.id}/role", {"role": "admin", "confirm_password": "errada"})
    assert bad.status_code == 303
    db.expire_all()
    assert db.get(User, target.id).role == "operator"
    ok = client.post(f"/admin/users/{target.id}/role", {"role": "admin", "confirm_password": "admin-pass-123"})
    assert ok.status_code == 303
    db.expire_all()
    assert db.get(User, target.id).role == "admin"


def test_demoting_or_regular_role_change_does_not_need_password(client, db):
    _create_user(client, "func10", "operator")
    target = db.query(User).filter_by(username="func10").one()
    assert client.post(f"/admin/users/{target.id}/role", {"role": "director"}).status_code == 303
    db.expire_all()
    assert db.get(User, target.id).role == "director"


def test_removing_another_admin_2fa_requires_the_caller_own_password(client, db):
    admin2 = _user(client, "admin2", "admin")
    admin2.get("/account/2fa")
    db.expire_all()
    other = db.query(User).filter_by(username="admin2").one()
    code = totp_service.code_at(totp_service.current_secret(other))
    assert admin2.post("/account/2fa/enable", {"code": code}).status_code == 200
    db.expire_all()
    assert db.query(User).filter_by(username="admin2").one().has_2fa

    bad = client.post(f"/admin/users/{other.id}/reset-2fa", {"confirm_password": "errada"})
    assert bad.status_code == 303
    db.expire_all()
    assert db.get(User, other.id).has_2fa

    ok = client.post(f"/admin/users/{other.id}/reset-2fa", {"confirm_password": "admin-pass-123"})
    assert ok.status_code == 303
    db.expire_all()
    assert not db.get(User, other.id).has_2fa


def test_resetting_2fa_of_a_demoted_former_admin_does_not_need_password(client, db):
    """A checagem olha o PERFIL ATUAL do alvo: um ex-admin rebaixado, mas que ainda tem 2FA ativo (role change não
    desliga o 2FA sozinho), não é mais "outro administrador" — continua sendo um 2FA comum de remover."""
    admin3 = _user(client, "admin3", "admin")
    admin3.get("/account/2fa")
    db.expire_all()
    target = db.query(User).filter_by(username="admin3").one()
    code = totp_service.code_at(totp_service.current_secret(target))
    assert admin3.post("/account/2fa/enable", {"code": code}).status_code == 200
    db.expire_all()
    target = db.query(User).filter_by(username="admin3").one()
    assert target.has_2fa
    assert client.post(f"/admin/users/{target.id}/role", {"role": "operator"}).status_code == 303
    db.expire_all()
    target = db.query(User).filter_by(username="admin3").one()
    assert target.role == "operator" and target.has_2fa          # ainda tem 2FA, mas não é mais admin
    assert client.post(f"/admin/users/{target.id}/reset-2fa", {}).status_code == 303
    db.expire_all()
    assert not db.get(User, target.id).has_2fa


# ---------------------------------------------------------- conta inativa não some do bloqueio/tempo
def test_inactive_account_still_locks_after_n_wrong_attempts(client, db):
    """Antes, conta inativa nunca mostrava 'bloqueado' (o incremento era pulado): dava para distinguir por
    comportamento quais contas foram desativadas."""
    _create_user(client, "exfunc", "operator")
    target = db.query(User).filter_by(username="exfunc").one()
    target.active, target.must_change_password = False, False
    db.commit()
    c = _new_client()
    last = None
    for _i in range(6):
        last = _login(c, "exfunc", "errada")
    assert "bloqueado" in last.text.lower()


# ---------------------------------------------------------- reativar limpa bloqueio acumulado enquanto estava inativa
def test_reactivating_a_user_clears_stale_lockout(client, db):
    _create_user(client, "reat1", "operator")
    target = db.query(User).filter_by(username="reat1").one()
    target.active = False
    db.commit()
    c = _new_client()
    for _i in range(6):
        _login(c, "reat1", "errada")
    db.expire_all()
    t = db.get(User, target.id)
    assert t.blocked_until is not None or t.failed_attempts
    assert client.post(f"/admin/users/{target.id}/toggle", {}).status_code == 303   # reativa (estava inativo)
    db.expire_all()
    t = db.get(User, target.id)
    assert t.active and t.blocked_until is None and not t.failed_attempts


# ---------------------------------------------------------- nome de usuário duplicado só por caixa
def test_username_uniqueness_is_case_insensitive(client, db):
    _create_user(client, "Func12", "operator")
    r = client.post("/admin/users", {"username": "func12", "role": "operator"})
    assert r.status_code == 303
    assert "já existe" in client.get("/admin/users").text
    assert db.query(User).filter(User.username.in_(["Func12", "func12"])).count() == 1


# ---------------------------------------------------------- HTML injection via código da loja (sink no JS)
def test_store_code_is_escaped_in_director_js_sinks():
    js = open("app/static/js/director.js", encoding="utf-8").read()
    assert "esc(r.code)" in js and "esc(a.code)" in js and "esc(b.code)" in js


# ---------------------------------------------------------- filename com acento não derruba o download
def test_document_filename_with_accents_does_not_crash_the_download(client, db, png):
    _make_store(client)
    _upload(client, png)
    doc = db.query(Document).order_by(Document.id.desc()).first()
    doc.filename = "conta de luz – março.png"
    db.commit()
    r = client.get(f"/documents/{doc.id}")
    assert r.status_code == 200
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
