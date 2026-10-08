import json
from decimal import Decimal
from pathlib import Path

from app.models import ConsumerUnit, EnergyBill, RecordType
from app.services import import_service
from app.services.extraction_service import MockExtractor
from app.services.gemini_service import parse_response_text
from app.services.matching_service import type_for_utility
from tests.test_app_flow import _form_from_review, _make_store, _upload

ENERGISA = json.loads((Path(__file__).parent / "fixtures" / "energisa_set_2026.json").read_text())


def test_energisa_fixture_parses_and_items_sum_to_total():
    e = parse_response_text(json.dumps(ENERGISA))
    assert e.consumer_unit_number == "461.615.050-40" and e.total_value == 93.28 and e.days == 32
    assert round(sum(i.value for i in e.line_items), 2) == e.total_value
    assert e.consumption_kwh == 62 and e.consumption_hp_kwh is None and e.demand_hfp_kw is None


def test_energisa_recognised_by_brand_or_legal_name(db):
    types = db.query(RecordType).all()
    assert type_for_utility(types, "ENERGISA MINAS RIO - DISTRIBUIDORA DE ENERGIA S.A.").code == "energisa"
    assert type_for_utility(types, "Energisa").code == "energisa"
    assert type_for_utility(types, "CEMIG DISTRIBUICAO S.A.").code == "cemig"   # não confunde as marcas


def test_energisa_import_creates_unit_typed_energisa_with_single_consumption(client, png, db, monkeypatch):
    monkeypatch.setattr(import_service, "get_extractor", lambda: MockExtractor(ENERGISA))
    store_id = _make_store(client, code="LOJA33", unit=None)
    job = _upload(client, png)
    html = client.get(f"/import/{job}/review").text
    assert "Unidade consumidora não cadastrada" in html
    form = {**_form_from_review(html), "unit_mode": "new", "new_store_id": str(store_id), "new_number": "461.615.050-40"}
    assert client.post(f"/import/{job}/confirm", form).status_code == 303
    db.expire_all()
    unit, bill = db.query(ConsumerUnit).one(), db.query(EnergyBill).one()
    assert unit.record_type.code == "energisa" and unit.number_normalized == "46161505040"
    assert bill.consumption_total == Decimal("62") and bill.consumption_hp is None
    assert str(bill.total_value) == "93.28" and bill.reference.month == 9 and bill.due_date.day == 11
