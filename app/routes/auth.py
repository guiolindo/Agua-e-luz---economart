from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import security
from app.database import get_db
from app.models import User
from app.security import verify_csrf
from app.services import auth_service
from app.web import render

router = APIRouter()
GENERIC_ERROR = "Usuário ou senha incorretos."
LOCKED_ERROR = ("Acesso bloqueado por excesso de tentativas. Tente de novo em {minutes} minuto(s) "
                "ou peça ao administrador para redefinir a senha.")


@router.get("/login")
def login_page(request: Request, next: str = "/"):
    return render(request, "login.html", next=next)


@router.post("/login", dependencies=[Depends(verify_csrf)])
def login(request: Request, username: str = Form(..., max_length=80), password: str = Form(..., max_length=256),
          next: str = Form("/"), db: Session = Depends(get_db)):
    result = auth_service.attempt_login(db, request, username, password)
    if not result.ok:
        error = LOCKED_ERROR.format(minutes=result.minutes) if result.locked else GENERIC_ERROR
        return render(request, "login.html", status_code=401, next=next, error=error, username=username.strip()[:80])
    target = next if next.startswith("/") and not next.startswith("//") and "\\" not in next else "/"
    if result.user.is_admin and result.user.has_2fa:
        # senha certa, mas a sessão só nasce depois do código do autenticador
        request.session.clear()
        request.session["pre2fa"] = {"uid": result.user.id, "ts": security._now_ts(), "next": target}
        return RedirectResponse("/login/2fa", status_code=303)
    return _finish_login(request, result.user, target)


def _finish_login(request: Request, user: User, target: str):
    security.start_session(request, user)
    if user.must_change_password:
        return RedirectResponse("/account/password", status_code=303)
    if target == "/" and user.is_director:
        target = "/diretoria"
    return RedirectResponse(target, status_code=303)


PRE2FA_SECONDS = 300


def _pending_user(request: Request, db: Session) -> tuple[User | None, str]:
    pend = request.session.get("pre2fa") or {}
    user = db.get(User, pend.get("uid")) if pend.get("uid") else None
    if user is None or not user.active or not user.has_2fa or security._now_ts() - int(pend.get("ts", 0)) > PRE2FA_SECONDS:
        request.session.pop("pre2fa", None)
        return None, "/"
    return user, pend.get("next", "/")


@router.get("/login/2fa")
def login_2fa_page(request: Request, db: Session = Depends(get_db)):
    user, _ = _pending_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return render(request, "login_2fa.html")


@router.post("/login/2fa", dependencies=[Depends(verify_csrf)])
def login_2fa(request: Request, code: str = Form(..., max_length=32), db: Session = Depends(get_db)):
    user, target = _pending_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    result = auth_service.verify_second_factor(db, request, user, code)
    if result.ok:
        return _finish_login(request, user, target)
    if result.locked:
        request.session.pop("pre2fa", None)
        return render(request, "login.html", status_code=401, next="/", error=LOCKED_ERROR.format(minutes=result.minutes))
    return render(request, "login_2fa.html", status_code=401, error="Código incorreto ou já usado. Confira o app e tente de novo.")


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if user is not None:
        auth_service.revoke_sessions(user)  # derruba também cookies copiados antes do logout
        auth_service.security_event(db, request, "logout", user.id)
        db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
