from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AlertAck, User
from app.security import current_user, verify_csrf
from app.services import alert_service, audit_service
from app.web import flash, render

router = APIRouter()


def _can_ack(user: User) -> bool:
    return user.can_write or user.can_see_executive


@router.get("/alertas")
def alerts_page(request: Request, sev: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    alerts = alert_service.compute(db)
    shown = [a for a in alerts if a.severity == sev] if sev in alert_service.ORDER else alerts
    counts = {k: sum(1 for a in alerts if a.severity == k) for k in alert_service.ORDER}
    return render(request, "alerts/list.html", user=user, alerts=shown, total=len(alerts), counts=counts, sev=sev,
                  can_ack=_can_ack(user), labels=alert_service.LABEL)


@router.post("/alertas/conferido", dependencies=[Depends(verify_csrf)])
def alerts_ack(request: Request, key: str = Form("", max_length=80), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not _can_ack(user):
        raise HTTPException(status_code=403, detail="Seu perfil é somente de consulta.")
    if key in {a.key for a in alert_service.compute(db)}:       # só chaves de alertas que existem de fato
        db.add(AlertAck(key=key, by_user=user.id))
        audit_service.log(db, user.id, "alert_ack", "alert", None, {"alerta": key})
        db.commit()
        alert_service.reset_cache()
        flash(request, "Alerta marcado como conferido.")
    return RedirectResponse("/alertas", status_code=303)


@router.get("/api/alertas/contagem")
def alerts_count(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return JSONResponse(alert_service.counts(db))
