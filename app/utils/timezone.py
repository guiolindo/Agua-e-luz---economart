"""Fuso do negócio: horário de Brasília (America/Sao_Paulo, UTC−3).

O banco guarda instantes em UTC; tudo que o usuário vê ou que define "hoje" usa este fuso.
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


def local_now() -> datetime:
    return datetime.now(TZ)


def local_today() -> date:
    return local_now().date()


def to_local(value: datetime | None) -> datetime | None:
    """Converte um instante (UTC; sem tzinfo = UTC, como o SQLite devolve) para Brasília."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TZ)


def dt_br(value: datetime | None, seconds: bool = False, short: bool = False) -> str:
    """Filtro de template: '07/10/2026 21:05' (ou com segundos / sem o ano)."""
    local = to_local(value)
    if local is None:
        return "—"
    fmt = "%d/%m %H:%M" if short else "%d/%m/%Y %H:%M:%S" if seconds else "%d/%m/%Y %H:%M"
    return local.strftime(fmt)
