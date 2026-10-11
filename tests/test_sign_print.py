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


def test_print_pages_of_a_pdf_use_the_sharper_render():
    """115 dpi esticado até A4 saía borrado: a impressão pede a página em ~190 dpi (hq=1)."""
    import io
    import struct

    from PIL import Image

    from app.services import pdf_pages

    buf = io.BytesIO()
    Image.new("RGB", (600, 900), "white").save(buf, "PDF", resolution=72)

    def width(png):
        return struct.unpack(">I", png[16:20])[0]

    normal = pdf_pages.render_page(buf.getvalue(), 1)
    sharp = pdf_pages.render_page(buf.getvalue(), 1, pdf_pages.PRINT_SCALE)
    assert width(sharp) > width(normal) * 1.5
    assert "hq=1" in open("app/routes/stores.py", encoding="utf-8").read()


def test_sign_page_has_two_separate_print_jobs(client, db, png):
    """Cada impressão com uma orientação só: 1) a folha da loja; 2) a conta original sozinha (foto ou PDF do jeito que é)."""
    _, bill = _saved_bill(client, db, _png(600, 900))
    html = client.get(f"/stores/{bill.unit.store_id}/report?bill={bill.id}&doc=1").text
    assert "data-print-chain" in html and "Imprimir tudo: folha e depois a conta" in html and "data-print-sheet" in html
    assert f'data-next="/impressao/original/{bill.document_id}"' in html and f'href="/impressao/original/{bill.document_id}"' in html
    assert "Tudo no mesmo trabalho" in html
    assert "html.sheet-only .orig-page { display: none" in open("app/static/css/app.css", encoding="utf-8").read()
    js = open("app/static/js/app.js", encoding="utf-8").read()
    assert "data-print-sheet" in js and "data-print-chain" in js and "afterprint" in js and "window.location.href = next" in js


def test_original_photo_print_page_matches_the_photo_orientation(client, db):
    _, bill = _saved_bill(client, db, _png(900, 600))
    r = client.get(f"/impressao/original/{bill.document_id}")
    assert r.status_code == 200 and "size: A4 landscape" in r.text and f'src="/documents/{bill.document_id}"' in r.text
    assert "window.print()" in r.text and "nonce=" in r.text                                      # sem script inline solto (CSP)


def test_original_portrait_photo_prints_in_portrait(client, db):
    _, bill = _saved_bill(client, db, _png(600, 900))
    assert "size: A4 portrait" in client.get(f"/impressao/original/{bill.document_id}").text


def test_original_print_page_needs_login_and_missing_is_404(client):
    from tests.test_security import _new_client

    assert client.get("/impressao/original/99999").status_code == 404
    r = _new_client().get("/impressao/original/1")
    assert "/login" in str(r.url)


def test_original_pdf_print_page_uses_the_pages_in_the_orientation_of_the_first(client, db):
    """2º passo do "Imprimir tudo" para PDF: páginas em ~190 dpi, um trabalho só, na orientação da 1ª página."""
    import io

    from PIL import Image

    from app.models import Document

    buf = io.BytesIO()
    a, b = Image.new("RGB", (600, 900), "white"), Image.new("RGB", (600, 900), "white")
    a.save(buf, "PDF", save_all=True, append_images=[b], resolution=100)
    _make_store(client)
    r = client.post("/import", {"store_id": ""}, files={"file": ("conta.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 303
    job = int(r.headers["location"].rsplit("/", 1)[1])
    html = client.get(f"/import/{job}/review").text
    client.post(f"/import/{job}/confirm", {**_form_from_review(html), "unit_mode": "matched"})
    doc = db.query(Document).order_by(Document.id.desc()).first()
    r = client.get(f"/impressao/original/{doc.id}")
    assert r.status_code == 200 and "size: A4 portrait" in r.text
    assert r.text.count(f"/documents/{doc.id}/pages/") == 2 and "hq=1" in r.text
