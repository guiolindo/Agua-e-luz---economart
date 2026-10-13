"""Painel do administrador: on-line, última conta lançada, exportações, quem abriu a apresentação."""
from datetime import timedelta

import pytest

from app.config import get_settings

from app.models import AuditLog, User
from app.models.mixins import utcnow
from app.services import admin_panel
from tests.test_app_flow import _make_store
from tests.test_director import _user
from tests.test_roles import _seed_bill


def test_only_admin_sees_the_admin_panel(client, db):
    assert client.get("/admin").status_code == 200
    for name, role in (("func1", "operator"), ("dir1", "director"), ("con1", "viewer")):
        assert _user(client, name, role).get("/admin").status_code == 403
    assert 'href="/admin"' in client.get("/").text and "Painel admin" in client.get("/").text


def test_who_is_online_and_logout_takes_them_off(client, db):
    func = _user(client, "func2", "operator")
    func.get("/")
    html = client.get("/admin").text
    assert "On-line agora" in html and "func2" in html
    db.expire_all()
    u = db.query(User).filter_by(username="func2").one()
    assert admin_panel.is_online(u)
    func.post("/logout", {})
    db.expire_all()
    assert not admin_panel.is_online(db.query(User).filter_by(username="func2").one())


def test_last_seen_is_written_at_most_once_a_minute(client, db):
    client.get("/")
    db.expire_all()
    first = db.query(User).filter_by(username="admin").one().last_seen_at
    client.get("/stores")
    db.expire_all()
    assert db.query(User).filter_by(username="admin").one().last_seen_at == first


def test_last_entry_and_last_export(client, db):
    store_id = _make_store(client)
    _seed_bill(client, db, store_id)
    client.get("/notas/export.xlsx")
    html = client.get("/admin").text
    assert "Última conta lançada" in html and "CD300" in html and "R$ 1.000,00" in html
    assert "Planilha (Excel) da lista de contas" in html


@pytest.fixture
def open_presentation(monkeypatch):
    monkeypatch.setattr(get_settings(), "presentation_until", "2099-01-01T00:00:00-03:00")


def test_presentation_views_are_logged_once_per_half_hour(client, db, open_presentation):
    func = _user(client, "func3", "operator")
    assert func.get("/apresentacao").status_code == 200
    func.get("/apresentacao")
    assert db.query(AuditLog).filter_by(action="view", entity="presentation").count() == 1
    html = client.get("/admin").text
    assert "1</strong> de" in html and "func3" in html and "Ainda não abriram: admin" in html


def test_ago_is_human():
    now = utcnow()
    assert admin_panel.ago(None) == "nunca" and admin_panel.ago(now, now) == "agora"
    assert admin_panel.ago(now - timedelta(minutes=3), now) == "há 3 min"
    assert admin_panel.ago(now - timedelta(hours=2), now) == "há 2 h"
    assert admin_panel.ago(now - timedelta(days=1, hours=1), now) == "ontem"
    assert admin_panel.ago(now - timedelta(days=5), now) == "há 5 dias"
