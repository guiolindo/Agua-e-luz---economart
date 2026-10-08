import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store
from app.seed import seed
from app.services import chart_service, dashboard_service, import_service
from app.services.extraction_service import MockExtractor
from app.services.gemini_service import parse_response_text
from app.services.matching_service import type_for_utility
from tests.test_app_flow import _form_from_review, _make_store, _upload

GT = json.loads((Path(__file__).parent / "fixtures" / "cemig_gt_ago_2026.json").read_text())


def _gt_type(db):
    return db.scalar(select(RecordType).where(RecordType.code == "cemig-geracao"))


def test_gt_fixture_parses_and_items_sum_to_total():
    e = parse_response_text(json.dumps(GT))
    assert e.consumer_unit_number == "3014272029" and e.total_value == 53376.83 and e.days == 31
    assert round(sum(i.value for i in e.line_items), 2) == e.total_value
    assert e.consumption_hp_kwh + e.consumption_hfp_kwh == 128783          # bate com a quantidade faturada
    assert e.handwritten_note is None                                        # carimbo LANÇADO não é anotação


def test_gt_is_bill_type_and_not_confused_with_distribution(db):
    types = db.query(RecordType).all()
    assert _gt_type(db).is_bill
    assert type_for_utility(types, "Cemig Geração e Transmissão S.A.").code == "cemig-geracao"
    assert type_for_utility(types, "CEMIG GERAÇÃO E TRANSMISSÃO S.A").code == "cemig-geracao"
    assert type_for_utility(types, "CEMIG DISTRIBUIÇÃO S.A.").code == "cemig"
    assert type_for_utility(types, "CEMIG").code == "cemig"


def test_seed_converts_legacy_manual_type_without_touching_records(db):
    rt = _gt_type(db)
    store = Store(code="LEG1", name="Legado")
    db.add(store)
    db.flush()
    db.add(ManualRecord(store_id=store.id, record_type_id=rt.id, reference=date(2026, 7, 1), value=Decimal("1000.00"), data={}))
    rt.kind = "manual"            # banco de produção antigo
    db.commit()
    seed(db)
    db.expire_all()
    assert _gt_type(db).kind == "bill" and db.query(ManualRecord).filter_by(store_id=store.id).count() == 1
    seed(db)                      # idempotente
    assert _gt_type(db).kind == "bill"


def test_gt_import_creates_unit_typed_gt(client, png, db, monkeypatch):
    monkeypatch.setattr(import_service, "get_extractor", lambda: MockExtractor(GT))
    store_id = _make_store(client, code="LOJA44", unit=None)
    job = _upload(client, png)
    html = client.get(f"/import/{job}/review").text
    assert "Unidade consumidora não cadastrada" in html
    form = {**_form_from_review(html), "unit_mode": "new", "new_store_id": str(store_id), "new_number": "3014272029"}
    assert client.post(f"/import/{job}/confirm", form).status_code == 303
    db.expire_all()
    unit, bill = db.query(ConsumerUnit).one(), db.query(EnergyBill).one()
    assert unit.record_type.code == "cemig-geracao" and unit.number_normalized == "3014272029"
    assert str(bill.total_value) == "53376.83" and bill.reference == date(2026, 8, 1) and bill.consumption_total == Decimal("128783")


def _legacy_setup(db):
    """Loja com histórico manual antigo (sem unidade) + uma conta nova do tipo G&T com unidade."""
    rt = _gt_type(db)
    store = Store(code="LEG2", name="Legado 2")
    db.add(store)
    db.flush()
    unit = ConsumerUnit(store_id=store.id, number="3014272029", number_normalized="3014272029", record_type_id=rt.id)
    db.add(unit)
    db.flush()
    old = ManualRecord(store_id=store.id, record_type_id=rt.id, reference=date(2026, 7, 1), value=Decimal("40000.00"), data={})
    db.add(old)
    db.add(EnergyBill(unit_id=unit.id, record_type_id=rt.id, reference=date(2026, 8, 1), total_value=Decimal("53376.83"),
                      consumption_hp=Decimal("12159"), consumption_hfp=Decimal("116624"), source="import", line_items=[]))
    db.commit()
    return store, unit, rt, old


def test_legacy_manual_history_stays_in_charts_and_summary(db):
    store, unit, rt, old = _legacy_setup(db)
    chart = chart_service.build_chart(db, store, record_type=rt, indicator_key="total_value", start=date(2026, 7, 1), end=date(2026, 8, 1))
    by_label = {s["label"]: s["data"] for s in chart["series"]}
    assert by_label["Sem unidade"] == [40000.0, None] and by_label["3014272029"] == [None, 53376.83]
    summary = chart_service.store_summary(db, store, date(2026, 7, 1), date(2026, 8, 1))
    row = next(r for r in summary["rows"] if r["type"].code == "cemig-geracao")
    assert [str(v) for v in row["values"]] == ["40000.00", "53376.83"]       # uma linha só, histórico + conta


def test_legacy_record_still_editable_as_manual(client, db):
    store, unit, rt, old = _legacy_setup(db)
    page = client.get(f"/manual?record={old.id}")
    assert page.status_code == 200 and 'name="f_energia_kwh"' in page.text
    form = {"csrf_token": _form_from_review(page.text).get("csrf_token", ""), "edit_record": str(old.id), "store_id": str(store.id),
            "unit_id": "", "type_id": str(rt.id), "reference": "2026-07", "value": "41000,00", "notes": ""}
    res = client.post("/manual", form)
    assert res.status_code == 303, res.text[:300]
    db.expire_all()
    assert db.get(ManualRecord, old.id).value == Decimal("41000.00")


def test_no_false_pending_when_bill_replaces_manual_entry(db):
    store, unit, rt, old = _legacy_setup(db)
    items = dashboard_service.pending_items(db, date(2026, 8, 1), date(2026, 7, 1))
    assert not [i for i in items if i["type"].code == "cemig-geracao" and "mês anterior" in i["text"]]


def test_rs_per_kwh_ignores_gt_bill_so_kwh_is_not_counted_twice(db):
    from app.services import executive_service
    store, unit, rt, old = _legacy_setup(db)
    dist = db.scalar(select(RecordType).where(RecordType.code == "cemig"))
    unit_d = ConsumerUnit(store_id=store.id, number="1206007301819", number_normalized="1206007301819", record_type_id=dist.id)
    db.add(unit_d)
    db.flush()
    db.add(EnergyBill(unit_id=unit_d.id, record_type_id=dist.id, reference=date(2026, 8, 1), total_value=Decimal("20000.00"),
                      consumption_hp=Decimal("10000"), consumption_hfp=Decimal("30000"), source="import", line_items=[]))
    db.commit()
    data = executive_service.build(db, date(2026, 8, 1), date(2026, 8, 1))
    assert data["kpi"]["rs_kwh"] == 0.5          # 20.000 / 40.000 kWh só da distribuição; a G&T (128.783 kWh) fica fora
