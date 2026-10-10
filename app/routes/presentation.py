from fastapi import APIRouter, Depends, HTTPException, Request

from app.models import User
from app.security import current_user
from app.utils.presentation import presentation_open, presentation_until_label
from app.web import render

router = APIRouter()


@router.get("/apresentacao")
def presentation(request: Request, user: User = Depends(current_user)):
    """Slides de apresentação do sistema, para qualquer pessoa logada, só até o prazo (PRESENTATION_UNTIL)."""
    if not presentation_open():
        raise HTTPException(404, "A apresentação do sistema não está mais disponível.")
    return render(request, "presentation.html", user=user, until=presentation_until_label())
