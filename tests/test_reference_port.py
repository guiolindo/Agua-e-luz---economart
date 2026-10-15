"""Recursos trazidos do projeto Notas-despesas: tela offline, rastreio de requisição, PDF com script, confirmação
com senha em contas sensíveis, cache/compressão dos estáticos e a matriz de rotas protegidas."""
import io
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

from app.main import app
from app.models import User
from app.utils.uploads import UploadError, pdf_has_active_content, validate_upload
from tests.test_director import _user
from tests.test_security import _create_user


# ------------------------------------------------------------ PDF com script
def _pdf(extra=None) -> bytes:
    w = PdfWriter()
    w.add_blank_page(200, 200)
    if extra:
        extra(w)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _open_launch(w):
    w._root_object[NameObject("/OpenAction")] = DictionaryObject(
        {NameObject("/S"): NameObject("/Launch"), NameObject("/F"): TextStringObject("calc.exe")})


def _link(action):
    def add(w):
        an = DictionaryObject({NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Link"),
                               NameObject("/A"): DictionaryObject(action)})
        w.pages[0][NameObject("/Annots")] = ArrayObject([w._add_object(an)])
    return add


def test_clean_pdf_and_plain_links_are_accepted():
    assert not pdf_has_active_content(_pdf())
    uri = _link({NameObject("/S"): NameObject("/URI"), NameObject("/URI"): TextStringObject("https://cemig.com.br")})
    data = _pdf(uri)
    assert not pdf_has_active_content(data)                              # conta com link para o site: normal
    assert validate_upload("conta.pdf", data, 10_000_000)[1] == "application/pdf"


@pytest.mark.parametrize("extra", [
    lambda w: w.add_js("app.alert('x')"),                                 # JavaScript no catálogo
    _open_launch,                                                         # abrir programa ao abrir o PDF
    _link({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("x")}),
])
def test_pdf_with_script_is_refused(extra):
    data = _pdf(extra)
    assert pdf_has_active_content(data)
    with pytest.raises(UploadError, match="código embutido"):
        validate_upload("conta.pdf", data, 10_000_000)


def test_unparseable_pdf_falls_back_to_byte_scan():
    assert pdf_has_active_content(b"%PDF-1.4 lixo /JavaScript lixo")
    assert not pdf_has_active_content(b"%PDF-1.4 lixo sem nada")


# ------------------------------------------------------------ estáticos, offline e service worker
def test_static_files_are_compressed_and_cached(client):
    r = client.get("/static/css/app.css?v=abc", headers={"Accept-Encoding": "gzip"})
    assert r.headers["content-encoding"] == "gzip"
    assert "immutable" in r.headers["cache-control"]                      # versão no endereço: guarda por 1 ano
    r = client.get("/static/img/logo.png")
    assert r.headers["cache-control"] == "public, max-age=86400"
    page = client.get("/notas", headers={"Accept-Encoding": "gzip"})      # páginas com dados: sem gzip (BREACH) e sem cache
    assert "content-encoding" not in page.headers and page.headers["cache-control"] == "no-store"


def test_asset_version_covers_every_js_and_css():
    from app.web import BASE_DIR, _asset_version

    before = _asset_version()
    admin_js = BASE_DIR / "static" / "js" / "admin.js"
    original = admin_js.read_bytes()
    try:
        admin_js.write_bytes(original + b"\n// muda")
        assert _asset_version() != before                                 # antes, mudar o admin.js não trocava a versão
    finally:
        admin_js.write_bytes(original)


def test_service_worker_and_offline_page_are_public_and_versioned(client):
    anon = TestClient(app)
    sw = anon.get("/sw.js")
    assert sw.status_code == 200 and sw.headers["content-type"].startswith("text/javascript")
    assert "__V__" not in sw.text and sw.headers["service-worker-allowed"] == "/"
    from app.web import templates
    assert templates.env.globals["ASSET_VERSION"] in sw.text
    off = anon.get("/offline")
    assert off.status_code == 200 and "Sem conexão" in off.text and "/static/js/offline.js" in off.text
    assert "<script>" not in off.text                                     # CSP: nada de script embutido


# ------------------------------------------------------------ código da requisição
def test_every_response_has_a_request_id(client):
    r = client.get("/notas")
    assert re.fullmatch(r"[0-9a-f]{8}", r.headers["x-request-id"])
    assert client.get("/notas").headers["x-request-id"] != r.headers["x-request-id"]


def test_500_page_shows_the_request_id(client, monkeypatch):
    from app.routes import help as help_route

    def boom(*a, **k):
        raise RuntimeError("falha simulada")
    monkeypatch.setattr(help_route, "render", boom)
    tc = TestClient(app, raise_server_exceptions=False)
    tc.cookies = client.tc.cookies
    r = tc.get("/ajuda")
    assert r.status_code == 500
    code = re.search(r"Código do erro: <strong class=\"mono\">([0-9a-f]{8})</strong>", r.text)
    assert code


def test_log_lines_carry_the_request_id(caplog):
    import logging

    from app.middleware import RequestIdLogFilter, request_id_var
    request_id_var.set("abcd1234")
    rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "falhou %s", ("aqui",), None)
    RequestIdLogFilter().filter(rec)
    assert rec.getMessage() == "[req=abcd1234] falhou aqui"
    request_id_var.set("")


# ------------------------------------------------------------ sessão (aviso de expiração)
def test_page_tells_the_browser_how_long_the_session_lasts(client):
    html = client.get("/").text
    idle = int(re.search(r'data-idle="(\d+)"', html).group(1))
    left = int(re.search(r'data-max-left="(\d+)"', html).group(1))
    assert idle == 60 * 60 and 11 * 3600 < left <= 12 * 3600
    assert "data-idle" not in TestClient(app).get("/login").text


def test_expired_session_returns_with_the_filters(client):
    anon = TestClient(app)
    r = anon.get("/notas?q=coelba&year=2026", follow_redirects=False)
    assert r.headers["location"] == "/login?next=/notas%3Fq%3Dcoelba%26year%3D2026"


def test_long_forms_warn_before_leaving(client, db):
    from tests.test_app_flow import _make_store
    _make_store(client)
    assert 'id="mf" data-dirty-guard' in client.get("/manual?modo=loja").text
    assert 'id="bf" data-no-loading data-dirty-guard' in client.get("/manual/lote").text


# ------------------------------------------------------------ confirmação com senha em contas sensíveis
def test_resetting_a_director_password_needs_the_admin_password(client, db):
    _create_user(client, "dire1", "director")
    target = db.query(User).filter_by(username="dire1").one()
    html = client.get("/admin/users").text
    assert "data-confirm-password=\"Gerar uma senha provisória para dire1" in html
    r = client.post(f"/admin/users/{target.id}/reset-password", {})
    assert r.status_code == 303                                           # sem a senha: recusado
    assert "Senha incorreta" in client.get("/admin/users").text
    html = client.post(f"/admin/users/{target.id}/reset-password", {"confirm_password": "admin-pass-123"}).text
    assert "dire1" in html and re.search(r"\b\d{4}\b", html)              # com a senha: mostra a provisória


def test_operator_password_reset_needs_no_password(client, db):
    _create_user(client, "func9", "operator")
    target = db.query(User).filter_by(username="func9").one()
    assert client.post(f"/admin/users/{target.id}/reset-password", {}).status_code == 200


def test_deactivating_another_admin_needs_the_password(client, db):
    _create_user(client, "adm2", "admin")
    target = db.query(User).filter_by(username="adm2").one()
    client.post(f"/admin/users/{target.id}/toggle", {})
    db.refresh(target)
    assert target.active                                                  # sem senha: continua ativo
    client.post(f"/admin/users/{target.id}/toggle", {"confirm_password": "admin-pass-123"})
    db.refresh(target)
    assert not target.active


# ------------------------------------------------------------ matriz de rotas
PUBLIC = {"/login", "/login/2fa", "/health", "/sw.js", "/offline", "/favicon.ico", "/logout"}


def _routes(method):
    for r in app.routes:
        if isinstance(r, APIRoute) and method in r.methods and r.path not in PUBLIC:
            yield re.sub(r"\{[^}]+\}", "1", r.path)


def test_every_page_requires_login(client):
    anon = TestClient(app)
    leaks = []
    for path in _routes("GET"):
        r = anon.get(path, follow_redirects=False)
        if not (r.status_code in (401, 403) or (r.status_code in (302, 303, 307) and "/login" in r.headers.get("location", ""))):
            leaks.append((path, r.status_code))
    assert not leaks, f"rotas abertas sem login: {leaks}"


def test_every_admin_route_refuses_other_profiles(client, db):
    operator = _user(client, "func1", "operator")
    open_admin = []
    for path in _routes("GET"):
        if path.startswith("/admin"):
            r = operator.get(path, follow_redirects=False)
            if r.status_code not in (403, 404):
                open_admin.append((path, r.status_code))
    for path in _routes("POST"):
        if path.startswith("/admin"):
            r = operator.post(path, {})
            if r.status_code not in (403, 404, 422):
                open_admin.append((path, r.status_code))
    assert not open_admin, f"rotas de admin abertas a funcionário: {open_admin}"


def test_report_and_print_open_in_the_same_tab():
    """Relatório, folha para assinatura e original são telas do próprio sistema: abrem na mesma aba, com Voltar.
    Aba nova só para a imagem ampliada na conferência (sair dali perderia o que foi digitado) e para o arquivo
    bruto quando não deu para montar a impressão."""
    import pathlib
    root = pathlib.Path("app/templates")
    for f in root.rglob("*.html"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if 'target="_blank"' in line:
                assert f.name in ("review.html", "report.html", "print.html"), f"{f}: {line.strip()[:120]}"
                assert "/report?" not in line and "/print\"" not in line
    for f in ("stores/report.html", "bills/print.html"):
        assert "data-back>← Voltar" in (root / f).read_text(encoding="utf-8")


# ------------------------------------------------------------ IP real atrás da CDN do Railway
def test_client_ip_uses_railway_real_ip_and_falls_back(monkeypatch):
    from starlette.requests import Request

    from app.config import get_settings
    from app.security import client_ip

    def req(headers):
        return Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()], "client": ("10.0.0.9", 1)})
    cdn = {"x-forwarded-for": "186.248.10.20, 169.150.224.129"}
    assert client_ip(req({**cdn, "x-real-ip": "186.248.10.20"})) == "186.248.10.20"     # antes: o IP da CDN
    assert client_ip(req({**cdn, "x-real-ip": "lixo<script>"})) == "169.150.224.129"   # inválido: regra antiga
    assert client_ip(req(cdn)) == "169.150.224.129"
    monkeypatch.setattr(get_settings(), "client_ip_source", "xff")
    assert client_ip(req({**cdn, "x-real-ip": "186.248.10.20"})) == "169.150.224.129"


def test_admin_can_check_the_recorded_ip(client):
    html = client.get("/admin/ip", headers={"X-Real-IP": "186.248.1.2", "X-Forwarded-For": "186.248.1.2, 169.150.224.129"}).text
    assert "IP que o sistema registra" in html and "186.248.1.2" in html and "169.150.224.129" in html
    assert "/admin/ip" in client.get("/admin/audit").text
