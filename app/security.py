import hashlib
import hmac
import os
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


class LoginRequired(Exception):
    pass


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(candidate.hex(), digest)
    except (ValueError, TypeError):
        return False


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if user is None or not user.active:
        request.session.clear()
        raise LoginRequired()
    return user


def admin_required(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas administradores podem acessar esta área.")
    return user


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
