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
GENERIC_ERROR = "Usuário ou senha incorretos, ou acesso temporariamente bloqueado."


@router.get("/login")
def login_page(request: Request, next: str = "/"):
    return render(request, "login.html", next=next)


@router.post("/login", dependencies=[Depends(verify_csrf)])
def login(request: Request, username: str = Form(..., max_length=80), password: str = Form(..., max_length=256),
          next: str = Form("/"), db: Session = Depends(get_db)):
    result = auth_service.attempt_login(db, request, username, password)
    if not result.ok:
        return render(request, "login.html", status_code=401, next=next, error=GENERIC_ERROR)
    security.start_session(request, result.user)
    if result.user.must_change_password:
        return RedirectResponse("/account/password", status_code=303)
    target = next if next.startswith("/") and not next.startswith("//") and "\\" not in next else "/"
    return RedirectResponse(target, status_code=303)


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
