from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import ConsumerUnit, Import, User
from app.repositories.stores import default_bill_type, list_stores
from app.schemas.forms import extraction_to_form, low_confidence_fields, parse_bill_form
from app.security import current_user, verify_csrf
from app.services import audit_service
from app.services.duplicate_service import find_bill_duplicates
from app.services.import_service import UnitConflict, create_unit, get_extraction, run_import, save_bill
from app.services.matching_service import suggest_similar_units
from app.utils.uploads import UploadError
from app.web import flash, render

router = APIRouter()
STEPS = [("received", "Documento recebido"), ("extracting", "Lendo a conta"), ("matching", "Identificando a unidade"),
         ("done", "Pronto para conferência")]


def _job_or_404(db: Session, import_id: int) -> Import:
    job = db.get(Import, import_id)
    if not job:
        raise HTTPException(404, "Importação não encontrada.")
    return job


@router.get("/import")
def import_page(request: Request, store_id: int | None = None, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    recent = db.scalars(select(Import).order_by(Import.id.desc()).limit(8)).all()
    return render(request, "imports/upload.html", user=user, stores=list_stores(db, only_active=True),
                  store_id=store_id, recent=recent, max_mb=get_settings().max_upload_mb)


@router.post("/import", dependencies=[Depends(verify_csrf)])
async def import_upload(request: Request, background: BackgroundTasks, file: UploadFile = File(...),
                        store_id: int | None = Form(None), user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    from app.services.import_service import create_import

    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)  # nunca carrega mais que o limite + 1 byte
    try:
        job = create_import(db, file.filename or "conta", data, user.id, store_id)
    except UploadError as exc:
        return render(request, "imports/upload.html", status_code=400, user=user, error=str(exc),
                      stores=list_stores(db, only_active=True), store_id=store_id, recent=[],
                      max_mb=get_settings().max_upload_mb)
    background.add_task(run_import, job.id)
    return RedirectResponse(f"/import/{job.id}", status_code=303)


@router.get("/import/{import_id}")
def import_progress(request: Request, import_id: int, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    job = _job_or_404(db, import_id)
    if job.status == "ready":
        return RedirectResponse(f"/import/{job.id}/review", status_code=303)
    return render(request, "imports/progress.html", user=user, job=job, steps=STEPS)


@router.get("/import/{import_id}/status")
def import_status(import_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = _job_or_404(db, import_id)
    return JSONResponse({"status": job.status, "stage": job.stage, "error": job.error})


@router.post("/import/{import_id}/retry", dependencies=[Depends(verify_csrf)])
def import_retry(import_id: int, background: BackgroundTasks, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    job = _job_or_404(db, import_id)
    if job.status == "failed":
        job.status, job.stage, job.error = "processing", "received", None
        db.commit()
        background.add_task(run_import, job.id)
    return RedirectResponse(f"/import/{job.id}", status_code=303)


@router.post("/import/{import_id}/cancel", dependencies=[Depends(verify_csrf)])
def import_cancel(request: Request, import_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = _job_or_404(db, import_id)
    if job.status != "confirmed":
        job.status = "cancelled"
        audit_service.log(db, user.id, "cancel", "import", job.id)
        db.commit()
    flash(request, "Importação descartada.", "info")
    return RedirectResponse("/import", status_code=303)


def _review_ctx(db: Session, job: Import, form: dict, errors: dict | None = None, dups=None, unit_mode: str | None = None,
                posted: dict | None = None) -> dict:
    extraction = get_extraction(job)
    unit = db.get(ConsumerUnit, job.matched_unit_id) if job.matched_unit_id else None
    posted = posted or {}
    return {
        "job": job, "extraction": extraction, "form": form, "errors": errors or {}, "dups": dups or [],
        "flagged": low_confidence_fields(extraction), "unit": unit,
        "similar": [] if unit else suggest_similar_units(db, extraction.consumer_unit_number),
        "units": db.scalars(select(ConsumerUnit).where(ConsumerUnit.active.is_(True)).order_by(ConsumerUnit.number)).all(),
        "stores": list_stores(db, only_active=True), "posted": posted,
        "unit_mode": unit_mode or ("matched" if unit else "new"),
    }


@router.get("/import/{import_id}/review")
def review(request: Request, import_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = _job_or_404(db, import_id)
    if job.status != "ready":
        return RedirectResponse(f"/import/{job.id}", status_code=303)
    form = extraction_to_form(get_extraction(job))
    ctx = _review_ctx(db, job, form)
    if ctx["unit"]:
        from app.utils.parsing import parse_reference
        ctx["dups"] = find_bill_duplicates(db, ctx["unit"].id, parse_reference(form["reference"]),
                                           form["invoice_number"] or None)
    return render(request, "imports/review.html", user=user, **ctx)


@router.post("/import/{import_id}/confirm", dependencies=[Depends(verify_csrf)])
async def confirm(request: Request, import_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = _job_or_404(db, import_id)
    if job.status != "ready":
        raise HTTPException(409, "Esta importação já foi finalizada ou descartada.")
    posted = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    values, errors = parse_bill_form(posted)
    mode = posted.get("unit_mode", "matched")

    def rerender(dups=None, status=400):
        ctx = _review_ctx(db, job, posted, errors, dups, unit_mode=mode, posted=posted)
        return render(request, "imports/review.html", status_code=status, user=user, **ctx)

    unit = None
    if mode in ("matched", "existing"):
        raw = posted.get("unit_id") if mode == "existing" else (job.matched_unit_id or posted.get("unit_id"))
        unit = db.get(ConsumerUnit, int(raw)) if raw and str(raw).isdigit() else None
        if unit is None:
            errors["unit"] = "Selecione a unidade consumidora."
    elif mode == "new":
        if not (posted.get("new_store_id") or "").isdigit():
            errors["unit"] = "Selecione a loja da nova unidade."
        if not (posted.get("new_number") or "").strip():
            errors["new_number"] = "Informe o número da unidade consumidora."
    if errors:
        return rerender()

    action = posted.get("duplicate_action", "")
    if unit is not None:
        dups = find_bill_duplicates(db, unit.id, values["reference"], values["invoice_number"])
        if dups and action not in ("replace", "new"):
            return rerender(dups, status=409)
    else:
        dups = []

    try:
        if unit is None:
            unit = create_unit(db, int(posted["new_store_id"]), posted["new_number"],
                               posted.get("new_description") or None,
                               default_bill_type(db).id if default_bill_type(db) else None, user.id)
        rtype = unit.record_type or default_bill_type(db)
        extraction = get_extraction(job)
        items = [i.model_dump() for i in extraction.line_items] if extraction else None
        replace = dups[0] if dups and action == "replace" else None
        bill = save_bill(db, unit, rtype.id, values, user.id, document_id=job.document_id, line_items=items,
                         replace=replace)
        job.status, job.bill_id, job.matched_unit_id = "confirmed", bill.id, unit.id
        audit_service.log(db, user.id, "import", "import", job.id, {"bill_id": bill.id, "unit_id": unit.id})
        db.commit()
    except UnitConflict as exc:
        db.rollback()
        errors["unit"] = str(exc)
        return rerender()

    flash(request, f"Conta {values['reference'].strftime('%m/%Y')} da unidade {unit.number} salva em {unit.store.code}.")
    return RedirectResponse(f"/stores/{unit.store_id}?highlight={unit.id}&type_id={rtype.id}", status_code=303)
