"""Rede da empresa pelo IP do link: o admin cadastra os IPs; cada evento da auditoria grava se veio da empresa."""
from app.config import get_settings
from app.models import AuditLog, CompanyNetwork
from app.services import network_service
from tests.test_security import _login, _new_client


def _login_from(ip, user="admin", pw="admin-pass-123"):
    c = _new_client()
    c.tc.headers["X-Real-IP"] = ip
    _login(c, user, pw)
    return c


def test_ips_and_ranges_from_env_and_from_the_admin(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "company_networks", "186.248.0.0/16, lixo")
    network_service.reset()
    assert network_service.is_company_ip("186.248.7.9") and not network_service.is_company_ip("187.32.111.41")
    client.post("/admin/rede", {"cidr": "187.32.111.41", "label": "Link Algar"})
    assert db.query(CompanyNetwork).one().cidr == "187.32.111.41/32"
    assert network_service.is_company_ip("187.32.111.41") and not network_service.is_company_ip("x")
    assert db.query(AuditLog).filter_by(action="network_add").count() == 1
    client.post("/admin/rede", {"cidr": "10.0.0.0/4"})                               # faixa larga demais
    client.post("/admin/rede", {"cidr": "nao-e-ip"})
    assert db.query(CompanyNetwork).count() == 1


def test_nothing_is_said_while_no_ip_is_registered(client, db):
    _login_from("187.32.111.41")
    assert all("rede" not in (a.details or {}) for a in db.query(AuditLog).all())
    assert "<th>Rede</th>" not in client.get("/admin").text


def test_each_event_records_where_it_came_from_at_that_moment(client, db):
    client.post("/admin/rede", {"cidr": "187.32.111.41"})
    inside = _login_from("187.32.111.41")
    inside.post("/types", {"name": "AGUA TESTE", "kind": "manual"})                 # um evento qualquer, não só login
    _login_from("200.10.10.10")
    logins = db.query(AuditLog).filter_by(action="login").order_by(AuditLog.id).all()
    assert [a.details.get("rede") for a in logins[-2:]] == ["empresa", "fora"]
    assert db.query(AuditLog).filter_by(action="create", entity="record_type").one().details["rede"] == "empresa"
    html = client.get("/admin/audit").text
    assert "na empresa" in html and ">fora<" in html
    row = db.query(CompanyNetwork).one()
    client.post(f"/admin/rede/{row.id}/remover", {})                                  # o IP saiu do cadastro...
    db.expire_all()
    assert db.query(AuditLog).filter_by(action="login").order_by(AuditLog.id).all()[-2].details["rede"] == "empresa"   # ...e o histórico não muda


def test_new_company_ip_shows_up_as_frequent_unknown(client, db):
    client.post("/admin/rede", {"cidr": "187.32.111.41"})
    for _ in range(3):
        _login_from("177.10.20.30")                                                    # a operadora trocou o IP
    page = client.get("/admin/ip").text
    assert "IPs de login frequentes que não estão cadastrados" in page and "177.10.20.30" in page
    client.post("/admin/rede", {"cidr": "177.10.20.30"})
    assert "IPs de login frequentes" not in client.get("/admin/ip").text                # cadastrado: sai da lista


def test_panel_column_uses_the_last_login(client, db):
    client.post("/admin/rede", {"cidr": "187.32.111.41"})
    _login_from("187.32.111.41")
    panel = client.get("/admin").text
    assert "<th>Rede</th>" in panel and "Na empresa" in panel
