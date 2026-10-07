"""Autenticação, sessão, autorização, CSRF e utilidades de segurança."""
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User


class LoginRequired(Exception):
    pass


class MustChangePassword(Exception):
    pass


# ---------------------------------------------------------------- senhas
SCRYPT_LOGN = 15  # N=32768 (≈32 MB, ~100 ms). Hashes antigos (N=16384) continuam válidos e são atualizados no login.
_MAXMEM = 128 * 1024 * 1024


def _scrypt(password: str, salt: bytes, logn: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**logn, r=8, p=1, maxmem=_MAXMEM)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    return f"scrypt${SCRYPT_LOGN}${salt.hex()}${_scrypt(password, salt, SCRYPT_LOGN).hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        if len(parts) == 3:       # legado: scrypt$salt$digest (N=2^14)
            logn, salt, digest = 14, parts[1], parts[2]
        else:
            logn, salt, digest = int(parts[1]), parts[2], parts[3]
        return hmac.compare_digest(_scrypt(password, bytes.fromhex(salt), logn).hex(), digest)
    except (ValueError, TypeError, IndexError):
        return False


def needs_rehash(stored: str) -> bool:
    return not stored.startswith(f"scrypt${SCRYPT_LOGN}$")


_dummy: str | None = None


def verify_dummy(password: str) -> None:
    """Gasta o mesmo tempo de uma verificação real quando o usuário não existe (evita enumeração por tempo)."""
    global _dummy
    if _dummy is None:
        _dummy = hash_password("senha-chamariz-nunca-valida")
    verify_password(password, _dummy)


_COMMON = {"password", "senha", "123456", "12345678", "123456789", "1234567890", "qwerty", "qwertyuiop", "abc123",
           "admin", "administrador", "economart", "multicom", "trocar123", "mudar123", "senha123", "password1",
           "11111111", "00000000", "iloveyou", "letmein", "welcome"}


def validate_password(password: str, username: str = "", min_length: int | None = None) -> str | None:
    """Mensagem de erro (pt-BR) ou None se a senha é aceitável."""
    n = min_length or get_settings().min_password_length
    if len(password) < n:
        return f"A senha deve ter pelo menos {n} caracteres."
    if len(password) > 200:
        return "A senha é longa demais."
    low = password.lower()
    if low in _COMMON or re.sub(r"[^a-z]", "", low) in _COMMON:
        return "Essa senha é muito comum. Escolha outra."
    if username and username.lower() in low:
        return "A senha não pode conter o nome de usuário."
    if len(set(password)) < 5:
        return "A senha é muito repetitiva."
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 2:
        return "Use uma combinação de letras e números (ou símbolos)."
    return None


def generate_temp_password() -> str:
    return secrets.token_urlsafe(12)


# ---------------------------------------------------------------- IP / LGPD
_runtime_secret = ""


def configure(secret: str) -> None:
    global _runtime_secret
    _runtime_secret = secret


def client_ip(request: Request) -> str:
    """IP do cliente. Atrás de N proxies (Railway = 1) vale a entrada N-ésima a partir do FIM de X-Forwarded-For:
    entradas à esquerda podem ser forjadas pelo cliente, a última foi escrita pelo proxy de confiança."""
    count = get_settings().trusted_proxy_count
    xff = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if count > 0 and len(xff) >= count:
        return xff[-count][:64]
    return ((request.client.host if request.client else "") or "unknown")[:64]


def pseudonymize(value: str | None) -> str | None:
    """HMAC do dado pessoal (IP/usuário digitado) para o log: correlaciona sem guardar o valor bruto."""
    if not value:
        return None
    s = get_settings()
    key = (s.pseudonym_key or s.secret_key or _runtime_secret or "dev").encode() + b":pseudonym"
    return "h:" + hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:16]


# ---------------------------------------------------------------- sessão
def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def start_session(request: Request, user: User) -> None:
    """Nova sessão (descarta a anterior: evita session fixation) ligada à época atual do usuário."""
    request.session.clear()
    now = _now_ts()
    request.session.update(uid=user.id, epoch=user.epoch, iat=now, seen=now)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    s = get_settings()
    sess = request.session
    uid = sess.get("uid")
    user = db.get(User, uid) if uid else None
    now = _now_ts()
    valid = (
        user is not None and user.active
        and sess.get("epoch") == user.epoch                                   # logout/troca de senha/desativação revogam
        and now - int(sess.get("iat", 0)) <= s.session_max_hours * 3600       # duração máxima absoluta
        and now - int(sess.get("seen", 0)) <= s.session_idle_minutes * 60     # inatividade
    )
    if not valid:
        sess.clear()
        raise LoginRequired()
    sess["seen"] = now
    if user.must_change_password and request.url.path not in ("/account/password", "/logout"):
        raise MustChangePassword()
    return user


def admin_required(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administradores podem acessar esta área.")
    return user


def writer_required(user: User = Depends(current_user)) -> User:
    if not user.can_write:
        raise HTTPException(status_code=403, detail="Seu perfil é somente de consulta.")
    return user


# ---------------------------------------------------------------- CSRF
def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


async def verify_csrf(request: Request) -> None:
    expected = request.session.get("csrf")
    supplied = request.headers.get("x-csrf-token")
    if not supplied:
        form = await request.form()
        supplied = form.get("csrf_token")
    if not expected or not supplied or not hmac.compare_digest(str(supplied), expected):
        raise HTTPException(status_code=403, detail="Sessão expirada ou requisição inválida. Recarregue a página.")
