"""Arquivo que não é conta de energia: barrado, nada lançado, bytes apagados."""
import pytest

from app.models import AuditLog, Document, EnergyBill, Import
from app.schemas.extraction import BillExtraction
from app.services import import_service, extraction_service
from app.services.extraction_service import MockExtractor
from app.services.import_service import rejection_reason
from tests.test_app_flow import _make_store, _upload


@pytest.mark.parametrize("payload", [
    {"is_energy_bill": False, "not_bill_reason": "cardápio de restaurante"},
    {},                                                      # a IA não leu nada que identifique uma conta
    {"is_energy_bill": True, "customer_name": "Fulano"},     # disse que é conta, mas sem UC, valor, mês, nota nem itens
])
def test_non_bill_is_rejected_and_file_is_deleted(client, png, db, monkeypatch, payload):
    _make_store(client)
    monkeypatch.setattr(import_service, "get_extractor", lambda: MockExtractor(payload=payload))
    job_id = _upload(client, png)
    page = client.get(f"/import/{job_id}", follow_redirects=False)
    assert page.status_code == 200 and "Arquivo barrado" in page.text and "não parece ser uma conta" in page.text
    db.expire_all()
    job = db.get(Import, job_id)
    assert job.status == "rejected" and job.extracted is None and job.bill_id is None
    doc = db.get(Document, job.document_id)
    assert doc.data is None and not doc.available                    # foto/PDF apagado: não ficou guardado
    assert db.query(EnergyBill).count() == 0
    ev = db.query(AuditLog).filter_by(action="import_rejected").one()
    assert ev.details["bytes_deleted"] is True
    assert client.get(f"/import/{job_id}/review", follow_redirects=False).status_code in (303, 400, 404)  # sem conferência
    assert "Barrada" in client.get("/import").text


def test_real_bill_is_not_rejected(client, png, db):
    _make_store(client)
    job_id = _upload(client, png)
    assert client.get(f"/import/{job_id}", follow_redirects=False).status_code == 303   # vai direto à conferência
    db.expire_all()
    assert db.get(Import, job_id).status == "ready" and db.get(Document, db.get(Import, job_id).document_id).available


def test_rejection_rules_unit():
    assert rejection_reason(BillExtraction()) is not None
    assert rejection_reason(BillExtraction(is_energy_bill=False)) == "documento que não é conta de energia"
    assert rejection_reason(BillExtraction(total_value=10.5)) is None
    assert rejection_reason(BillExtraction(consumer_unit_number="1-2")) is None
