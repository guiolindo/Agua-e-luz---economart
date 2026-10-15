"""Rede da empresa pelo IP do link (COMPANY_NETWORKS): só registro, nada pedido ao usuário nem bloqueado."""
from app.config import get_settings
from app.services import network_service
from tests.test_security import _new_client
from tests.test_security import _login


def test_company_ip_accepts_single_ips_and_ranges(monkeypatch):
    monkeypatch.setattr(get_settings(), "company_networks", "187.32.111.41, 186.248.0.0/16, lixo")
    assert network_service.is_company_ip("187.32.111.41") and network_service.is_company_ip("186.248.7.9")
    assert not network_service.is_company_ip("169.150.224.129") and not network_service.is_company_ip("x")


def test_no_browser_probe_and_csp_untouched(client):
    r = client.get("/")
    assert "data-net-check" not in r.text and "/api/rede" not in r.text
    assert "connect-src 'self';" in r.headers["content-security-policy"]


def test_panel_marks_each_person_by_the_ip_of_the_last_login(client, monkeypatch):
    assert "<th>Rede</th>" not in client.get("/admin").text                         # sem IPs cadastrados: sem coluna
    monkeypatch.setattr(get_settings(), "company_networks", "187.32.111.41")
    inside = _new_client()
    inside.tc.headers["X-Real-IP"] = "187.32.111.41"
    _login(inside, "admin", "admin-pass-123")
    panel = client.get("/admin").text
    assert "<th>Rede</th>" in panel and "Rede da empresa" in panel
    outside = _new_client()
    outside.tc.headers["X-Real-IP"] = "200.10.10.10"
    _login(outside, "admin", "admin-pass-123")
    assert "Fora da rede da empresa" in client.get("/admin").text


def test_ip_page_tells_whether_the_ip_is_the_companys(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "company_networks", "187.32.111.41")
    html = client.get("/admin/ip", headers={"X-Real-IP": "187.32.111.41"}).text
    assert "IP da empresa?" in html and "Sim" in html and "Testar agora" not in html
