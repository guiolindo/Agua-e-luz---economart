from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import verify_csrf, verify_password
from app.web import render

router = APIRouter()


@router.get("/login")
def login_page(request: Request, next: str = "/"):
    return render(request, "login.html", next=next)


@router.post("/login", dependencies=[Depends(verify_csrf)])
def login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/"),
          db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not user or not user.active or not verify_password(password, user.password_hash):
        return render(request, "login.html", status_code=401, next=next, error="Usuário ou senha incorretos.")
    request.session.clear()
    request.session["uid"] = user.id
    target = next if next.startswith("/") and not next.startswith("//") else "/"
    return RedirectResponse(target, status_code=303)


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
