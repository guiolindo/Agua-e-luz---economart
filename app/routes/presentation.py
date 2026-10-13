from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AuditLog, User
from app.models.mixins import utcnow
from app.security import current_user
from app.services import audit_service
from app.utils.presentation import presentation_open, presentation_until_label
from app.web import render

router = APIRouter()


@router.get("/apresentacao")
def presentation(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Slides de apresentação do sistema, para qualquer pessoa logada, só até o prazo (PRESENTATION_UNTIL)."""
    if not presentation_open():
        raise HTTPException(404, "A apresentação do sistema não está mais disponível.")
    # quem abriu a apresentação (painel do administrador): um registro por pessoa a cada 30 min, não a cada recarga
    recent = db.scalar(select(AuditLog.id).where(AuditLog.user_id == user.id, AuditLog.action == "view",
                                                 AuditLog.entity == "presentation",
                                                 AuditLog.at >= utcnow() - timedelta(minutes=30)).limit(1))
    if recent is None:
        audit_service.log(db, user.id, "view", "presentation", None)
        db.commit()
    return render(request, "presentation.html", user=user, until=presentation_until_label(),
                  require_2fa=get_settings().require_admin_2fa)
