from fastapi import APIRouter, Depends, Request

from app.models import User
from app.security import current_user
from app.web import render

router = APIRouter()


@router.get("/ajuda")
def help_page(request: Request, user: User = Depends(current_user)):
    return render(request, "help.html", user=user)
