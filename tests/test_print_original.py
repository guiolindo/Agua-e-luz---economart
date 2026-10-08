import io

from PIL import Image

from app.models import Document, EnergyBill
from tests.test_app_flow import _form_from_review, _make_store


def _pdf(pages: int) -> bytes:
    imgs = [Image.new("RGB", (600, 800), (255 - i * 40, 255, 255)) for i in range(pages)]
    out = io.BytesIO()
    imgs[0].save(out, "PDF", save_all=True, append_images=imgs[1:])
    return out.getvalue()


def _bill_with(client, db, content: bytes, name: str, mime: str):
    _make_store(client)
    r = client.post("/import", {"store_id": ""}, files={"file": (name, content, mime)})
    assert r.status_code == 303, r.text
    job = int(r.headers["location"].rsplit("/", 1)[1])
    form = {**_form_from_review(client.get(f"/import/{job}/review").text), "unit_mode": "matched"}
    assert client.post(f"/import/{job}/confirm", form).status_code == 303
    return db.query(EnergyBill).one()


def test_pdf_original_is_printed_page_by_page(client, db):
    bill = _bill_with(client, db, _pdf(2), "conta.pdf", "application/pdf")
    off = client.get(f"/bills/{bill.id}/print").text
    assert "Documento original" not in off and "/pages/" not in off                  # sem marcar, nada extra
    html = client.get(f"/bills/{bill.id}/print?doc=1").text
    assert f"/documents/{bill.document_id}/pages/1.png" in html and f"/documents/{bill.document_id}/pages/2.png" in html
    assert "página 1 de 2" in html and 'id="original"' in html and "Original incluído" in html
    assert "não pode ser embutido" not in html
    for n in (1, 2):
        r = client.get(f"/documents/{bill.document_id}/pages/{n}.png")
        assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n" and r.headers["cache-control"] == "no-store"
    assert client.get(f"/documents/{bill.document_id}/pages/3.png").status_code == 404      # só existem 2 páginas
    assert client.get(f"/documents/{bill.document_id}/pages/0.png").status_code == 404


def test_image_original_still_works_and_has_no_page_route(client, db, png):
    bill = _bill_with(client, db, png, "conta.png", "image/png")
    html = client.get(f"/bills/{bill.id}/print?doc=1").text
    assert f'src="/documents/{bill.document_id}"' in html and "Original incluído" in html
    assert client.get(f"/documents/{bill.document_id}/pages/1.png").status_code == 404      # não é PDF


def test_page_route_needs_login_and_handles_expired_or_unreadable_pdf(client, db):
    from fastapi.testclient import TestClient

    from app.main import app
    bill = _bill_with(client, db, _pdf(1), "conta.pdf", "application/pdf")
    assert TestClient(app).get(f"/documents/{bill.document_id}/pages/1.png", follow_redirects=False).status_code == 303
    doc = db.get(Document, bill.document_id)
    doc.data = None                                                                        # retenção de 6 meses já apagou
    db.commit()
    assert client.get(f"/documents/{bill.document_id}/pages/1.png").status_code == 410
    assert "Documento original" not in client.get(f"/bills/{bill.id}/print?doc=1").text   # e a conta ainda imprime


def test_corrupt_pdf_falls_back_to_a_link_instead_of_breaking_the_print_page(client, db):
    from app.services import pdf_pages
    assert pdf_pages.page_count(b"%PDF-1.4 not really a pdf") == 0
    assert pdf_pages.render_page(b"%PDF-1.4 not really a pdf", 1) is None
    bill = _bill_with(client, db, _pdf(1), "conta.pdf", "application/pdf")
    import app.services.pdf_pages as pp
    real = pp.page_count
    pp.page_count = lambda data: 0
    try:
        html = client.get(f"/bills/{bill.id}/print?doc=1")
    finally:
        pp.page_count = real
    assert html.status_code == 200 and "Não foi possível preparar o PDF" in html.text
