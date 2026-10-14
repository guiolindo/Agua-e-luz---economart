"""Auditoria de fluxo (14/10/2026): páginas de erro, sessão expirada, primeiro acesso e conferência mais simples."""
from tests.test_app_flow import _form_from_review, _make_store, _upload
from tests.test_director import _create_user, _login, _new_client


def test_unknown_address_shows_a_friendly_page_not_json(client):
    r = client.get("/pagina-que-nao-existe", headers={"accept": "text/html"})
    assert r.status_code == 404 and "Página não encontrada" in r.text and '{"detail"' not in r.text
    assert "Ir para o início" in r.text and "Código 404" not in r.text
    r = client.get("/stores/99999", headers={"accept": "text/html"})
    assert r.status_code == 404 and "Loja não encontrada." in r.text


def test_expired_session_explains_why_you_are_back_at_login(client):
    c = _new_client()
    assert "Sua sessão terminou" in c.get("/login?next=/notas").text
    assert "Sua sessão terminou" not in c.get("/login").text


def test_first_access_asks_for_the_temporary_password_by_name(client):
    pw = _create_user(client, "joana", "operator")
    c = _new_client()
    _login(c, "joana", pw)
    page = c.get("/account/password").text
    assert "Senha provisória" in page


def test_review_hides_the_other_unit_options_when_the_unit_was_recognised(client, db, png):
    _make_store(client)
    job = _upload(client, png)
    html = client.get(f"/import/{job}/review").text
    assert '<details class="unit-other"' in html and "Não é esta unidade? Trocar" in html
    assert "review-actions" in html                                                       # botão de salvar fixo à vista
    r = client.post(f"/import/{job}/confirm", {**_form_from_review(html), "unit_mode": "matched"})
    assert r.status_code == 303
    after = client.get(r.headers["location"]).text
    assert "Importar outra" in after and 'id="sign-link"' in after                       # um só destaque: imprimir
