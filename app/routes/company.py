"""Lojas da empresa (administrador): carregar a lista oficial e vincular as lojas criadas antes dela."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Store, User
from app.security import admin_required, verify_csrf
from app.services import audit_service, company_stores
from app.web import flash, plural, render

router = APIRouter()
MAX_TEXT = 200_000


def link_context(db: Session) -> dict:
    """Lojas antigas a vincular (cartão no topo da tela Lojas, só para o administrador)."""
    legacy = company_stores.legacy_stores(db)
    if not legacy:
        return {"legacy": []}
    officials = company_stores.official_stores(db)
    return {"legacy": legacy, "officials": officials,
            "suggestions": {s.id: company_stores.suggest(s, officials) for s in legacy},
            "summaries": {s.id: company_stores.link_summary(s, db) for s in legacy}}


def _page(request: Request, db: Session, user: User, **extra):
    return render(request, "admin/company.html", user=user, officials=company_stores.official_stores(db), **extra)


@router.get("/admin/lojas")
def company_page(request: Request, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    return _page(request, db, user)


@router.post("/admin/lojas/conferir", dependencies=[Depends(verify_csrf)])
def company_preview(request: Request, text: str = Form("", max_length=MAX_TEXT), user: User = Depends(admin_required),
                    db: Session = Depends(get_db)):
    parsed = company_stores.plan(db, company_stores.parse(text))
    if not parsed.rows and not parsed.errors:
        flash(request, "Nenhuma loja encontrada no texto. Cole as linhas da planilha (com o CNPJ de cada loja).", "error")
        return RedirectResponse("/admin/lojas", status_code=303)
    return _page(request, db, user, preview=parsed, text=text)


@router.post("/admin/lojas/carregar", dependencies=[Depends(verify_csrf)])
def company_import(request: Request, text: str = Form("", max_length=MAX_TEXT), user: User = Depends(admin_required),
                   db: Session = Depends(get_db)):
    parsed = company_stores.parse(text)
    if not parsed.rows:
        flash(request, "Nenhuma loja válida para carregar.", "error")
        return RedirectResponse("/admin/lojas", status_code=303)
    created, updated = company_stores.apply(db, parsed)
    audit_service.log(db, user.id, "import", "company_stores", None,
                      {"created": created, "updated": updated, "codes": [r.code for r in parsed.rows][:200]})
    db.commit()
    msg = f"Lista carregada: {plural(created, 'loja nova', 'lojas novas')}, {plural(updated, 'atualizada', 'atualizadas')}."
    if parsed.errors:
        msg += f" {plural(len(parsed.errors), 'linha ignorada', 'linhas ignoradas')} por erro."
    flash(request, msg)
    return RedirectResponse("/stores#vincular" if company_stores.legacy_stores(db) else "/stores", status_code=303)


def _pair(db: Session, legacy_id: int, official_id: int) -> tuple[Store, Store]:
    legacy, official = db.get(Store, legacy_id), db.get(Store, official_id)
    if not legacy or not official:
        raise HTTPException(404, "Loja não encontrada.")
    return legacy, official


@router.get("/admin/lojas/vincular")
def link_confirm(request: Request, legacy: int, official: int | None = None, user: User = Depends(admin_required),
                 db: Session = Depends(get_db)):
    if not official:
        flash(request, "Escolha a loja da lista oficial.", "error")
        return RedirectResponse("/stores#vincular", status_code=303)
    old, new = _pair(db, legacy, official)
    if old.is_official or not new.is_official or old.id == new.id:
        flash(request, "Escolha uma loja antiga e uma loja da lista oficial.", "error")
        return RedirectResponse("/stores#vincular", status_code=303)
    return render(request, "admin/company_link.html", user=user, old=old, new=new,
                  summary=company_stores.link_summary(old, db))


@router.post("/admin/lojas/vincular", dependencies=[Depends(verify_csrf)])
def link_store(request: Request, legacy_id: int = Form(...), official_id: int = Form(...),
               user: User = Depends(admin_required), db: Session = Depends(get_db)):
    old, new = _pair(db, legacy_id, official_id)
    old_label, old_id = old.label, old.id
    try:
        summary = company_stores.link(db, old, new)
    except company_stores.LinkError as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return RedirectResponse("/stores#vincular", status_code=303)
    audit_service.log(db, user.id, "link", "store", new.id,
                      {"from_id": old_id, "from": old_label, "units": summary.units, "bills": summary.bills,
                       "records": summary.records})
    db.commit()
    flash(request, f"{old_label} vinculada a {new.label}: {plural(summary.units, 'unidade', 'unidades')}, {plural(summary.bills, 'conta', 'contas')} "
                   f"e {plural(summary.records, 'lançamento', 'lançamentos')} passaram para a loja oficial.")
    return RedirectResponse("/stores#vincular", status_code=303)
