import json
from pathlib import Path

import pytest

from app.schemas.forms import extraction_to_form, low_confidence_fields, parse_bill_form
from app.services.extraction_service import MockExtractor
from app.services.gemini_service import (
    ExtractionError,
    GeminiService,
    parse_response_text,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cemig_set_2026.json"


def test_parse_valid_gemini_response():
    e = parse_response_text(FIXTURE.read_text())
    assert e.consumer_unit_number == "12.060.073.018-19" and e.total_value == 20505.00 and len(e.line_items) == 8


def test_line_items_sum_to_total():
    e = parse_response_text(FIXTURE.read_text())
    assert round(sum(i.value for i in e.line_items), 2) == e.total_value


@pytest.mark.parametrize("text", [None, "", "not json", '{"total_value": "abc"}'])
def test_invalid_gemini_response_raises(text):
    with pytest.raises(ExtractionError):
        parse_response_text(text)


def test_missing_fields_stay_null():
    e = parse_response_text(json.dumps({"consumer_unit_number": "1"}))
    assert e.total_value is None and e.due_date is None and e.line_items == []
    assert {"reference", "total_value", "due_date"} <= low_confidence_fields(e)


def test_gemini_without_key_fails_gracefully():
    with pytest.raises(ExtractionError, match="GEMINI_API_KEY"):
        GeminiService(api_key="").extract(b"x", "image/png")


def test_form_roundtrip_brazilian_formats():
    form = extraction_to_form(MockExtractor().extract(b"", "image/png"))
    assert form["reference"] == "2026-09" and form["total_value"] == "20505,00" and form["consumption_hfp"] == "58372"
    values, errors = parse_bill_form(form)
    assert not errors and str(values["total_value"]) == "20505.00" and values["reference"].month == 9


def test_form_validation_errors():
    _, errors = parse_bill_form({"reference": "", "total_value": "-1", "due_date": "32/13/2026", "days": "9999"})
    assert {"reference", "total_value", "due_date", "days"} <= set(errors)
