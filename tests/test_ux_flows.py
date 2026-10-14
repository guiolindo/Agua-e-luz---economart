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


def test_search_with_empty_filters_works(client, db):
    """O formulário de Contas manda os filtros vazios (store_id=&type_id=): antes dava erro 422 em JSON."""
    r = client.get("/notas?q=L03&store_id=&type_id=&origin=&start=&end=")
    assert r.status_code == 200 and "Contas e lançamentos" in r.text
    assert client.get("/notas/export.csv?q=&store_id=&type_id=").status_code == 200
    assert client.get("/diretoria?region=&supplier=").status_code == 200


def test_search_understands_store_name_and_month_together(client, db):
    from tests.test_roles import _seed_bill

    store_id = _make_store(client, code="L05")
    db.query(__import__("app.models", fromlist=["Store"]).Store).filter_by(id=store_id).one().name = "Loja Oeste"
    db.commit()
    _seed_bill(client, db, store_id)                                      # conta de AGO/2026
    def n(q):
        import re
        return int(re.search(r"(\d+) registro", client.get("/notas", params={"q": q}).text).group(1))
    assert n("L05 ago/2026") == 1 and n("loja oeste") == 1 and n("oeste agosto") == 1 and n("08/2026") == 1
    assert n("L05 set/2026") == 0 and n("cemig 2026") == 1
