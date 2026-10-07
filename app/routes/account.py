from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import security
from app.database import get_db
from app.models import User
from app.security import current_user, verify_csrf
from app.services import auth_service
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
