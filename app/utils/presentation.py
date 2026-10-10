"""Janela da apresentação do sistema: aberta até PRESENTATION_UNTIL (padrão: sexta 16/10/2026, 17h, Brasília)."""
from datetime import datetime

from app.config import get_settings
from app.utils.timezone import TZ, local_now


def presentation_deadline() -> datetime | None:
    raw = (get_settings().presentation_until or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None                                   # valor inválido: desliga (nunca deixa aberta por engano)
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def presentation_open() -> bool:
    deadline = presentation_deadline()
    return deadline is not None and local_now() < deadline


def presentation_until_label() -> str:
    deadline = presentation_deadline()
    if deadline is None:
        return ""
    local = deadline.astimezone(TZ)
    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    hora = f"{local.hour}h" if local.minute == 0 else f"{local.hour}h{local.minute:02d}"
    return f"{dias[local.weekday()]}, {local:%d/%m/%Y}, às {hora}"
