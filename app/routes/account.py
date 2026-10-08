from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import security
from app.database import get_db
from app.models import User
from app.config import get_settings
from app.security import admin_required, current_user, verify_csrf
from app.services import auth_service, totp_service
from app.web import flash, render

router = APIRouter()


@router.get("/account/password")
def password_page(request: Request, user: User = Depends(current_user)):
    return render(request, "account/password.html", user=user, forced=bool(user.must_change_password))


@router.post("/account/password", dependencies=[Depends(verify_csrf)])
def password_change(request: Request, current_password: str = Form(..., max_length=256),
                    new_password: str = Form(..., max_length=256), confirm: str = Form(..., max_length=256),
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    error = None
    if not security.verify_password(current_password, user.password_hash):
        error = "A senha atual está incorreta."
        auth_service.security_event(db, request, "password_change_failed", user.id)
        db.commit()
    elif new_password != confirm:
        error = "A confirmação não confere com a nova senha."
    elif new_password == current_password:
        error = "A nova senha deve ser diferente da atual."
    else:
        error = security.validate_password(new_password, user.username)
    if error:
        return render(request, "account/password.html", status_code=400, user=user, error=error,
                      forced=bool(user.must_change_password))
    auth_service.set_password(db, user, new_password)
    auth_service.security_event(db, request, "password_changed", user.id)
    db.commit()
    security.start_session(request, user)  # outras sessões deste usuário caem; esta continua
    flash(request, "Senha alterada.")
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------- 2FA (só administrador)
def _2fa_page(request, user, db, **extra):
    secret = None
    if not user.has_2fa:
        if not user.totp_secret:
            totp_service.start_enrollment(user)
            db.commit()
        secret = totp_service.current_secret(user)
        extra.setdefault("qr", totp_service.qr_svg(totp_service.provisioning_uri(user.username, secret)))
        extra["secret"] = " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))
    return render(request, "account/two_factor.html", status_code=extra.pop("status_code", 200), user=user,
                  enabled=user.has_2fa, required=get_settings().require_admin_2fa, **extra)


@router.get("/account/2fa")
def two_factor_page(request: Request, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    return _2fa_page(request, user, db)


@router.post("/account/2fa/enable", dependencies=[Depends(verify_csrf)])
def two_factor_enable(request: Request, code: str = Form(..., max_length=32), user: User = Depends(admin_required),
                      db: Session = Depends(get_db)):
    if user.has_2fa or not user.totp_secret:
        return RedirectResponse("/account/2fa", status_code=303)
    if not totp_service.check_code(user, code):
        auth_service.security_event(db, request, "2fa_setup_failed", user.id)
        db.commit()
        return _2fa_page(request, user, db, status_code=400, error="Código incorreto. Confira se o app está com a hora certa e tente de novo.")
    user.totp_enabled = True
    codes = totp_service.new_recovery_codes(user)
    auth_service.revoke_sessions(user)       # outras sessões abertas caem; esta continua
    auth_service.security_event(db, request, "2fa_enabled", user.id)
    db.commit()
    security.start_session(request, user)
    return render(request, "account/two_factor.html", user=user, enabled=True, recovery_codes=codes,
                  required=get_settings().require_admin_2fa)


@router.post("/account/2fa/disable", dependencies=[Depends(verify_csrf)])
def two_factor_disable(request: Request, password: str = Form(..., max_length=256), code: str = Form(..., max_length=32),
                       user: User = Depends(admin_required), db: Session = Depends(get_db)):
    if not user.has_2fa:
        return RedirectResponse("/account/2fa", status_code=303)
    if not (security.verify_password(password, user.password_hash)
            and (totp_service.check_code(user, code) or totp_service.use_recovery_code(user, code))):
        auth_service.security_event(db, request, "2fa_disable_failed", user.id)
        db.commit()
        return _2fa_page(request, user, db, status_code=400, error="Senha ou código incorretos.")
    totp_service.disable(user)
    auth_service.security_event(db, request, "2fa_disabled", user.id)
    db.commit()
    security.start_session(request, user)
    flash(request, "Verificação em duas etapas desativada.", "info")
    return RedirectResponse("/account/2fa", status_code=303)
