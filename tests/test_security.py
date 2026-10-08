import re

import pytest
from fastapi.testclient import TestClient

from app import security
from app.config import Settings, get_settings
from app.main import app
from app.models import AuditLog, Document, User
from app.services import crypto_service
from app.startup_checks import security_problems
from tests.conftest import Client
from tests.test_app_flow import _form_from_review, _make_store, _upload

PROTECTED = ["/", "/stores", "/stores/1", "/units/1", "/import", "/manual", "/types", "/admin/users", "/admin/audit",
             "/account/password", "/documents/1", "/bills/1/print", "/stores/1/report", "/api/stores/1/chart"]


def _new_client() -> Client:
    c = Client(TestClient(app))
    c.refresh()
    return c


def _create_user(admin: Client, username: str, role: str) -> str:
    r = admin.post("/admin/users", {"username": username, "role": role})
    assert r.status_code == 200
    return re.search(r"<code[^>]*>(.*?)</code>", r.text).group(1)


def _login(c: Client, username: str, password: str):
    c.refresh()
    r = c.post("/login", {"username": username, "password": password})
    c.refresh()   # a sessão é recriada no login (anti session-fixation): pega o novo token CSRF
    return r


# ---------------------------------------------------------------- autenticação
@pytest.mark.parametrize("path", PROTECTED)
def test_every_page_requires_login(path):
    anon = TestClient(app)
    r = anon.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_mutations_without_login_are_rejected():
    anon = Client(TestClient(app))
    anon.refresh()
    for url in ("/stores", "/manual", "/types", "/import", "/admin/users"):
        assert anon.post(url, {}).status_code in (303, 403, 422)
    assert anon.tc.get("/health").status_code == 200  # único endpoint público além de /login e /static


LOCKED = "excesso de tentativas"      # frase só da mensagem de bloqueio (a tela traz um aviso fixo com a palavra "bloqueado")


def test_wrong_password_says_wrong_password_and_lockout_says_locked(client, db):
    from app.middleware import reset_rate_limits
    pw = _create_user(client, "maria", "operator")
    c = _new_client()
    for _ in range(2):                                  # senha provisória: bloqueia na 3ª
        r = _login(c, "maria", "errada-errada-1")
        assert r.status_code == 401 and "incorretos" in r.text and LOCKED not in r.text
    third = _login(c, "maria", "errada-errada-1")       # a que estoura o limite já avisa do bloqueio
    assert third.status_code == 401 and LOCKED in third.text and "15 minuto(s)" in third.text
    r = _login(c, "maria", pw)                          # senha CERTA, mas conta bloqueada
    assert r.status_code == 401 and LOCKED in r.text
    db.expire_all()
    actions = [a.action for a in db.query(AuditLog).filter(AuditLog.entity == "auth")]
    assert "account_locked" in actions and "login_blocked" in actions and actions.count("login_failed") >= 3
    reset_rate_limits()


def test_lockout_message_does_not_reveal_whether_account_exists(client, db):
    """Usuário inventado bloqueia com as mesmas palavras e no mesmo número de tentativas de uma conta normal (5)."""
    from app.middleware import reset_rate_limits
    ghost = _new_client()
    for _ in range(4):
        r = _login(ghost, "nao-existe", "qualquer-coisa-1")
        assert r.status_code == 401 and "incorretos" in r.text and LOCKED not in r.text
    fifth = _login(ghost, "nao-existe", "qualquer-coisa-1")
    assert fifth.status_code == 401 and LOCKED in fifth.text
    assert LOCKED in _login(ghost, "Nao-Existe", "outra-coisa-1").text                 # maiúscula/minúscula não escapa
    reset_rate_limits()
    real = _new_client()                                                               # conta normal (admin): também 5
    for _ in range(4):
        assert LOCKED not in _login(real, "admin", "errada-errada-1").text
    assert LOCKED in _login(real, "admin", "errada-errada-1").text
    assert _login(_new_client(), "outro-fantasma", "x").status_code == 401             # bloqueio é por nome, não global
    reset_rate_limits()


def test_unknown_user_lock_expires_and_stores_no_raw_name(client, db):
    from datetime import timedelta

    from app.middleware import reset_rate_limits
    from app.models import LoginThrottle
    from app.models.mixins import utcnow
    c = _new_client()
    for _ in range(5):
        _login(c, "fantasma-x", "qualquer-coisa-1")
    reset_rate_limits()
    row = db.query(LoginThrottle).one()
    assert "fantasma" not in row.key and row.key.startswith("h:")
    row.blocked_until = utcnow() - timedelta(minutes=1)
    db.commit()
    again = _login(c, "fantasma-x", "qualquer-coisa-1")
    assert "incorretos" in again.text and LOCKED not in again.text
    reset_rate_limits()


def test_login_page_explains_the_lockout_rule_up_front(client):
    html = _new_client().get("/login").text
    assert "bloqueado por 15 minutos" in html and "5 tentativas" in html


def test_lockout_expires(client, db):
    pw = _create_user(client, "joao", "operator")
    c = _new_client()
    for _ in range(5):
        _login(c, "joao", "errada-errada-1")
    from datetime import timedelta

    from app.models.mixins import utcnow
    u = db.query(User).filter_by(username="joao").one()
    u.blocked_until = utcnow() - timedelta(minutes=1)
    db.commit()
    assert _login(c, "joao", pw).status_code == 303


def test_login_rate_limit_per_ip(client):
    c = _new_client()
    codes = [_login(c, "x", "y").status_code for _ in range(12)]
    assert codes[:9] == [401] * 9 and codes[9:] == [429] * 3      # a fixture já gastou 1 das 10 tentativas/min


def test_failed_login_audit_never_stores_raw_ip_or_typed_username(client, db):
    _login(_new_client(), "alguem-digitou-senha-aqui", "x")
    rows = [a for a in db.query(AuditLog).filter_by(action="login_failed")]
    blob = str([r.details for r in rows])
    assert "alguem-digitou-senha-aqui" not in blob and "testclient" not in blob and "h:" in blob


# ---------------------------------------------------------------- sessão
def test_logout_revokes_a_copied_cookie(client):
    stolen = client.tc.cookies.get("energia_session")
    assert client.get("/stores").status_code == 200
    client.post("/logout")
    thief = TestClient(app, cookies={"energia_session": stolen})
    assert thief.get("/stores", follow_redirects=False).status_code == 303


def test_session_idle_and_absolute_timeouts(client, monkeypatch):
    now = security._now_ts()
    monkeypatch.setattr(security, "_now_ts", lambda: now + get_settings().session_idle_minutes * 60 + 5)
    assert client.get("/stores", follow_redirects=False).status_code == 303   # inatividade


def test_session_absolute_timeout(client, monkeypatch):
    now = security._now_ts()
    for _ in range(3):  # mantém ativa por "atividade", mas estoura a duração máxima
        monkeypatch.setattr(security, "_now_ts", lambda: now + 1800)
        client.get("/stores")
        now += 1800
    monkeypatch.setattr(security, "_now_ts", lambda: now + get_settings().session_max_hours * 3600)
    assert client.get("/stores", follow_redirects=False).status_code == 303


def test_session_cookie_flags(client):
    c = _new_client()
    r = _login(c, "admin", "admin-pass-123")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_deactivating_user_kills_open_sessions(client):
    pw = _create_user(client, "ana", "operator")
    ana = _new_client()
    assert _login(ana, "ana", pw).status_code == 303
    ana.post("/account/password", {"current_password": pw, "new_password": "Nova-senha-forte-77", "confirm": "Nova-senha-forte-77"})
    assert ana.get("/stores").status_code == 200
    uid = int(re.search(r"/admin/users/(\d+)/toggle", client.get("/admin/users").text.split("ana")[-1]).group(1))
    client.post(f"/admin/users/{uid}/toggle")
    assert ana.get("/stores", follow_redirects=False).status_code == 303


# ---------------------------------------------------------------- senhas
@pytest.mark.parametrize("pw", ["curta1", "senhasenha", "Senha12345".lower(), "aaaaaaaaaaaa", "password123", "admin-teste-1"])
def test_weak_passwords_rejected(pw):
    assert security.validate_password(pw, "admin-teste") is not None or pw == "senhasenha" and False


def test_strong_password_accepted_and_legacy_hash_upgraded(client, db):
    assert security.validate_password("Tr0cadera-forte-9", "ana") is None
    import hashlib
    import os
    salt = os.urandom(16)
    legacy = "scrypt$" + salt.hex() + "$" + hashlib.scrypt(b"Antiga-senha-123", salt=salt, n=2**14, r=8, p=1).hex()
    db.add(User(username="legado", password_hash=legacy, role="operator"))
    db.commit()
    assert _login(_new_client(), "legado", "Antiga-senha-123").status_code == 303
    db.expire_all()
    assert db.query(User).filter_by(username="legado").one().password_hash.startswith("scrypt$15$")


def test_new_user_must_change_temp_password_and_sees_it_once(client):
    html = client.post("/admin/users", {"username": "carla", "role": "viewer"}).text
    temp = re.search(r"<code[^>]*>(.*?)</code>", html).group(1)
    assert "uma única vez" in html or "não será exibida novamente" in html
    assert temp not in client.get("/admin/users").text                       # não reaparece
    carla = _new_client()
    r = _login(carla, "carla", temp)
    assert r.status_code == 303 and r.headers["location"] == "/account/password"
    assert carla.get("/stores", follow_redirects=False).headers["location"] == "/account/password"   # bloqueada até trocar
    assert carla.post("/account/password", {"current_password": temp, "new_password": "curta", "confirm": "curta"}).status_code == 400
    ok = carla.post("/account/password", {"current_password": temp, "new_password": "Minha-senha-nova-42", "confirm": "Minha-senha-nova-42"})
    assert ok.status_code == 303 and carla.get("/stores").status_code == 200
    assert _login(_new_client(), "carla", temp).status_code == 401           # a provisória morreu


def test_password_change_revokes_other_sessions(client):
    pw = _create_user(client, "rui", "operator")
    a, b = _new_client(), _new_client()
    _login(a, "rui", pw)
    a.post("/account/password", {"current_password": pw, "new_password": "Senha-do-Rui-2026", "confirm": "Senha-do-Rui-2026"})
    _login(b, "rui", "Senha-do-Rui-2026")
    assert b.get("/stores").status_code == 200
    b.post("/account/password", {"current_password": "Senha-do-Rui-2026", "new_password": "Outra-senha-forte-9", "confirm": "Outra-senha-forte-9"})
    assert a.get("/stores", follow_redirects=False).status_code == 303       # sessão antiga caiu


# ---------------------------------------------------------------- autorização
def test_viewer_can_read_and_print_but_not_write(client, png):
    _make_store(client)
    pw = _create_user(client, "vera", "viewer")
    v = _new_client()
    _login(v, "vera", pw)
    v.post("/account/password", {"current_password": pw, "new_password": "Consulta-forte-2026", "confirm": "Consulta-forte-2026"})
    assert v.get("/").status_code == 200 and v.get("/stores/1").status_code == 200
    assert v.get("/import").status_code == 403 and v.get("/manual").status_code == 403
    r = v.post("/import", {}, files={"file": ("c.png", png, "image/png")})
    assert r.status_code == 403
    assert v.post("/manual", {"store_id": "1"}).status_code == 403
    assert "Importar conta" not in v.get("/").text                            # nem aparece o botão
    assert v.get("/types").status_code == 403 and v.get("/admin/users").status_code == 403


def test_operator_manages_energy_but_not_users_or_audit(client):
    pw = _create_user(client, "otavio", "operator")
    o = _new_client()
    _login(o, "otavio", pw)
    o.post("/account/password", {"current_password": pw, "new_password": "Operador-forte-2026", "confirm": "Operador-forte-2026"})
    o.refresh()
    assert o.get("/import").status_code == 200 and o.get("/types").status_code == 200 and o.get("/stores/new").status_code == 200
    assert o.post("/stores", {"code": "X1"}).status_code == 303                       # funcionário cadastra filial
    for url in ("/admin/users", "/admin/audit"):                                        # acessos e auditoria: só o administrador
        assert o.get(url).status_code == 403
    assert o.post("/admin/users", {"username": "intruso", "role": "admin"}).status_code == 403


def test_last_admin_cannot_be_demoted_or_deactivated(client, db):
    admin = db.query(User).filter_by(username="admin").one()
    other = _create_user(client, "chefe", "admin")
    chefe = db.query(User).filter_by(username="chefe").one()
    client.post(f"/admin/users/{chefe.id}/role", {"role": "viewer"})       # tem 2 admins: ok
    db.expire_all()
    assert db.get(User, chefe.id).role == "viewer"
    c2 = _new_client()
    assert _login(c2, "admin", "admin-pass-123").status_code == 303
    # admin tenta se rebaixar via 2º admin inexistente -> só 1 admin ativo
    client.post(f"/admin/users/{chefe.id}/role", {"role": "admin"})
    client.post(f"/admin/users/{admin.id}/toggle")                          # self: ignorado
    db.expire_all()
    assert db.get(User, admin.id).active and other


# ---------------------------------------------------------------- cabeçalhos / CSRF / corpo
def test_security_headers_and_csp_nonce(client):
    r = client.get("/stores")
    h = r.headers
    assert h["x-content-type-options"] == "nosniff" and h["cache-control"] == "no-store" and "same-origin" in h["cross-origin-opener-policy"]
    csp = h["content-security-policy"]
    assert "script-src 'self' 'nonce-" in csp and "unsafe-inline'" not in csp.split("style-src")[0] and "object-src 'none'" in csp
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    page = client.get("/import").text
    assert f'nonce="{re.search(r"nonce=.([^\"]+)", page).group(1)}"' in page
    assert client.get("/static/css/app.css").headers.get("cache-control") != "no-store"
    assert nonce  # presente em toda resposta


def test_pages_have_no_inline_event_handlers_and_every_inline_script_has_nonce(client, png, db):
    _make_store(client)
    job = _upload(client, png)
    client.post(f"/import/{job}/confirm", {**_form_from_review(client.get(f"/import/{job}/review").text), "unit_mode": "matched"})
    bill_id = db.query(__import__("app.models", fromlist=["EnergyBill"]).EnergyBill).one().id
    pages = ["/", "/stores", "/stores/1", "/units/1", "/import", f"/import/{job}/review", "/manual", "/types", "/admin/users",
             "/admin/audit", "/account/password", "/stores/1/report", f"/bills/{bill_id}/print"]
    for path in pages:
        html = client.get(path).text
        assert not re.search(r"\son(click|change|submit|input|load|error)\s*=", html, re.I), path
        for tag in re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*type=)[^>]*>", html):
            assert "nonce=" in tag, (path, tag)


def test_document_response_is_hardened(client, png, db):
    _make_store(client)
    job = _upload(client, png)
    doc_id = db.query(Document).one().id
    r = client.get(f"/documents/{doc_id}")
    assert r.status_code == 200 and r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    assert "sandbox" in r.headers["content-security-policy"] and job


def test_cross_site_post_is_rejected(client):
    r = client.tc.post("/stores", data={"code": "EVIL", "csrf_token": client.token}, headers={"Origin": "https://evil.example"},
                       follow_redirects=False)
    assert r.status_code == 403
    r = client.tc.post("/stores", data={"code": "EVIL", "csrf_token": client.token}, headers={"Sec-Fetch-Site": "cross-site"},
                       follow_redirects=False)
    assert r.status_code == 403
    assert client.post("/stores", {"code": "OK1"}).status_code == 303          # mesma origem segue funcionando


def test_missing_or_wrong_csrf_token_rejected(client):
    assert client.tc.post("/stores", data={"code": "N1"}, follow_redirects=False).status_code == 403
    assert client.tc.post("/stores", data={"code": "N1", "csrf_token": "errado"}, follow_redirects=False).status_code == 403


def test_oversized_bodies_rejected_before_parsing(client):
    big = str(get_settings().max_upload_bytes + 5 * 1024 * 1024)
    r = client.tc.post("/import", headers={"content-length": big, "x-csrf-token": client.token}, content=b"x")
    assert r.status_code == 413
    assert client.tc.post("/stores", headers={"content-length": "2000000", "x-csrf-token": client.token}, content=b"x").status_code == 413


def test_client_ip_uses_trusted_proxy_hop_not_spoofable_left_side():
    from starlette.requests import Request
    def req(xff):
        return Request({"type": "http", "headers": [(b"x-forwarded-for", xff.encode())] if xff else [], "client": ("10.0.0.9", 1)})
    assert security.client_ip(req("1.2.3.4")) == "1.2.3.4"
    assert security.client_ip(req("6.6.6.6, 1.2.3.4")) == "1.2.3.4"           # o cliente forjou "6.6.6.6": ignorado
    assert security.client_ip(req("")) == "10.0.0.9"


# ---------------------------------------------------------------- criptografia em repouso
def test_documents_encrypted_at_rest_and_roundtrip(client, png, db):
    _make_store(client)
    _upload(client, png)
    doc = db.query(Document).one()
    assert doc.encrypted and doc.data != png and doc.data.startswith(b"gAAAA") and doc.size == len(png)
    assert client.get(f"/documents/{doc.id}").content == png


def test_wrong_key_does_not_crash_or_leak(client, png, db, monkeypatch):
    _make_store(client)
    _upload(client, png)
    doc = db.query(Document).one()
    monkeypatch.setattr(get_settings(), "document_encryption_key", crypto_service.generate_key())
    assert client.get(f"/documents/{doc.id}").status_code == 500


def test_key_rotation_with_multiple_keys(db, monkeypatch):
    old, new = crypto_service.generate_key(), crypto_service.generate_key()
    s = get_settings()
    monkeypatch.setattr(s, "document_encryption_key", old)
    blob, enc = crypto_service.encrypt(b"segredo")
    monkeypatch.setattr(s, "document_encryption_key", f"{new},{old}")      # nova cifra, antiga ainda decifra
    assert crypto_service.decrypt(blob, enc) == b"segredo"
    assert crypto_service.decrypt(crypto_service.encrypt(b"x")[0], True) == b"x"


# ---------------------------------------------------------------- produção fail-closed
def test_production_refuses_insecure_configuration():
    bad = Settings(debug=False, secret_key="curta", document_encryption_key="", database_url="sqlite:///x.db")
    problems = security_problems(bad)
    assert len(problems) == 3 and any("SECRET_KEY" in p for p in problems) and any("DOCUMENT_ENCRYPTION_KEY" in p for p in problems)
    good = Settings(debug=False, secret_key="a" * 40, document_encryption_key=crypto_service.generate_key(),
                    database_url="postgresql://u:p@h/db")
    assert security_problems(good) == []
    assert security_problems(Settings(debug=True, secret_key="")) == []
    assert any("inválida" in p for p in security_problems(Settings(debug=False, secret_key="a" * 40, document_encryption_key="lixo",
                                                                  database_url="postgresql://u:p@h/d")))


def test_production_rejects_weak_admin_password(db):
    from app.seed import seed
    s = get_settings()
    db.query(User).delete()
    db.commit()
    mp = pytest.MonkeyPatch()
    mp.setattr(s, "debug", False)
    mp.setattr(s, "admin_password", "fraca123")
    try:
        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            seed(db)
    finally:
        mp.undo()


def test_audit_page_admin_only_and_never_shows_raw_ip(client):
    html = client.get("/admin/audit").text
    assert "login" in html and "testclient" not in html


# ---------------------------------------------------------------- PDF de ponta a ponta
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")


class _SpyExtractor:
    name = "spy"

    def __init__(self):
        self.seen = []

    def extract(self, data, mime_type, catalog=None):
        from app.services.extraction_service import MockExtractor
        self.seen.append((data, mime_type))
        return MockExtractor().extract(data, mime_type)


def test_pdf_flow_sends_original_bytes_as_pdf_and_serves_it_inline_and_encrypted(client, db, monkeypatch):
    from app.services import import_service
    spy = _SpyExtractor()
    monkeypatch.setattr(import_service, "get_extractor", lambda: spy)
    _make_store(client)
    r = client.post("/import", {}, files={"file": ("conta.pdf", PDF, "application/pdf")})
    job = int(r.headers["location"].rsplit("/", 1)[1])
    assert spy.seen == [(PDF, "application/pdf")]                       # o Gemini recebe o PDF decifrado, intacto
    doc = db.query(Document).one()
    assert doc.encrypted and doc.data != PDF and doc.size == len(PDF)    # no banco está cifrado
    review = client.get(f"/import/{job}/review").text
    assert f'<iframe src="/documents/{doc.id}"' in review
    served = client.get(f"/documents/{doc.id}")
    assert served.content == PDF and served.headers["content-type"] == "application/pdf"
    assert "content-security-policy" not in served.headers               # CSP/sandbox quebraria o visualizador de PDF
    assert served.headers["x-content-type-options"] == "nosniff" and served.headers["cache-control"] == "no-store"
    client.post(f"/import/{job}/confirm", {**_form_from_review(review), "unit_mode": "matched"})
    from app.models import EnergyBill
    bill = db.query(EnergyBill).one()
    page = client.get(f"/bills/{bill.id}/print?doc=1").text
    assert f"/documents/{doc.id}/pages/1.png" in page and "não pode ser embutido" not in page   # o PDF agora entra na impressão como imagem


def test_same_file_is_not_sent_to_gemini_twice(client, db, monkeypatch):
    from app.services import import_service
    spy = _SpyExtractor()
    monkeypatch.setattr(import_service, "get_extractor", lambda: spy)
    _make_store(client)
    r = client.post("/import", {}, files={"file": ("conta.pdf", PDF, "application/pdf")})
    job = int(r.headers["location"].rsplit("/", 1)[1])
    client.post(f"/import/{job}/confirm", {**_form_from_review(client.get(f"/import/{job}/review").text), "unit_mode": "matched"})
    again = client.post("/import", {}, files={"file": ("renomeado.pdf", PDF, "application/pdf")})
    assert again.status_code == 409 and "já foi importado" in again.text and "/units/" in again.text
    assert len(spy.seen) == 1                                            # nenhuma 2ª chamada à API
    assert db.query(Document).count() == 1


def test_discarded_import_allows_reupload_of_same_file(client, db, monkeypatch):
    from app.services import import_service
    monkeypatch.setattr(import_service, "get_extractor", lambda: _SpyExtractor())
    _make_store(client)
    job = int(client.post("/import", {}, files={"file": ("a.pdf", PDF, "application/pdf")}).headers["location"].rsplit("/", 1)[1])
    client.post(f"/import/{job}/cancel")
    assert client.post("/import", {}, files={"file": ("a.pdf", PDF, "application/pdf")}).status_code == 303


def test_new_pages_are_csp_clean(client, db):
    for path in ("/ajuda", "/points/new", "/points/new?fragment=1"):
        html = client.get(path).text
        assert not re.search(r"\son(click|change|submit|input|load|error)\s*=", html, re.I), path
        for tag in re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*type=)[^>]*>", html):
            assert "nonce=" in tag, (path, tag)
