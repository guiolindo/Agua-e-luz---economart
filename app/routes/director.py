from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import director_required
from app.services import executive_service
from app.utils.parsing import parse_reference
from app.web import render

router = APIRouter()


@router.get("/diretoria")
def executive_panel(request: Request, start: str | None = None, end: str | None = None, by: str = "reference",
                    region: str | None = None, types: list[int] | None = None,
                    user: User = Depends(director_required), db: Session = Depends(get_db)):
    data = executive_service.build(db, parse_reference(start), parse_reference(end), "due" if by == "due" else "reference",
                                   types or None, region or None)
    return render(request, "director/panel.html", user=user, payload=executive_service.client_payload(data), **data)
