from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import admin_required, hash_password, verify_csrf
from app.web import flash, render

router = APIRouter()


@router.get("/admin/users")
def users_page(request: Request, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    return render(request, "admin/users.html", user=user, users=db.scalars(select(User).order_by(User.username)).all())


@router.post("/admin/users", dependencies=[Depends(verify_csrf)])
def user_create(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form("user"),
                user: User = Depends(admin_required), db: Session = Depends(get_db)):
    username = username.strip()
    if not username or len(password) < 8:
        flash(request, "Informe o usuário e uma senha com pelo menos 8 caracteres.", "error")
    elif db.scalar(select(User).where(User.username == username)):
        flash(request, "Esse usuário já existe.", "error")
    else:
        db.add(User(username=username, password_hash=hash_password(password),
                    role="admin" if role == "admin" else "user"))
        db.commit()
        flash(request, f"Usuário {username} criado.")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/toggle", dependencies=[Depends(verify_csrf)])
def user_toggle(request: Request, user_id: int, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target and target.id != user.id:
        target.active = not target.active
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)
