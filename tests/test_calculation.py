from datetime import date
from decimal import Decimal

from app.services.calculation_service import add_months, month_range, variation


def test_variation_up_matches_example_from_bill():
    v = variation(Decimal("19536.31"), Decimal("20505.00"))
    assert v.pct == Decimal("4.96") and v.direction == "up" and v.text == "↑ 4,96%"


def test_variation_down_and_flat():
    assert variation(100, 91.79).text == "↓ 8,21%"
    assert variation(100, 100).direction == "flat"
    assert variation(100, 100).text == "→ 0,00%"


def test_variation_without_base_is_none():
    assert variation(None, 10).pct is None and variation(0, 10).pct is None and variation(10, None).text == "—"


def test_month_range_crosses_year():
    r = month_range(date(2025, 11, 15), date(2026, 2, 1))
    assert r == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]
    assert add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
