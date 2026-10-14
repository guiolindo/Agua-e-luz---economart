"""Lixeira. Quem lança contas vê e restaura o que ELE excluiu nos últimos 30 dias (erro simples se desfaz sem
depender de ninguém). O administrador vê tudo, por 180 dias, e pode desfazer de uma vez o que uma pessoa apagou."""
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.database import get_db
from app.models import TrashItem, User
from app.models.mixins import utcnow
from app.security import admin_required, verify_csrf, writer_required
from app.services import trash_service
from app.web import flash, render

router = APIRouter()


def _safe_next(next_url: str, default: str = "/lixeira") -> str:
    return next_url if next_url.startswith("/") and not next_url.startswith("//") and "\\" not in next_url else default


@router.get("/lixeira")
def trash_page(request: Request, por: int | None = None, user: User = Depends(writer_required), db: Session = Depends(get_db)):
    s = get_settings()
    stmt = select(TrashItem).order_by(TrashItem.restored_at.is_not(None), TrashItem.deleted_at.desc())
    if user.is_admin:
        if por:
            stmt = stmt.where(TrashItem.deleted_by == por)
        stmt = stmt.limit(500)
    else:                                   # lixeira pessoal: só o que a pessoa excluiu, ainda dentro do prazo dela
        stmt = stmt.where(TrashItem.deleted_by == user.id, TrashItem.deleted_at >= trash_service.personal_cutoff(),
                          TrashItem.restored_at.is_(None))
    rows = []
    for it in db.scalars(stmt):
        again = it.restored_at is None and trash_service.relaunched(db, it) is not None
        if again and not user.is_admin:
            continue                        # já foi lançada de novo: não há o que restaurar, some da lixeira pessoal
        rows.append({"item": it, "relaunched": again, "can": it.restored_at is None and not again and trash_service.can_restore(user, it)})
    ctx = {"rows": rows, "por": por, "kinds": trash_service.KIND_LABELS, "days": s.trash_days,
           "personal_days": s.trash_personal_days, "limit": s.max_deletes_per_hour}
    if user.is_admin:
        since = utcnow() - timedelta(days=7)
        week = db.execute(select(TrashItem.deleted_by, func.count()).where(TrashItem.deleted_at >= since)
                          .group_by(TrashItem.deleted_by)).all()
        ctx.update(names={u.id: u.username for u in db.scalars(select(User))}, week=sorted(week, key=lambda r: -r[1]),
                   blocks=trash_service.recent_blocks(db),
                   pending=sum(1 for r in rows if r["can"]) if por else 0)
    return render(request, "trash.html", user=user, **ctx)


@router.post("/lixeira/{item_id}/restaurar", dependencies=[Depends(verify_csrf)])
def trash_restore(request: Request, item_id: int, next: str = Form("/lixeira"), user: User = Depends(writer_required),
                  db: Session = Depends(get_db)):
    back = _safe_next(next)
    item = db.get(TrashItem, item_id)
    if item is None or not trash_service.can_restore(user, item):
        flash(request, "Este item não está na sua lixeira (passou do prazo ou foi excluído por outra pessoa). "
                       "Peça ao administrador.", "error")
        return RedirectResponse("/lixeira", status_code=303)
    try:
        trash_service.restore(db, item, user)
    except trash_service.TrashError as exc:
        db.rollback()
        flash(request, str(exc), "info")
        return RedirectResponse(back, status_code=303)
    db.commit()
    flash(request, f"Restaurado: {item.summary}.")
    return RedirectResponse(back, status_code=303)


@router.post("/lixeira/restaurar-de", dependencies=[Depends(verify_csrf)])
def trash_restore_all(request: Request, deleted_by: int = Form(...), confirm_password: str = Form(""),
                      user: User = Depends(admin_required), db: Session = Depends(get_db)):
    """Desfaz de uma vez tudo o que uma pessoa excluiu (o caso de quem saiu apagando)."""
    if not security.verify_password(confirm_password, user.password_hash):
        flash(request, "Senha incorreta: restaurar tudo de uma vez precisa da confirmação da sua senha.", "error")
        return RedirectResponse(f"/lixeira?por={deleted_by}", status_code=303)
    ok, again = 0, 0
    for item in db.scalars(select(TrashItem).where(TrashItem.deleted_by == deleted_by, TrashItem.restored_at.is_(None))
                           .order_by(TrashItem.deleted_at)):
        try:
            with db.begin_nested():
                trash_service.restore(db, item, user)
            ok += 1
        except trash_service.TrashError:
            again += 1
    db.commit()
    msg = f"{ok} item(ns) restaurado(s)."
    if again:
        msg += f" {again} não precisaram: o mesmo mês já foi lançado de novo."
    flash(request, msg)
    return RedirectResponse(f"/lixeira?por={deleted_by}", status_code=303)
