from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.repositories.stores import list_stores
from app.security import current_user
from app.services import dashboard_service
from app.utils.parsing import parse_reference
from app.web import render

router = APIRouter()


@router.get("/")
def home(request: Request, month: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = dashboard_service.overview(db, parse_reference(month))
    return render(request, "dashboard.html", user=user, stores_list=list_stores(db, only_active=True), **data)
