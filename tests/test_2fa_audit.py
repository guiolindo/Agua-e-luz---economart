"""2FA (TOTP) do administrador e cadeia de integridade da auditoria."""
import re
import time

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.models import AuditLog, User
from app.services import audit_service, totp_service
from tests.conftest import PNG as PNG_BYTES, Client
from tests.test_security import _create_user, _login, _new_client


def _admin(db):
    return db.query(User).filter_by(username="admin").one()


def _enable_2fa(client: Client, db):
    """Ativa o 2FA do admin logado pelas rotas reais; devolve (segredo, códigos de recuperação)."""
    page = client.get("/account/2fa").text
    assert "<svg" in page
    db.expire_all()
    secret = totp_service.current_secret(_admin(db))
    r = client.post("/account/2fa/enable", {"code": totp_service.code_at(secret)})
    assert r.status_code == 200
    client.refresh()
    codes = re.findall(r"\b[0-9a-f]{4}-[0-9a-f]{4}\b", r.text)
    assert len(codes) == 8
    return secret, codes


def _2fa(c: Client, code: str):
    assert c.get("/login/2fa").status_code == 200      # a página gera o token CSRF da sessão pendente
    c.refresh()
    return c.post("/login/2fa", {"code": code})


def _next_code(secret: str) -> str:
    """Código da PRÓXIMA janela (o da atual pode já ter sido gasto na ativação)."""
    return totp_service.code_at(secret, time.time() + 30)


def test_totp_matches_rfc6238_vector():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"     # "12345678901234567890"
    assert totp_service.code_at(secret, 59) == "287082"
    assert totp_service.code_at(secret, 1111111109) == "081804"


def test_enable_2fa_rejects_wrong_code_and_stores_secret_encrypted(client, db):
    client.get("/account/2fa")
    assert client.post("/account/2fa/enable", {"code": "000000"}).status_code == 400
    db.expire_all()
    assert not _admin(db).has_2fa
    secret, _ = _enable_2fa(client, db)
    db.expire_all()
    u = _admin(db)
    assert u.has_2fa and u.totp_secret.startswith("enc:") and secret not in u.totp_secret
    assert all(len(h) == 64 for h in u.totp_recovery)           # só hashes, nunca os códigos


def test_admin_login_needs_authenticator_code(client, db):
    secret, _ = _enable_2fa(client, db)
    c = _new_client()
    r = _login(c, "admin", "admin-pass-123")
    assert r.status_code == 303 and r.headers["location"] == "/login/2fa"
    bad = _2fa(c, "123456")
    assert bad.status_code == 401
    assert c.get("/stores", follow_redirects=False).status_code == 303          # ainda sem sessão
    c = _new_client()
    _login(c, "admin", "admin-pass-123")
    ok = _2fa(c, _next_code(secret))
    assert ok.status_code == 303 and ok.headers["location"] == "/"
    assert c.get("/stores", follow_redirects=False).status_code == 200


def test_code_cannot_be_replayed(client, db):
    secret, _ = _enable_2fa(client, db)
    code = _next_code(secret)
    c1 = _new_client()
    _login(c1, "admin", "admin-pass-123")
    assert _2fa(c1, code).status_code == 303
    c2 = _new_client()
    _login(c2, "admin", "admin-pass-123")
    assert _2fa(c2, code).status_code == 401


def test_recovery_code_works_once(client, db):
    _, codes = _enable_2fa(client, db)
    c = _new_client()
    _login(c, "admin", "admin-pass-123")
    assert _2fa(c, codes[0]).status_code == 303
    c2 = _new_client()
    _login(c2, "admin", "admin-pass-123")
    assert _2fa(c2, codes[0]).status_code == 401
    db.expire_all()
    assert len(_admin(db).totp_recovery) == 7


def test_wrong_codes_lock_the_account_even_with_new_password_logins(client, db):
    _enable_2fa(client, db)
    for _ in range(get_settings().max_login_attempts):
        c = _new_client()
        _login(c, "admin", "admin-pass-123")          # a senha certa não zera o contador
        _2fa(c, "111111")
    c = _new_client()
    r = _login(c, "admin", "admin-pass-123")
    assert r.status_code == 401 and "bloqueado" in r.text.lower()


def test_pre2fa_session_expires(client, db, monkeypatch):
    from app import security
    _enable_2fa(client, db)
    c = _new_client()
    _login(c, "admin", "admin-pass-123")
    now = security._now_ts()
    monkeypatch.setattr(security, "_now_ts", lambda: now + 400)
    assert c.get("/login/2fa", follow_redirects=False).headers["location"] == "/login"


def test_only_admin_sees_2fa_and_non_admin_login_unchanged(client, db):
    pin = _create_user(client, "func", "operator")
    c = _new_client()
    assert _login(c, "func", pin).headers["location"] == "/account/password"
    db.query(User).filter_by(username="func").one().must_change_password = False
    db.commit()
    assert c.get("/account/2fa", follow_redirects=False).status_code == 403


def test_require_admin_2fa_forces_setup(client, db):
    s = get_settings()
    s.require_admin_2fa = True
    try:
        r = client.get("/stores", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/account/2fa"
        assert client.get("/account/2fa").status_code == 200
        _enable_2fa(client, db)
        assert client.get("/stores", follow_redirects=False).status_code == 200
    finally:
        s.require_admin_2fa = False


def test_another_admin_can_reset_2fa(client, db):
    _enable_2fa(client, db)
    pin = _create_user(client, "admin2", "admin")
    c2 = _new_client()
    _login(c2, "admin2", pin)
    c2.post("/account/password", {"current_password": pin, "new_password": "Segunda-senha-9", "confirm": "Segunda-senha-9"})
    c2.refresh()
    target = _admin(db).id
    assert c2.post(f"/admin/users/{target}/reset-2fa", {"confirm_password": "Segunda-senha-9"}).status_code == 303
    db.expire_all()
    assert not _admin(db).has_2fa
    assert db.query(AuditLog).filter_by(action="2fa_reset").count() == 1


def test_disable_requires_password_and_code(client, db):
    secret, codes = _enable_2fa(client, db)
    assert client.post("/account/2fa/disable", {"password": "errada", "code": codes[0]}).status_code == 400
    r = client.post("/account/2fa/disable", {"password": "admin-pass-123", "code": codes[0]})
    assert r.status_code == 303
    db.expire_all()
    assert not _admin(db).has_2fa


# ---------------------------------------------------------------- auditoria à prova de adulteração
def _log(db, n):
    for i in range(n):
        audit_service.log(db, None, "create", "store", i, {"i": i, "nome": f"loja {i}"})
    db.commit()


def test_audit_events_are_chained_even_in_one_flush(db):
    _log(db, 5)
    rows = db.query(AuditLog).order_by(AuditLog.id).all()
    assert all(r.row_hash for r in rows)
    assert rows[0].prev_hash == "" or rows[0].prev_hash == rows[0].prev_hash
    for a, b in zip(rows, rows[1:]):
        assert b.prev_hash == a.row_hash
    rep = audit_service.verify_chain(db)
    assert rep.ok and rep.protected == len(rows) and rep.head == rows[-1].row_hash


def test_editing_an_event_is_detected(db):
    _log(db, 4)
    ids = [r.id for r in db.query(AuditLog).order_by(AuditLog.id)]
    db.execute(text("UPDATE audit_log SET action='delete' WHERE id=:i"), {"i": ids[1]})
    db.commit()
    rep = audit_service.verify_chain(db)
    assert not rep.ok and rep.broken_id == ids[1] and "alterado" in rep.reason


def test_deleting_a_middle_event_is_detected(db):
    _log(db, 4)
    ids = [r.id for r in db.query(AuditLog).order_by(AuditLog.id)]
    db.execute(text("DELETE FROM audit_log WHERE id=:i"), {"i": ids[1]})
    db.commit()
    rep = audit_service.verify_chain(db)
    assert not rep.ok and rep.broken_id == ids[2]


def test_injected_unsealed_event_is_detected(db):
    _log(db, 2)
    db.execute(text("INSERT INTO audit_log (at, action, entity) VALUES (CURRENT_TIMESTAMP, 'forjado', 'x')"))
    db.commit()
    assert not audit_service.verify_chain(db).ok


def test_legacy_events_before_protection_are_tolerated(db):
    db.execute(text("INSERT INTO audit_log (at, action, entity) VALUES (CURRENT_TIMESTAMP, 'antigo', 'x')"))
    db.commit()
    _log(db, 2)
    rep = audit_service.verify_chain(db)
    assert rep.ok and rep.legacy == 1 and rep.protected == 2


def test_audit_page_verify_button(client, db):
    html = client.post("/admin/audit/verify").text
    assert "Auditoria íntegra" in html
    db.execute(text("UPDATE audit_log SET action='x' WHERE id=(SELECT MIN(id) FROM audit_log)"))
    db.commit()
    assert "Adulteração detectada" in client.post("/admin/audit/verify").text


# ---------------------------------------------------------------- disjuntor do Gemini
def test_circuit_breaker_opens_after_failures_and_recovers():
    from app.services.circuit_breaker import BreakerOpen, CircuitBreaker
    t = [0.0]
    b = CircuitBreaker("x", failure_threshold=2, reset_seconds=30, clock=lambda: t[0])

    def boom():
        with b.call():
            raise ValueError

    for _ in range(2):
        with pytest.raises(ValueError):
            boom()
    with pytest.raises(BreakerOpen):
        with b.call():
            pass
    t[0] = 31                                   # meio-aberto: uma chamada de teste
    with b.call():
        pass
    with b.call():                              # sucesso fechou
        pass


def test_breaker_ignores_caller_errors():
    from app.services.circuit_breaker import CircuitBreaker
    b = CircuitBreaker("y", failure_threshold=1)
    for _ in range(3):
        with pytest.raises(KeyError):
            with b.call(counts=lambda e: False):
                raise KeyError
    with b.call():
        pass


def test_gemini_service_fast_fails_when_breaker_open(monkeypatch):
    from app.services import gemini_service
    from app.services.circuit_breaker import gemini_breaker
    from google import genai
    from google.genai import errors

    class FakeModels:
        calls = 0

        def generate_content(self, **kw):
            FakeModels.calls += 1
            raise errors.APIError(503, {"error": {"message": "x"}})

    class FakeClient:
        def __init__(self, **kw):
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    gemini_breaker.reset()
    svc = gemini_service.GeminiService(api_key="k", sleep=lambda s: None)
    try:
        for _ in range(gemini_breaker.failure_threshold):
            with pytest.raises(gemini_service.ExtractionError):
                svc.extract(PNG_BYTES, "image/png")
        before = FakeModels.calls
        with pytest.raises(gemini_service.ExtractionError, match="instável"):
            svc.extract(PNG_BYTES, "image/png")
        assert FakeModels.calls == before            # rejeitou sem chamar o Google
    finally:
        gemini_breaker.reset()


def test_audit_page_uses_readable_labels(client):
    html = client.get("/admin/audit").text
    assert "Entrou no sistema" in html and "auth #" not in html and ">login<" not in html


def test_health_checks_the_database(client, monkeypatch):
    assert client.get("/health").text == "ok"
    from app import database

    class Broken:
        def connect(self):
            raise RuntimeError("sem banco")

    monkeypatch.setattr(database, "engine", Broken())
    r = client.get("/health")
    assert r.status_code == 503 and "banco" in r.text


def test_audit_csv_export_is_admin_only_and_exports_labels(client):
    from fastapi.testclient import TestClient
    from app.main import app

    r = client.get("/admin/audit/export.csv")
    assert r.status_code == 200 and "Entrou no sistema" in r.content.decode("utf-8")
    assert TestClient(app).get("/admin/audit/export.csv", follow_redirects=False).status_code == 303
