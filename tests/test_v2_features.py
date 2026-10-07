import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app import database
from app.models import ConsumerUnit, Document, EnergyBill, RecordType, Store
from app.models.mixins import utcnow
from app.services import import_service
from app.services.extraction_service import MockExtractor
from app.services.gemini_service import (ExtractionError, GeminiService, build_prompt, message_for_code,
                                         parse_response_text)
from app.services.matching_service import find_store_by_hint, type_for_utility
from app.services.retention_service import purge_expired_documents
from tests.test_app_flow import _form_from_review, _make_store, _upload

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "cemig_set_2026.json").read_text())


# ---------- retenção de 6 meses ----------
def test_retention_purges_only_old_documents_and_keeps_data(db):
    old = Document(filename="a.png", content_type="image/png", size=3, sha256="a", data=b"abc",
                   created_at=utcnow() - timedelta(days=200))
    new = Document(filename="b.png", content_type="image/png", size=3, sha256="b", data=b"abc",
                   created_at=utcnow() - timedelta(days=30))
    db.add_all([old, new])
    db.commit()
    assert purge_expired_documents(db) == 1
    db.expire_all()
    assert old.data is None and old.purged_at and old.filename == "a.png" and not old.available
    assert new.data == b"abc" and new.available
    assert purge_expired_documents(db) == 0  # idempotente


def test_expired_document_returns_410_and_bill_survives(client, png, db):
    _make_store(client)
    job = _upload(client, png)
    form = {**_form_from_review(client.get(f"/import/{job}/review").text), "unit_mode": "matched"}
    client.post(f"/import/{job}/confirm", form)
    bill = db.query(EnergyBill).one()
    doc = db.get(Document, bill.document_id)
    doc.created_at = utcnow() - timedelta(days=400)
    db.commit()
    purge_expired_documents(db)
    r = client.get(f"/documents/{bill.document_id}")
    assert r.status_code == 410
    page = client.get(f"/units/{bill.unit_id}").text
    assert "Original expirado" in page and "Ver documento original" not in page
    db.expire_all()
    assert str(db.get(EnergyBill, bill.id).total_value) == "20505.00"  # dados ficam


# ---------- Gemini: erros, retentativa, parsing ----------
def test_friendly_error_messages_never_leak_details():
    assert "Limite de uso" in message_for_code(429) and "indisponível" in message_for_code(503)
    assert "chave" in message_for_code(403).lower() and "modelo" in message_for_code(404).lower()


def test_parse_tolerates_markdown_wrapped_json():
    wrapped = "Aqui está:\n```json\n" + json.dumps(FIXTURE) + "\n```"
    assert parse_response_text(wrapped).total_value == 20505.0


def test_prompt_includes_catalog_and_no_guess_rules():
    p = build_prompt("- CD300 (CD Ribeirão) ← CD 300")
    assert "ZERO CHUTE" in p and "- CD300" in p and "À MÃO" in p
    assert "Catálogo" not in build_prompt(None)


def _fake_genai(monkeypatch, outcomes):
    """Substitui genai.Client; cada chamada consome um resultado (exceção ou texto)."""
    from google import genai

    calls = []

    class Models:
        def generate_content(self, **kw):
            calls.append(kw)
            out = outcomes.pop(0)
            if isinstance(out, Exception):
                raise out
            return type("R", (), {"text": out})()

    class Client:
        def __init__(self, **kw):
            self.models = Models()

    monkeypatch.setattr(genai, "Client", Client)
    return calls


def test_gemini_retries_on_429_then_succeeds(monkeypatch):
    from google.genai import errors

    calls = _fake_genai(monkeypatch, [errors.APIError(429, {"error": {"message": "x"}}), json.dumps(FIXTURE)])
    sleeps = []
    svc = GeminiService(api_key="k", model="m", sleep=sleeps.append)
    assert svc.extract(b"x", "image/png", "- CD300").total_value == 20505.0
    assert len(calls) == 2 and sleeps == [2]


def test_gemini_does_not_retry_on_auth_error_and_hides_details(monkeypatch):
    from google.genai import errors

    calls = _fake_genai(monkeypatch, [errors.APIError(403, {"error": {"message": "key=SECRET123"}})])
    with pytest.raises(ExtractionError) as exc:
        GeminiService(api_key="k", model="m", sleep=lambda s: None).extract(b"x", "image/png")
    assert len(calls) == 1 and "SECRET123" not in str(exc.value) and "chave" in str(exc.value).lower()


def test_gemini_gives_up_after_three_503(monkeypatch):
    from google.genai import errors

    calls = _fake_genai(monkeypatch, [errors.APIError(503, {}) for _ in range(3)])
    with pytest.raises(ExtractionError, match="indisponível"):
        GeminiService(api_key="k", model="m", sleep=lambda s: None).extract(b"x", "image/png")
    assert len(calls) == 3


# ---------- anotação à mão e distribuidora ----------
def test_store_hint_matches_code_alias_and_ignores_formatting(db):
    db.add_all([Store(code="CD300", aliases=["CD Rib Neves"]), Store(code="CD301", name="Campina Verde")])
    db.commit()
    assert find_store_by_hint(db, "CD 300").code == "CD300" and find_store_by_hint(db, "cd-rib neves").code == "CD300"
    assert find_store_by_hint(db, "campina  verde").code == "CD301"
    assert find_store_by_hint(db, "CD 30") is None and find_store_by_hint(db, "") is None  # nunca chuta


def test_type_for_utility(db):
    types = db.query(RecordType).all()
    assert type_for_utility(types, "COMPANHIA DE ELETRICIDADE DO ESTADO DA BAHIA - COELBA").code == "coelba"
    assert type_for_utility(types, "CEMIG Distribuição S.A.").code == "cemig"
    assert type_for_utility(types, "Outra Energia") is None


def test_review_warns_when_handwritten_store_differs_from_unit_store(client, png):
    _make_store(client, code="CD300", unit=None)   # a anotação à mão na foto diz "CD 300"
    _make_store(client, code="LOJA9")              # mas a UC lida está cadastrada em outra loja
    job = _upload(client, png)
    html = client.get(f"/import/{job}/review").text
    assert "anotação à mão" in html and "LOJA9" in html


def test_no_warning_when_handwritten_note_matches(client, png):
    _make_store(client, code="CD300")
    job = _upload(client, png)
    assert "anotação à mão" not in client.get(f"/import/{job}/review").text


def test_coelba_bill_creates_unit_with_coelba_type_and_hint_preselects_store(client, png, db, monkeypatch):
    payload = {"utility": "COELBA", "consumer_unit_number": "0123456789", "reference_month": "2026-09",
               "total_value": 3500.5, "consumption_kwh": 4200, "days": 30, "handwritten_note": "SAJ"}
    monkeypatch.setattr(import_service, "get_extractor", lambda: MockExtractor(payload))
    r = client.post("/stores", {"code": "CD400", "aliases": "SAJ, Santo Antonio"})
    store_id = int(r.headers["location"].split("/")[2])
    job = _upload(client, png)
    html = client.get(f"/import/{job}/review").text
    assert "Unidade consumidora não cadastrada" in html and f'<option value="{store_id}" selected>' in html
    form = {**_form_from_review(html), "unit_mode": "new", "new_store_id": str(store_id), "new_number": "0123456789"}
    assert client.post(f"/import/{job}/confirm", form).status_code == 303
    db.expire_all()
    unit = db.query(ConsumerUnit).one()
    bill = db.query(EnergyBill).one()
    assert unit.record_type.code == "coelba" and bill.record_type_id == unit.record_type_id
    assert bill.consumption_total == Decimal("4200") and bill.consumption_hp is None


def test_admin_can_create_bill_type_for_new_utility(client, db):
    client.post("/types", {"name": "ENERGISA", "kind": "bill"})
    rt = db.query(RecordType).filter_by(code="energisa").one()
    assert rt.is_bill and rt.fields == []


# ---------- relatório impresso ----------
def test_print_report_has_summary_blocks_and_variation(client, db):
    store_id = _make_store(client)
    unit = db.query(ConsumerUnit).one()
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    for m, v in ((8, "19536.31"), (9, "20505.00")):
        client.post("/manual", {"store_id": store_id, "unit_id": unit.id, "type_id": cemig.id, "reference": f"2026-{m:02d}",
                                "total_value": v, "days": "31"})
    html = client.get(f"/stores/{store_id}/report?start=2026-08&end=2026-09").text
    assert "Relatório por loja" in html and "CD300" in html and "↑ 4,96%" in html and "Dias de consumo" in html
    assert "R$ 20.505,00" in html and "window.print()" in html


# ---------- migração leve de colunas ----------
def test_ensure_columns_adds_missing_nullable_columns(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE stores (id INTEGER PRIMARY KEY, code VARCHAR(40), name VARCHAR(200), "
                       "location VARCHAR(200), notes TEXT, active BOOLEAN, created_at DATETIME, updated_at DATETIME)"))
    database.ensure_columns(eng)
    with eng.begin() as c:
        cols = {r[1] for r in c.execute(text("PRAGMA table_info(stores)"))}
    assert "aliases" in cols
