"""Login com bloqueio de conta, auditoria de acessos e troca de senha."""
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.models import User
from app.models.mixins import utcnow
from app.services import audit_service


@dataclass
class LoginResult:
    user: User | None
    ok: bool
    locked: bool = False


def _aware(dt):
    from datetime import timezone

    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def security_event(db: Session, request: Request, action: str, user_id: int | None, **details) -> None:
    audit_service.log(db, user_id, action, "auth", user_id,
                      {"ip": security.pseudonymize(security.client_ip(request)), **details})


def attempt_login(db: Session, request: Request, username: str, password: str) -> LoginResult:
    """Mensagem ao usuário é sempre a mesma (credencial errada, conta inexistente, bloqueada ou inativa): nada revela
    se a conta existe. O bloqueio temporário e o log de acessos ficam no servidor."""
    s = get_settings()
    now = utcnow()
    username = (username or "").strip()[:80]
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        security.verify_dummy(password)
        security_event(db, request, "login_failed", None, user=security.pseudonymize(username))
        db.commit()
        return LoginResult(None, False)

    blocked = _aware(user.blocked_until)
    if blocked and blocked > now:
        security.verify_dummy(password)  # mesmo custo de tempo
        security_event(db, request, "login_blocked", user.id)
        db.commit()
        return LoginResult(None, False, locked=True)

    # senha provisória (4 dígitos) é fraca de propósito: bloqueia mais cedo e expira
    limit = s.temp_max_login_attempts if user.must_change_password else s.max_login_attempts
    temp_expired = bool(user.must_change_password and user.temp_expires_at and _aware(user.temp_expires_at) < now)
    if temp_expired and security.verify_password(password, user.password_hash):
        security_event(db, request, "login_temp_expired", user.id)
        db.commit()
        return LoginResult(None, False)               # mesma mensagem genérica; o admin precisa redefinir
    if not user.active or not security.verify_password(password, user.password_hash):
        if user.active:
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= limit:
                user.blocked_until = now + timedelta(minutes=s.login_block_minutes)
                user.failed_attempts = 0
                security_event(db, request, "account_locked", user.id, minutes=s.login_block_minutes)
        security_event(db, request, "login_failed", user.id)
        db.commit()
        return LoginResult(None, False)

    user.failed_attempts, user.blocked_until, user.last_login = 0, None, now
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    security_event(db, request, "login", user.id)
    db.commit()
    return LoginResult(user, True)


def set_password(db: Session, user: User, new_password: str, *, must_change: bool = False) -> None:
    """Troca a senha e revoga todas as sessões existentes (incrementa a época).
    `must_change=True` = senha provisória: ganha validade (`temp_password_hours`) e obriga a troca no 1º acesso."""
    user.password_hash = security.hash_password(new_password)
    user.must_change_password = must_change
    user.temp_expires_at = utcnow() + timedelta(hours=get_settings().temp_password_hours) if must_change else None
    user.password_changed_at = utcnow()
    user.failed_attempts, user.blocked_until = 0, None
    user.session_epoch = user.epoch + 1


def revoke_sessions(user: User) -> None:
    user.session_epoch = user.epoch + 1
