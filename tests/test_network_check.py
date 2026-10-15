"""Máquina/rede da empresa: só registro (auditoria e Painel admin), nunca bloqueia."""
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models import AuditLog
from app.services import network_service


def test_company_ip_accepts_single_ips_and_ranges(monkeypatch):
    monkeypatch.setattr(get_settings(), "company_networks", "187.32.111.41, 186.248.0.0/16, lixo")
    assert network_service.is_company_ip("187.32.111.41") and network_service.is_company_ip("186.248.7.9")
    assert not network_service.is_company_ip("169.150.224.129") and not network_service.is_company_ip("x")


def test_disabled_by_default_and_csp_unchanged(client):
    html = client.get("/").text
    assert "data-net-check" not in html
    assert "connect-src 'self';" in client.get("/").headers["content-security-policy"]


def test_probe_url_is_allowed_in_csp_and_sent_to_the_page(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "intranet_probe_url", "https://lupus.intranet/ping")
    r = client.get("/")
    assert 'data-net-check="https://lupus.intranet/ping"' in r.text
    assert "connect-src 'self' https://lupus.intranet;" in r.headers["content-security-policy"]
    monkeypatch.setattr(get_settings(), "intranet_probe_url", "https://x.intranet'; script-src *")
    assert "script-src *" not in client.get("/").headers["content-security-policy"]   # nada injetado na CSP


def test_result_is_recorded_once_per_session(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "intranet_probe_url", "https://lupus.intranet/")
    monkeypatch.setattr(get_settings(), "company_networks", "187.32.111.41")
    h = {"X-CSRF-Token": client.token, "X-Real-IP": "187.32.111.41"}
    assert client.tc.post("/api/rede", json={"intranet": True}, headers=h).status_code == 200
    assert client.tc.post("/api/rede", json={"intranet": False}, headers=h).status_code == 200   # repetido: ignorado
    rows = db.query(AuditLog).filter_by(action="network_check").all()
    assert len(rows) == 1 and rows[0].details["intranet"] is True and rows[0].details["ip_empresa"] is True
    assert "data-net-check" not in client.get("/").text                            # já testou nesta sessão
    panel = client.get("/admin").text
    assert "<th>Rede</th>" in panel and "Máquina da empresa" in panel
    assert TestClient(app).post("/api/rede", json={"intranet": True}, follow_redirects=False).status_code in (303, 401, 403)


def test_outside_is_shown_as_such_and_requires_csrf(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "intranet_probe_url", "https://lupus.intranet/")
    assert client.tc.post("/api/rede", json={"intranet": True}).status_code == 403   # sem token
    client.tc.post("/api/rede", json={"intranet": False}, headers={"X-CSRF-Token": client.token})
    assert "Fora da empresa" in client.get("/admin").text
