"""Imprimir para assinatura: a folha da loja + a conta original, num clique (fluxo original: diretor confere e assina a nota)."""
from app.models import EnergyBill, Store
from tests.test_app_flow import _form_from_review, _make_store, _upload


def _saved_bill(client, db, png):
    _make_store(client)
    job = _upload(client, png)
    html = client.get(f"/import/{job}/review").text
    r = client.post(f"/import/{job}/confirm", {**_form_from_review(html), "unit_mode": "matched"})
    assert r.status_code == 303
    return r.headers["location"], db.query(EnergyBill).one()


def test_saving_a_bill_offers_print_for_signature(client, db, png):
    loc, bill = _saved_bill(client, db, png)
    assert f"bill={bill.id}" in loc
    page = client.get(loc).text
    assert "Imprimir para assinatura" in page and f"/stores/{bill.unit.store_id}/report?bill={bill.id}&doc=1" in page


def test_report_with_bill_prints_the_original_after_the_sheet(client, db, png):
    _, bill = _saved_bill(client, db, png)
    sid = bill.unit.store_id
    r = client.get(f"/stores/{sid}/report?bill={bill.id}&doc=1")
    assert r.status_code == 200
    html = r.text
    assert "Folha para assinatura" in html and 'class="orig-page"' in html
    assert f'src="/documents/{bill.document_id}"' in html                                   # foto original (não PDF)
    assert html.index('class="sheet') < html.index('class="orig-page"')                      # a conta vem DEPOIS da folha
    assert "@page orig" in client.get("/static/css/app.css").text                            # original em página retrato


def test_report_without_the_original_when_unchecked_or_no_bill(client, db, png):
    _, bill = _saved_bill(client, db, png)
    sid = bill.unit.store_id
    assert 'class="orig-page"' not in client.get(f"/stores/{sid}/report?bill={bill.id}&doc=0").text
    plain = client.get(f"/stores/{sid}/report").text
    assert 'class="orig-page"' not in plain and "Folha de impressão" in plain


def test_bill_from_another_store_is_ignored(client, db, png):
    _, bill = _saved_bill(client, db, png)
    other = Store(code="OUTRA", name="Outra loja")
    db.add(other)
    db.commit()
    html = client.get(f"/stores/{other.id}/report?bill={bill.id}&doc=1").text
    assert 'class="orig-page"' not in html and "Folha para assinatura" not in html          # não mistura conta de outra loja


def test_bills_list_has_the_right_print_buttons(client, db, png):
    _, bill = _saved_bill(client, db, png)
    html = client.get("/notas").text
    assert "Imprimir para assinatura" in html and "Relatório da conta" in html
    assert f"/stores/{bill.unit.store_id}/report?bill={bill.id}&doc=1" in html and f"/bills/{bill.id}/print" in html


def test_old_bill_report_explains_what_it_is(client, db, png):
    _, bill = _saved_bill(client, db, png)
    html = client.get(f"/bills/{bill.id}/print").text
    assert "Relatório da conta" in html and "Imprimir para assinatura" in html


def test_dashboard_lists_recent_bills_with_the_signature_button(client, db, png):
    _, bill = _saved_bill(client, db, png)
    html = client.get("/").text
    assert "Últimas contas lançadas" in html and f"/stores/{bill.unit.store_id}/report?bill={bill.id}&doc=1" in html


def test_dashboard_without_bills_has_no_recent_card(client):
    assert "Últimas contas lançadas" not in client.get("/").text


def test_help_and_tutorial_explain_the_signature_print():
    help_html = open("app/templates/help.html", encoding="utf-8").read()
    assert 'id="assinar"' in help_html and "Imprimir para assinatura" in help_html and "Relatório da conta" in help_html
    assert "Imprimir para assinatura" in open("TUTORIAL.md", encoding="utf-8").read()
