from datetime import date
from decimal import Decimal

from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store
from app.services import chart_service
from app.services.duplicate_service import find_bill_duplicates, find_manual_duplicates
from app.services.matching_service import find_unit_by_number, suggest_similar_units


def _setup(db):
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    store = Store(code="CD300", name="CD Ribeirão das Neves")
    db.add(store)
    db.flush()
    unit = ConsumerUnit(store_id=store.id, number="12.060.073.018-19", number_normalized="1206007301819",
                        record_type_id=cemig.id)
    db.add(unit)
    db.commit()
    return cemig, store, unit


def _bill(db, unit, rtype, month, value, **kw):
    b = EnergyBill(unit_id=unit.id, record_type_id=rtype.id, reference=date(2026, month, 1),
                   total_value=Decimal(str(value)), **kw)
    db.add(b)
    db.commit()
    return b


def test_matching_unit_to_store_ignores_formatting(db):
    _, store, unit = _setup(db)
    for text in ("12.060.073.018-19", "1206007301819", " 12060073018-19 "):
        found = find_unit_by_number(db, text)
        assert found.id == unit.id and found.store.code == "CD300"
    assert find_unit_by_number(db, "99.999.999.999-99") is None and find_unit_by_number(db, None) is None


def test_similar_units_suggested_for_misread_digit(db):
    _setup(db)
    assert [u.number for u in suggest_similar_units(db, "12.060.073.018-18")] == ["12.060.073.018-19"]
    assert suggest_similar_units(db, "11.111.111.111-11") == []


def test_bill_duplicates_by_month_and_invoice(db):
    cemig, _, unit = _setup(db)
    b = _bill(db, unit, cemig, 9, 20505, invoice_number="436179492")
    assert find_bill_duplicates(db, unit.id, date(2026, 9, 17))[0].id == b.id           # mesmo mês
    assert find_bill_duplicates(db, unit.id, date(2026, 10, 1), "436179492")[0].id == b.id  # mesma nota
    assert find_bill_duplicates(db, unit.id, date(2026, 8, 1), "other") == []
    assert find_bill_duplicates(db, unit.id, date(2026, 9, 1), exclude_id=b.id) == []


def test_manual_duplicates(db):
    _, store, _ = _setup(db)
    ll = db.query(RecordType).filter_by(code="ll-energia").one()
    db.add(ManualRecord(store_id=store.id, record_type_id=ll.id, reference=date(2026, 1, 1), value=Decimal(100)))
    db.commit()
    assert len(find_manual_duplicates(db, store.id, None, ll.id, date(2026, 1, 15))) == 1
    assert find_manual_duplicates(db, store.id, None, ll.id, date(2026, 2, 1)) == []


def test_chart_series_variation_and_highlight(db):
    cemig, store, unit = _setup(db)
    other = ConsumerUnit(store_id=store.id, number="12.060.073.019-00", number_normalized="1206007301900")
    db.add(other)
    db.commit()
    _bill(db, unit, cemig, 8, "19536.31", days=31, demand_hfp=Decimal(154))
    _bill(db, unit, cemig, 9, "20505.00", days=30, consumption_hp=Decimal(5388), consumption_hfp=Decimal(58372))
    _bill(db, other, cemig, 9, "1000")
    db.refresh(store)
    data = chart_service.build_chart(db, store, record_type=cemig, indicator_key="total_value", view="units",
                                     start=date(2026, 7, 1), end=date(2026, 9, 1), highlight_unit_id=unit.id)
    assert data["labels"] == ["JUL/26", "AGO/26", "SET/26"]
    s = {x["id"]: x for x in data["series"]}
    assert s[unit.id]["data"] == [None, 19536.31, 20505.0] and s[unit.id]["highlight"] and not s[other.id]["highlight"]
    assert s[unit.id]["variations"][2]["text"] == "↑ 4,96%" and s[unit.id]["variations"][1]["text"] == "—"
    assert any("Dias: 30" in line for line in s[unit.id]["lines"][2])
    assert any("Consumo HP" in line for line in s[unit.id]["lines"][2])
    cons = chart_service.build_chart(db, store, record_type=cemig, indicator_key="consumption_total",
                                     start=date(2026, 9, 1), end=date(2026, 9, 1))
    assert cons["series"][0]["data"] == [63760.0]


def test_store_summary_totals_by_type_and_month(db):
    cemig, store, unit = _setup(db)
    ll = db.query(RecordType).filter_by(code="ll-energia").one()
    _bill(db, unit, cemig, 8, 100)
    _bill(db, unit, cemig, 9, 110)
    db.add(ManualRecord(store_id=store.id, record_type_id=ll.id, reference=date(2026, 9, 1), value=Decimal(40)))
    db.commit()
    db.refresh(store)
    s = chart_service.store_summary(db, store, date(2026, 8, 1), date(2026, 9, 1))
    assert s["totals"] == [Decimal(100), Decimal(150)] and s["grand_total"] == Decimal(250)
    assert s["variations"][1].text == "↑ 50,00%"


def test_manual_type_indicators_follow_type_fields(db):
    gerador = db.query(RecordType).filter_by(code="gerador").one()
    assert [i.key for i in chart_service.indicators_for_type(gerador)] == ["value", "horas", "litros"]
