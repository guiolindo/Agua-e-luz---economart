from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import ConsumerUnit, EnergyBill, User
from app.repositories.stores import list_stores
from app.security import current_user
from app.services import alert_service, company_stores, dashboard_service
from app.utils.parsing import parse_reference
from app.web import render

router = APIRouter()


@router.get("/")
def home(request: Request, month: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.is_director:
        return RedirectResponse("/diretoria", status_code=303)
    data = dashboard_service.overview(db, parse_reference(month))
    recent_bills = db.scalars(select(EnergyBill).options(joinedload(EnergyBill.unit).joinedload(ConsumerUnit.store))
                              .order_by(EnergyBill.id.desc()).limit(5)).all()      # o fim do trabalho: imprimir para assinatura
    legacy_count = len(company_stores.legacy_stores(db)) if user.is_admin else 0
    return render(request, "dashboard.html", user=user, stores_list=list_stores(db, only_active=True),
                  alerts_open=alert_service.counts(db), recent_bills=recent_bills, legacy_count=legacy_count, **data)
