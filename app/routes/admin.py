from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.models.mixins import utcnow
from app.database import get_db
from app.models import AuditLog, User
from app.security import admin_required, verify_csrf
from app.services import audit_service, auth_service, totp_service
from app.web import flash, render

router = APIRouter()
ROLES = {
    "operator": "Funcionário — responsável por toda a gestão de energia (lojas, unidades, contas, lançamentos)",
    "director": "Diretoria — painel executivo, só consulta",
    "viewer": "Consulta — só visualiza e imprime",
    "admin": "Administrador — cria usuários e perfis, auditoria",
}


def _active_admins(db: Session) -> int:
    return len(db.scalars(select(User).where(User.role == "admin", User.active.is_(True))).all())


def _page(request, db, user, **extra):
    from datetime import datetime, timezone

    users = db.scalars(select(User).order_by(User.username)).all()
    now = utcnow()
    blocked = {u.id: until for u in users if (until := auth_service.is_blocked(u, now))}
    return render(request, "admin/users.html", user=user, users=users, blocked=blocked,
                  roles=ROLES, temp_hours=get_settings().temp_password_hours,
                  now_naive=datetime.now(timezone.utc).replace(tzinfo=None), **extra)


@router.get("/admin/users")
def users_page(request: Request, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    return _page(request, db, user)


@router.post("/admin/users", dependencies=[Depends(verify_csrf)])
def user_create(request: Request, username: str = Form(..., max_length=80), role: str = Form("operator"),
                user: User = Depends(admin_required), db: Session = Depends(get_db)):
    username = username.strip()
    if not username or len(username) < 3:
        flash(request, "Informe um nome de usuário com pelo menos 3 caracteres.", "error")
    elif db.scalar(select(User).where(User.username == username)):
        flash(request, "Esse usuário já existe.", "error")
    else:
        temp = security.generate_temp_password()
        new = User(username=username, password_hash=security.hash_password(temp),
                   role=role if role in ROLES else "operator", must_change_password=True,
                   temp_expires_at=utcnow() + timedelta(hours=get_settings().temp_password_hours))
        db.add(new)
        db.flush()
        audit_service.log(db, user.id, "create", "user", new.id, {"username": username, "role": new.role})
        db.commit()
        # exibida uma única vez, direto na resposta (nunca em cookie/flash)
        return _page(request, db, user, temp_for=username, temp_password=temp)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/reset-password", dependencies=[Depends(verify_csrf)])
def user_reset(request: Request, user_id: int, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        return RedirectResponse("/admin/users", status_code=303)
    temp = security.generate_temp_password()
    auth_service.set_password(db, target, temp, must_change=True)  # revoga sessões e desbloqueia
    audit_service.log(db, user.id, "password_reset", "user", target.id, {"by_admin": True})
    db.commit()
    return _page(request, db, user, temp_for=target.username, temp_password=temp)


@router.post("/admin/users/{user_id}/unlock", dependencies=[Depends(verify_csrf)])
def user_unlock(request: Request, user_id: int, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None:
        flash(request, "Usuário não encontrado.", "error")
    elif auth_service.is_blocked(target) is None and not target.failed_attempts:
        flash(request, f"{target.username} não está bloqueado.", "info")
    else:
        auth_service.unlock(target)
        audit_service.log(db, user.id, "account_unlocked", "user", target.id, {"by_admin": True})
        db.commit()
        flash(request, f"{target.username} desbloqueado: já pode tentar entrar de novo.")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/role", dependencies=[Depends(verify_csrf)])
def user_role(request: Request, user_id: int, role: str = Form(...), user: User = Depends(admin_required),
              db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target and role in ROLES:
        if target.role == "admin" and role != "admin" and _active_admins(db) <= 1:
            flash(request, "É preciso manter pelo menos um administrador ativo.", "error")
        else:
            target.role = role
            auth_service.revoke_sessions(target)
            audit_service.log(db, user.id, "role_change", "user", target.id, {"role": role})
            db.commit()
            flash(request, f"Perfil de {target.username} alterado.")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/toggle", dependencies=[Depends(verify_csrf)])
def user_toggle(request: Request, user_id: int, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target and target.id != user.id:
        if target.active and target.role == "admin" and _active_admins(db) <= 1:
            flash(request, "É preciso manter pelo menos um administrador ativo.", "error")
        else:
            target.active = not target.active
            auth_service.revoke_sessions(target)  # desativar derruba as sessões abertas na hora
            audit_service.log(db, user.id, "activate" if target.active else "deactivate", "user", target.id)
            db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/reset-2fa", dependencies=[Depends(verify_csrf)])
def user_reset_2fa(request: Request, user_id: int, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    """Outro administrador perdeu o celular: remove o 2FA dele (ele configura de novo no próximo acesso)."""
    target = db.get(User, user_id)
    if target is None or target.id == user.id or not target.has_2fa:
        flash(request, "Nada a redefinir.", "info")
    else:
        totp_service.disable(target)       # também encerra as sessões dele
        audit_service.log(db, user.id, "2fa_reset", "user", target.id, {"by_admin": True})
        db.commit()
        flash(request, f"2FA de {target.username} removido. Ele pode configurar de novo em Conta → Verificação em duas etapas.")
    return RedirectResponse("/admin/users", status_code=303)


def _audit_context(request, db, user, action=None, integrity=None):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(300)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    names = {u.id: u.username for u in db.scalars(select(User))}
    actions = sorted(db.scalars(select(AuditLog.action).distinct()).all())
    return render(request, "admin/audit.html", user=user, rows=db.scalars(stmt).all(), names=names, actions=actions,
                  action=action, integrity=integrity)


@router.post("/admin/audit/verify", dependencies=[Depends(verify_csrf)])
def audit_verify(request: Request, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    report = audit_service.verify_chain(db)
    audit_service.log(db, user.id, "audit_verified", "audit", None, {"ok": report.ok, "broken_id": report.broken_id})
    db.commit()
    return _audit_context(request, db, user, integrity=report)


@router.get("/admin/audit")
def audit_page(request: Request, action: str | None = None, user: User = Depends(admin_required),
               db: Session = Depends(get_db)):
    return _audit_context(request, db, user, action)

