from datetime import date
from decimal import Decimal

import pytest

from app.utils.parsing import normalize_uc, parse_date, parse_decimal, parse_reference
from app.utils.uploads import UploadError, validate_upload


@pytest.mark.parametrize("raw,expected", [
    ("20.505,00", "20505.00"), ("R$ 1.234,5", "1234.5"), ("-4,99", "-4.99"), ("58.372", "58372"),
    ("1234.56", "1234.56"), (20505.0, "20505.0"), ("", None), ("abc", None), (None, None),
])
def test_parse_decimal(raw, expected):
    got = parse_decimal(raw)
    assert (got is None) if expected is None else got == Decimal(expected)


@pytest.mark.parametrize("raw", ["2026-09", "SET/2026", "set/26", "09/2026", "2026-09-30", date(2026, 9, 17)])
def test_parse_reference(raw):
    assert parse_reference(raw) == date(2026, 9, 1)


def test_parse_reference_invalid():
    assert parse_reference("XYZ/2026") is None and parse_reference("2026-13") is None


def test_parse_date_iso_and_br():
    assert parse_date("2026-10-09") == date(2026, 10, 9) and parse_date("09/10/2026") == date(2026, 10, 9)
    assert parse_date("31/02/2026") is None


def test_normalize_uc():
    assert normalize_uc("12.060.073.018-19") == "1206007301819" == normalize_uc(" 1206007301819 ")


def test_upload_validation(png):
    assert validate_upload("conta.PNG", png, 1000)[1] == "image/png"
    with pytest.raises(UploadError):
        validate_upload("conta.png", b"MZ not an image", 1000)  # conteúdo não bate
    with pytest.raises(UploadError):
        validate_upload("conta.exe", png, 1000)
    with pytest.raises(UploadError):
        validate_upload("conta.png", png, 10)  # excede limite
    with pytest.raises(UploadError):
        validate_upload("conta.jpg", png, 1000)  # extensão diverge do conteúdo
