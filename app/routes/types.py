import re
import unicodedata

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RecordType, User
from app.repositories.stores import list_record_types
from app.security import admin_required, verify_csrf
from app.services import audit_service
from app.utils.parsing import clean_str
from app.web import flash, render

router = APIRouter()


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_fields(text: str) -> list[dict]:
    """Um campo por linha: 'Horas de operação (h)' -> {key, label, unit}."""
    fields, seen = [], set()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.fullmatch(r"(.+?)\s*\(([^)]*)\)", line)
        label, unit = (m.group(1).strip(), m.group(2).strip()) if m else (line, "")
        key = _slug(label).replace("-", "_") or "campo"
        while key in seen or key in ("value", "valor"):
            key += "_2"
        seen.add(key)
        fields.append({"key": key, "label": label[:80], "unit": unit[:10]})
    return fields[:12]


def fields_to_text(fields: list[dict]) -> str:
    return "\n".join(f"{f['label']} ({f['unit']})" if f.get("unit") else f["label"] for f in fields or [])


@router.get("/types")
def types_page(request: Request, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    return render(request, "types/list.html", user=user, types=list_record_types(db, only_active=False),
                  fields_to_text=fields_to_text)


@router.post("/types", dependencies=[Depends(verify_csrf)])
def type_create(request: Request, name: str = Form(...), kind: str = Form("manual"), description: str = Form(""),
                fields: str = Form(""),
                user: User = Depends(admin_required), db: Session = Depends(get_db)):
    code = _slug(name)
    if not code:
        flash(request, "Informe o nome do tipo.", "error")
    elif db.query(RecordType).filter(RecordType.code == code).first():
        flash(request, "Já existe um tipo com esse nome.", "error")
    else:
        is_bill = kind == "bill"
        rt = RecordType(code=code, name=name.strip()[:120], kind="bill" if is_bill else "manual",
                        description=clean_str(description), fields=[] if is_bill else parse_fields(fields),
                        sort_order=15 if is_bill else 100)
        db.add(rt)
        db.flush()
        audit_service.log(db, user.id, "create", "record_type", rt.id, {"name": rt.name})
        db.commit()
        flash(request, f"Tipo “{rt.name}” criado.")
    return RedirectResponse("/types", status_code=303)


@router.post("/types/{type_id}", dependencies=[Depends(verify_csrf)])
def type_update(request: Request, type_id: int, name: str = Form(...), description: str = Form(""),
                fields: str = Form(""), active: str = Form(""), user: User = Depends(admin_required),
                db: Session = Depends(get_db)):
    rt = db.get(RecordType, type_id)
    if not rt:
        raise HTTPException(404, "Tipo não encontrado.")
    rt.name, rt.description, rt.active = name.strip()[:120], clean_str(description), bool(active)
    if not rt.is_bill:
        rt.fields = parse_fields(fields)
    audit_service.log(db, user.id, "update", "record_type", rt.id)
    db.commit()
    flash(request, "Tipo atualizado.")
    return RedirectResponse("/types", status_code=303)
