"""Apresentação do sistema (/apresentacao): disponível para qualquer perfil logado, só até o prazo."""
import re
from pathlib import Path

import pytest

from app.config import get_settings
from app.utils import presentation
from tests.test_director import _user


@pytest.fixture
def until(monkeypatch):
    def set_(value):
        monkeypatch.setattr(get_settings(), "presentation_until", value)
    return set_


def test_every_role_sees_the_button_and_the_slides(client, until):
    until("2999-01-01T00:00:00-03:00")
    for name, role in (("apres1", "operator"), ("apres2", "director"), ("apres3", "viewer")):
        c = _user(client, name, role)
        assert 'href="/apresentacao"' in c.get("/").text or role == "director"        # diretoria abre direto no painel dela
        r = c.get("/apresentacao")
        assert r.status_code == 200 and "Antes. <em>Depois.</em>" in r.text and 'data-chapter="dir"' in r.text
    assert 'href="/apresentacao"' in client.get("/stores").text                       # administrador também


def test_presentation_requires_login(client):
    from tests.test_security import _new_client

    r = _new_client().get("/apresentacao")
    assert "/login" in str(r.url)                                               # segue o redirecionamento ao login
    assert "data-chapter" not in r.text


def test_after_the_deadline_the_button_and_the_page_are_gone(client, until):
    until("2020-01-01T00:00:00-03:00")
    assert 'href="/apresentacao"' not in client.get("/stores").text
    assert client.get("/apresentacao").status_code == 404


@pytest.mark.parametrize("value", ["", "isso não é data"])
def test_empty_or_invalid_deadline_keeps_it_closed(client, until, value):
    until(value)
    assert not presentation.presentation_open()
    assert client.get("/apresentacao").status_code == 404


def test_default_deadline_is_friday_16_oct_2026_at_5pm_brasilia():
    d = presentation.presentation_deadline()
    assert (d.year, d.month, d.day, d.hour, d.minute) == (2026, 10, 16, 17, 0) and d.weekday() == 4
    assert d.utcoffset().total_seconds() == -3 * 3600


def test_naive_deadline_is_read_as_brasilia_time(until):
    until("2026-10-16T17:00:00")
    assert presentation.presentation_until_label() == "sexta, 16/10/2026, às 17h"


def test_no_admin_screens_in_the_slides_and_every_image_exists(client, until):
    until("2999-01-01T00:00:00-03:00")
    html = client.get("/apresentacao").text
    assert "/admin" not in html and "admin-" not in html                               # a tela de administrador não é mostrada
    files = re.findall(r"/static/img/apresentacao/([\w.-]+)", html)
    assert len(files) >= 15
    for f in files:
        assert (Path("app/static/img/apresentacao") / f).is_file(), f
    assert "antes.webp" in files and "folha-impressa.webp" in files                    # comparativo antes × depois da folha
    for font in ("bricolage-grotesque", "inter"):
        assert (Path("app/static/fonts") / f"{font}-latin-wght-normal.woff2").is_file()


def test_presentation_page_is_allowed_by_the_csp(client, until):
    until("2999-01-01T00:00:00-03:00")
    r = client.get("/apresentacao")
    assert "<script nonce" not in r.text and "onclick=" not in r.text                  # só script externo (CSP sem unsafe-inline)


def test_presentation_uses_only_fictional_names(client, until):
    """Telas e textos da apresentação são de demonstração: nada de unidade, cliente ou loja reais."""
    until("2999-01-01T00:00:00-03:00")
    html = client.get("/apresentacao").text
    for real in ("MULTICOM", "12.060.073", "CD300", "Ribeirão das Neves"):
        assert real not in html
    css = open("app/static/css/presentation.css", encoding="utf-8").read()
    assert "http" not in css.replace("http://www.w3.org/2000/svg", "")                  # sem fontes/recursos externos (CSP)
