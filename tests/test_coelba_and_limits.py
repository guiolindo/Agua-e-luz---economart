import io
import json
import logging
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from app.config import Settings
from app.models import ConsumerUnit, EnergyBill, Import, RecordType
from app.models.mixins import utcnow
from app.services import import_service
from app.services.extraction_service import MockExtractor
from app.services.gemini_service import parse_response_text
from app.services.import_service import expire_if_stale
from app.services.matching_service import (
    find_unit_by_number,
    is_stamp,
    type_for_utility,
)
from app.utils.images import prepare_for_model
from app.utils.log_safety import RedactKeysFilter, redact
from app.utils.uploads import UploadError, validate_upload
from tests.test_app_flow import _form_from_review, _make_store, _upload

COELBA = json.loads((Path(__file__).parent / "fixtures" / "coelba_ago_2026.json").read_text())


# ---------- conta real da Coelba (fixture a partir da foto) ----------
def test_coelba_fixture_parses_and_items_sum_to_total():
    e = parse_response_text(json.dumps(COELBA))
    assert e.consumer_unit_number == "9.089.187.028-65" and e.total_value == 107556.36 and e.days == 31
    assert round(sum(i.value for i in e.line_items), 2) == e.total_value      # confere item a item
    assert any(i.value == -184.37 for i in e.line_items)                      # sinal negativo à direita ("184,37-")
    assert e.handwritten_note is None                                          # carimbo "LANÇADO" não é anotação


def test_coelba_recognised_by_brand_or_legal_name(db):
    types = db.query(RecordType).all()
    assert type_for_utility(types, "Neoenergia Coelba").code == "coelba"
    assert type_for_utility(types, "COMPANHIA DE ELETRICIDADE DO ESTADO DA BAHIA").code == "coelba"
    assert is_stamp("LANÇADO") and not is_stamp("CD 300")


def test_coelba_import_creates_unit_typed_coelba_with_hp_hfp(client, png, db, monkeypatch):
    monkeypatch.setattr(import_service, "get_extractor", lambda: MockExtractor(COELBA))
    store_id = _make_store(client, code="LOJA22", unit=None)
    job = _upload(client, png)
    html = client.get(f"/import/{job}/review").text
    assert "Unidade consumidora não cadastrada" in html and "FEIRA DE SANTANA" in html     # endereço exibido
    assert "anotação à mão" not in html.lower()
    form = {**_form_from_review(html), "unit_mode": "new", "new_store_id": str(store_id), "new_number": "9.089.187.028-65"}
    assert client.post(f"/import/{job}/confirm", form).status_code == 303
    db.expire_all()
    unit, bill = db.query(ConsumerUnit).one(), db.query(EnergyBill).one()
    assert unit.record_type.code == "coelba" and unit.number_normalized == "908918702865"
    assert bill.consumption_total == Decimal("227784.69") and bill.demand_hfp == Decimal("539.28")
    assert str(bill.total_value) == "107556.36" and bill.reference.month == 8 and len(bill.line_items) == 14
    assert find_unit_by_number(db, "9089187028-65").id == unit.id


# ---------- imagem enviada ao modelo ----------
def _jpeg(size, exif_orientation=None):
    img = Image.new("RGB", size, "white")
    buf = io.BytesIO()
    if exif_orientation:
        ex = img.getexif()
        ex[0x0112] = exif_orientation
        img.save(buf, "JPEG", exif=ex)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def test_big_photo_is_downscaled_small_is_untouched_pdf_passes_through():
    big = _jpeg((6000, 4000))
    out, mime = prepare_for_model(big, "image/jpeg")
    assert max(Image.open(io.BytesIO(out)).size) == 3000 and mime == "image/jpeg"
    small = _jpeg((800, 600))
    assert prepare_for_model(small, "image/jpeg")[0] == small
    assert prepare_for_model(b"%PDF-1.4", "application/pdf") == (b"%PDF-1.4", "application/pdf")
    assert prepare_for_model(b"garbage", "image/png") == (b"garbage", "image/png")     # nunca falha


def test_exif_rotation_is_applied():
    out, _ = prepare_for_model(_jpeg((400, 200), exif_orientation=6), "image/jpeg")
    assert Image.open(io.BytesIO(out)).size == (200, 400)


def test_pdf_with_too_many_pages_rejected():
    pdf = b"%PDF-1.4\n" + b"<< /Type /Page >>\n" * 40 + b"<< /Type /Pages >>"
    with pytest.raises(UploadError, match="páginas"):
        validate_upload("contas.pdf", pdf, 10_000_000)
    ok = b"%PDF-1.4\n" + b"<< /Type /Page >>\n" * 2 + b"<< /Type /Pages >>"
    assert validate_upload("conta.pdf", ok, 10_000_000)[1] == "application/pdf"


# ---------- travamentos / limites ----------
def test_stale_processing_import_is_failed_and_retryable(client, png, db, monkeypatch):
    monkeypatch.setattr(import_service, "run_import", lambda *a, **k: None)  # simula processo que morreu
    from app.routes import imports as routes
    monkeypatch.setattr(routes, "run_import", lambda *a, **k: None)
    job_id = _upload(client, png)
    job = db.get(Import, job_id)
    assert job.status == "processing" and not expire_if_stale(db, job)
    job.updated_at = utcnow() - timedelta(minutes=30)
    db.commit()
    s = client.get(f"/import/{job_id}/status").json()
    assert s["status"] == "failed" and "Tentar novamente" in s["error"]


def test_obsolete_model_is_replaced_and_current_kept():
    assert Settings(gemini_model="gemini-2.5-flash-lite").gemini_model == "gemini-3.5-flash-lite"
    assert Settings(gemini_model="gemini-3.5-flash").gemini_model == "gemini-3.5-flash"
    assert Settings().max_upload_mb == 12


def test_api_keys_are_redacted_from_logs(caplog):
    fake = "AIza" + "x" * 35
    assert fake not in redact(f"GET https://x/v1?key={fake}&a=1 x-goog-api-key: {fake}")
    assert "SEGREDO12345" not in redact("falha SEGREDO12345", ("SEGREDO12345",))
    rec = logging.LogRecord("t", logging.ERROR, __file__, 1, "erro em %s", (f"?key={fake}",), None)
    RedactKeysFilter().filter(rec)
    assert fake not in rec.getMessage()
