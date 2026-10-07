from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RecordType, Store, User
from app.security import current_user
from app.services import chart_service
from app.utils.parsing import parse_reference

router = APIRouter()


@router.get("/api/stores/{store_id}/chart")
def store_chart(store_id: int, type_id: int | None = None, indicator: str | None = None, view: str = "units",
                start: str | None = None, end: str | None = None, highlight: int | None = None,
                unit_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Loja não encontrada.")
    rtype = db.get(RecordType, type_id) if type_id else None
    return chart_service.build_chart(
        db, store, record_type=rtype, indicator_key=indicator, view="types" if view == "types" else "units",
        start=parse_reference(start), end=parse_reference(end), highlight_unit_id=highlight, unit_id=unit_id)
