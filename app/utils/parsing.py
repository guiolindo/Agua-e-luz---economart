"""Conversões tolerantes de texto -> tipos (formatos brasileiros)."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

MONTHS_PT = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
_MONTH_INDEX = {m: i + 1 for i, m in enumerate(MONTHS_PT)}


def normalize_uc(value: str | None) -> str:
    """'12.060.073.018-19' -> '1206007301819'. Chave de comparação entre UCs."""
    return re.sub(r"\D", "", value or "")


def parse_decimal(value) -> Decimal | None:
    """Aceita Decimal/int/float e textos como '20.505,00', 'R$ 1.234,5', '1234.56', '-4,99'."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:  # '1.234.567' -> milhar
        text = text.replace(".", "")
    elif re.fullmatch(r"-?\d{1,3}\.\d{3}", text):  # '20.505' em contexto BR = vinte mil (kWh)
        text = text.replace(".", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_int(value) -> int | None:
    d = parse_decimal(value)
    return int(d) if d is not None else None


def parse_date(value) -> date | None:
    """ISO (2026-10-09) ou BR (09/10/2026)."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?", text)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_reference(value) -> date | None:
    """Mês de referência -> dia 1. Aceita '2026-09', 'SET/2026', '09/2026', 'set/26', e datas completas."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.replace(day=1)
    text = str(value).strip().upper()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", text)
    if m:
        return _mk(int(m.group(1)), int(m.group(2)))
    m = re.fullmatch(r"([A-Z]{3})[/\-. ](\d{2,4})", text)
    if m and m.group(1) in _MONTH_INDEX:
        return _mk(_year(m.group(2)), _MONTH_INDEX[m.group(1)])
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{2,4})", text)
    if m:
        return _mk(_year(m.group(2)), int(m.group(1)))
    full = parse_date(text)
    return full.replace(day=1) if full else None


def _year(s: str) -> int:
    y = int(s)
    return 2000 + y if y < 100 else y


def _mk(y: int, m: int) -> date | None:
    try:
        return date(y, m, 1)
    except ValueError:
        return None


def parse_due_day(raw) -> tuple[int | None, bool]:
    """Dia de vencimento mensal (1-31). Devolve (valor, ok). Vazio = sem vencimento (None, True)."""
    text = ("" if raw is None else str(raw)).strip()
    if not text:
        return None, True
    if text.isdigit() and 1 <= int(text) <= 31:
        return int(text), True
    return None, False


def clean_str(value, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len] if max_len else text
