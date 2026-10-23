"""Fim do projeto: com SITE_CLOSED, todo endereço responde 404 com a tela verde; depois de SITE_BLACK_AT, tela preta."""
import re

import pytest

from app.config import get_settings


@pytest.fixture
def closed(monkeypatch):
    def set_(black_at="2999-01-01T00:00:00-03:00"):
        monkeypatch.setattr(get_settings(), "site_closed", True)
        monkeypatch.setattr(get_settings(), "site_black_at", black_at)
    return set_


PATHS = ["/", "/login", "/diretoria", "/admin/users", "/stores/1", "/static/css/app.css", "/apresentacao", "/qualquer"]


def test_every_address_shows_the_green_404_without_anything_of_the_system(client, closed):
    closed()
    for path in PATHS:
        r = client.tc.get(path, follow_redirects=False)
        assert r.status_code == 404, path
        assert "<h1>404</h1>" in r.text and "Not Found" in r.text, path
        low = r.text.lower()
        assert not any(w in low for w in ("economart", "energia", "logo", "<img", "<script", "<form")), path
    r = client.tc.post("/login", data={"username": "admin", "password": "admin-pass-123"}, follow_redirects=False)
    assert r.status_code == 404 and "set-cookie" not in r.headers                   # não dá mais para entrar


def test_page_is_safe_and_clears_the_browser(client, closed):
    closed()
    r = client.tc.get("/")
    nonce = re.search(r"'nonce-([^']+)'", r.headers["content-security-policy"]).group(1)
    assert f'<style nonce="{nonce}">' in r.text and "style=" not in r.text.replace("<style", "")
    assert "script-src" not in r.headers["content-security-policy"]                 # nem um script na página
    assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"]
    assert '"cookies"' in r.headers["clear-site-data"] and '"storage"' in r.headers["clear-site-data"]
    assert r.text.count('">404</i>') == 160                                         # "404" espalhado pela tela


def test_health_still_answers_for_the_deploy_and_old_service_worker_uninstalls(client, closed):
    closed()
    assert client.tc.get("/health").status_code == 200
    sw = client.tc.get("/sw.js")
    assert sw.status_code == 200 and "unregister()" in sw.text and "offline" not in sw.text


def test_after_ten_days_only_a_black_screen(client, closed):
    closed(black_at="2020-01-01T00:00:00-03:00")
    r = client.tc.get("/diretoria")
    assert r.status_code == 404 and "background:#000" in r.text
    assert "404" not in r.text and "<title>" not in r.text and "<body></body>" in r.text


def test_default_is_closed_and_black_on_2_nov_2026():
    from app.closed import black_at
    from app.config import Settings

    fields = Settings.model_fields                                               # padrão do código (sem o .env dos testes)
    assert fields["site_closed"].default is True and fields["site_black_at"].default.startswith("2026-11-02T00:00")
    assert black_at() is not None


def test_reopening_is_one_variable(client):
    assert get_settings().site_closed is False                                      # testes rodam com o sistema aberto
    assert client.get("/stores").status_code == 200
