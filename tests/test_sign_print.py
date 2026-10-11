"""Imprimir para assinatura: a folha da loja + a conta original, num clique (fluxo original: diretor confere e assina a nota)."""
import pytest

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
    assert "Folha para assinatura" in html and 'class="orig-page ' in html
    assert f'src="/documents/{bill.document_id}"' in html                                   # foto original (não PDF)
    assert html.index('class="sheet') < html.index('class="orig-page ')                      # a conta vem DEPOIS da folha
    assert "@page orig-p" in client.get("/static/css/app.css").text and "@page orig-l" in client.get("/static/css/app.css").text


def test_report_without_the_original_when_unchecked_or_no_bill(client, db, png):
    _, bill = _saved_bill(client, db, png)
    sid = bill.unit.store_id
    assert 'class="orig-page ' not in client.get(f"/stores/{sid}/report?bill={bill.id}&doc=0").text
    plain = client.get(f"/stores/{sid}/report").text
    assert 'class="orig-page ' not in plain and "Folha de impressão" in plain


def test_bill_from_another_store_is_ignored(client, db, png):
    _, bill = _saved_bill(client, db, png)
    other = Store(code="OUTRA", name="Outra loja")
    db.add(other)
    db.commit()
    html = client.get(f"/stores/{other.id}/report?bill={bill.id}&doc=1").text
    assert 'class="orig-page ' not in html and "Folha para assinatura" not in html          # não mistura conta de outra loja


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


def _png(w, h):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.parametrize("w,h,cls", [(600, 900, "orig-page p"), (900, 600, "orig-page l")])
def test_each_original_page_keeps_its_own_orientation(client, db, w, h, cls):
    """A conta original sai na proporção e na orientação dela: foto em pé = página em pé, foto deitada = página deitada."""
    _, bill = _saved_bill(client, db, _png(w, h))
    html = client.get(f"/stores/{bill.unit.store_id}/report?bill={bill.id}&doc=1").text
    assert f'class="{cls}"' in html


def test_pdf_pages_report_their_real_orientation():
    import io

    from PIL import Image

    from app.services import pdf_pages

    buf = io.BytesIO()
    a, b = Image.new("RGB", (600, 900), "white"), Image.new("RGB", (900, 600), "white")
    a.save(buf, "PDF", save_all=True, append_images=[b], resolution=100)
    sizes = pdf_pages.page_sizes(buf.getvalue())
    assert len(sizes) == 2 and sizes[0][0] < sizes[0][1] and sizes[1][0] > sizes[1][1]


def test_image_orientation_follows_exif_like_the_browser():
    """Foto de celular guarda o giro no EXIF: o navegador mostra girada, então a página também tem de ser girada."""
    import io

    from PIL import Image

    from app.services import pdf_pages

    im = Image.new("RGB", (900, 600), "white")
    exif = im.getexif()
    exif[0x0112] = 6                                    # girar 90°: a foto aparece em pé
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    assert pdf_pages.image_display_size(buf.getvalue()) == (600, 900)


def test_original_images_are_never_stretched_in_print_css():
    css = open("app/static/css/app.css", encoding="utf-8").read()
    assert "width: auto; height: auto; object-fit: contain" in css and "max-height: 278mm" in css and "max-height: 190mm" in css
