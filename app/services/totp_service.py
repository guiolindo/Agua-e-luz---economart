"""2FA por TOTP (RFC 6238) — compatível com Google Authenticator, Microsoft Authenticator, Authy etc.

Só administradores. O segredo é cifrado em repouso com a chave dos documentos (quando existe). Cada código vale uma
única vez (anti-replay por `totp_last_step`) e há 8 códigos de recuperação de uso único (guardados só como hash).
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from app import security
from app.models import User
from app.services import crypto_service

PERIOD, DIGITS, WINDOW = 30, 6, 1     # ±30 s de tolerância para relógio do celular
ISSUER = "Economart Energia"
RECOVERY_CODES = 8


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _hotp(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    return f"{(struct.unpack('>I', mac[off:off + 4])[0] & 0x7FFFFFFF) % 10**DIGITS:0{DIGITS}d}"


def _step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // PERIOD)


def code_at(secret: str, now: float | None = None) -> str:
    return _hotp(secret, _step(now))


def seal(secret: str) -> str:
    data, encrypted = crypto_service.encrypt(secret.encode())
    return ("enc:" if encrypted else "raw:") + data.decode()


def unseal(stored: str) -> str:
    kind, _, body = stored.partition(":")
    return crypto_service.decrypt(body.encode(), kind == "enc").decode()


def provisioning_uri(username: str, secret: str) -> str:
    label = quote(f"{ISSUER}:{username}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&algorithm=SHA1&digits={DIGITS}&period={PERIOD}"


def qr_svg(uri: str) -> str:
    import segno

    return segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#111111", light="#ffffff", title="QR Code do 2FA")


def start_enrollment(user: User) -> str:
    """Gera um segredo novo (ainda inativo até confirmar um código) e devolve em claro para exibir uma vez."""
    secret = new_secret()
    user.totp_secret, user.totp_enabled, user.totp_last_step = seal(secret), False, None
    return secret


def current_secret(user: User) -> str | None:
    return unseal(user.totp_secret) if user.totp_secret else None


def check_code(user: User, code: str, now: float | None = None) -> bool:
    """Confere o código de 6 dígitos (tolerância ±1 janela) e o consome: o mesmo código não vale duas vezes."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    secret = current_secret(user)
    if not secret or len(code) != DIGITS:
        return False
    cur = _step(now)
    for step in range(cur - WINDOW, cur + WINDOW + 1):
        if hmac.compare_digest(_hotp(secret, step), code) and step > (user.totp_last_step or 0):
            user.totp_last_step = step
            return True
    return False


def _hash_recovery(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").strip().lower().encode()).hexdigest()


def new_recovery_codes(user: User) -> list[str]:
    codes = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(RECOVERY_CODES)]
    user.totp_recovery = [_hash_recovery(c) for c in codes]
    return codes


def use_recovery_code(user: User, code: str) -> bool:
    h, left = _hash_recovery(code or ""), list(user.totp_recovery or [])
    for stored in left:
        if hmac.compare_digest(stored, h):
            left.remove(stored)
            user.totp_recovery = left
            return True
    return False


def disable(user: User) -> None:
    user.totp_secret, user.totp_enabled, user.totp_last_step, user.totp_recovery = None, False, None, None
    user.session_epoch = user.epoch + 1
