"""Redige chaves de API de qualquer log (mensagens e tracebacks)."""
import logging
import re
import traceback

_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)(x-goog-api-key['\"]?\s*[:=]\s*['\"]?)[^\s'\",&]+"),
    re.compile(r"(?i)([?&]key=)[^&\s'\"]+"),
]


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    for s in secrets:
        if s and len(s) > 6:
            text = text.replace(s, "[REDACTED]")
    text = _PATTERNS[0].sub("[REDACTED]", text)
    text = _PATTERNS[1].sub(r"\1[REDACTED]", text)
    return _PATTERNS[2].sub(r"\1[REDACTED]", text)


class RedactKeysFilter(logging.Filter):
    def __init__(self, secrets: tuple[str, ...] = ()):
        super().__init__()
        self.secrets = secrets

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage(), self.secrets)
        record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = redact("".join(traceback.format_exception(*record.exc_info)), self.secrets)
        return True


def install_log_redaction(*secrets: str) -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO)
    flt = RedactKeysFilter(secrets)
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        for h in logging.getLogger(name).handlers:
            if not any(isinstance(f, RedactKeysFilter) for f in h.filters):
                h.addFilter(flt)
