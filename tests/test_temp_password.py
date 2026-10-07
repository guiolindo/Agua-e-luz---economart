import re
from datetime import timedelta

import pytest

from app import security
from app.config import get_settings
from app.models import AuditLog, User
from app.models.mixins import utcnow
from tests.test_security import _create_user, _login, _new_client


def test_temp_password_is_four_digits_without_obvious_patterns():
    pins = [security.generate_temp_password() for _ in range(4000)]
    assert all(re.fullmatch(r"\d{4}", p) for p in pins)
    for p in pins:
        d = [int(c) for c in p]
        assert len(set(p)) > 1 and {d[i + 1] - d[i] for i in range(3)} not in ({1}, {-1}) and p[:2] != p[2:]   # nada de 0000/1234/4321/1212
    assert len(set(pins)) > 1500 and {c for p in pins for c in p} == set("0123456789")                       # sorteio bem distribuído


def test_admin_sees_the_pin_once_with_validity_and_user_must_change_it(client, db):
    html = client.post("/admin/users", {"username": "joana", "role": "operator"}).text
    pin = re.search(r"<code[^>]*>(.*?)</code>", html).group(1)
    assert re.fullmatch(r"\d{4}", pin) and "48 horas" in html and pin not in client.get("/admin/users").text
    u = db.query(User).filter_by(username="joana").one()
    assert u.must_change_password and u.temp_expires_at is not None
    delta = u.temp_expires_at.replace(tzinfo=None) - utcnow().replace(tzinfo=None)
    assert timedelta(hours=47) < delta <= timedelta(hours=48)
    c = _new_client()
    assert _login(c, "joana", pin).headers["location"] == "/account/password"              # 1º acesso: só troca de senha
    assert c.get("/stores", follow_redirects=False).headers["location"] == "/account/password"


def test_the_pin_never_lowers_the_bar_for_the_real_password(client, db):
    pin = _create_user(client, "marcos", "operator")
    c = _new_client()
    _login(c, "marcos", pin)
    for weak in ("1234", "12345678", "marcos-2026", "senha"):                                # a SENHA PESSOAL segue exigente
        assert c.post("/account/password", {"current_password": pin, "new_password": weak, "confirm": weak}).status_code == 400
    ok = c.post("/account/password", {"current_password": pin, "new_password": "Minha-Senha-Forte-77", "confirm": "Minha-Senha-Forte-77"})
    assert ok.status_code == 303
    db.expire_all()
    u = db.query(User).filter_by(username="marcos").one()
    assert not u.must_change_password and u.temp_expires_at is None
    assert _login(_new_client(), "marcos", pin).status_code == 401                          # o PIN morreu


def test_expired_pin_cannot_be_used_and_admin_reset_issues_a_new_one(client, db):
    pin = _create_user(client, "paula", "operator")
    u = db.query(User).filter_by(username="paula").one()
    u.temp_expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    r = _login(_new_client(), "paula", pin)
    assert r.status_code == 401 and "incorretos" in r.text                                   # mesma mensagem genérica
    db.expire_all()
    assert db.query(AuditLog).filter_by(action="login_temp_expired").count() == 1
    assert "Senha provisória expirada" in client.get("/admin/users").text
    html = client.post(f"/admin/users/{u.id}/reset-password", {}).text
    new_pin = re.search(r"<code[^>]*>(.*?)</code>", html).group(1)
    assert re.fullmatch(r"\d{4}", new_pin) and _login(_new_client(), "paula", new_pin).status_code == 303


def test_accounts_with_a_pin_lock_after_3_wrong_tries_normal_accounts_after_5(client, db):
    pin = _create_user(client, "rafa", "operator")
    c = _new_client()
    for _ in range(3):
        _login(c, "rafa", "0000x")
    assert _login(c, "rafa", pin).status_code == 401                                         # PIN certo, mas já bloqueada
    # conta normal (admin): continua com 5
    adm = _new_client()
    codes = [_login(adm, "admin", "errada-errada-1").status_code for _ in range(4)]
    assert codes == [401] * 4 and _login(adm, "admin", "admin-pass-123").status_code == 303


def test_pin_brute_force_is_not_feasible_with_the_lockout(client):
    """10.000 combinações / 3 tentativas por bloqueio de 15 min = ~34 dias de bloqueios sucessivos para esgotar o espaço."""
    s = get_settings()
    windows = 10_000 / s.temp_max_login_attempts
    days = windows * s.login_block_minutes / 60 / 24
    assert days > 30 and s.temp_password_hours == 48
    assert pytest is not None
