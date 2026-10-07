"""Ciclo de vida de uma importação: upload -> extração (background) -> conferência -> persistência."""
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import ConsumerUnit, Document, EnergyBill, Import, Store
from app.models.mixins import utcnow
from app.schemas.extraction import BillExtraction
from app.services import audit_service
from app.services.extraction_service import Extractor, get_extractor
from app.services.gemini_service import ExtractionError
from app.services.matching_service import find_unit_by_number
from app.utils.parsing import normalize_uc
from app.utils.uploads import sha256, validate_upload

log = logging.getLogger(__name__)

BILL_FIELDS = [
    "reference", "issue_date", "due_date", "invoice_number", "series", "total_value", "days",
    "previous_reading_date", "current_reading_date", "next_reading_date",
    "consumption_kwh", "consumption_hp", "consumption_hfp", "consumption_hr", "demand_hp", "demand_hfp", "contracted_demand",
    "pis_cofins_value", "icms_value", "bill_class", "subclass", "tariff_modality", "notes",
]


def create_import(db: Session, filename: str, data: bytes, user_id: int | None,
                  store_hint_id: int | None = None) -> Import:
    safe_name, content_type = validate_upload(filename, data, get_settings().max_upload_bytes)
    doc = Document(filename=safe_name, content_type=content_type, size=len(data), sha256=sha256(data),
                   data=data, uploaded_by=user_id)
    db.add(doc)
    db.flush()
    job = Import(document_id=doc.id, store_hint_id=store_hint_id, created_by=user_id)
    db.add(job)
    db.commit()
    return job


def run_import(import_id: int, extractor: Extractor | None = None, session_factory=SessionLocal) -> None:
    """Executa a extração em background (sessão própria). Atualiza `stage` para o feedback na tela."""
    db = session_factory()
    try:
        job = db.get(Import, import_id)
        if job is None:
            return
        extractor = extractor or get_extractor()
        if job.document.data is None:
            _fail(db, job, "O arquivo original desta importação já expirou e foi removido.")
            return
        job.stage = "extracting"
        db.commit()
        try:
            extraction = extractor.extract(job.document.data, job.document.content_type, store_catalog(db))
        except ExtractionError as exc:
            _fail(db, job, str(exc))
            return
        except Exception:
            log.exception("Erro inesperado na extração da importação %s", import_id)
            _fail(db, job, "Ocorreu um erro inesperado ao analisar a conta.")
            return

        job.extracted = extraction.model_dump()
        job.provider = extractor.name
        job.stage = "matching"
        db.commit()

        unit = find_unit_by_number(db, extraction.consumer_unit_number)
        job.matched_unit_id = unit.id if unit else None
        job.stage = "done"
        job.status = "ready"
        audit_service.log(db, job.created_by, "extract", "import", job.id,
                          {"provider": job.provider, "matched_unit_id": job.matched_unit_id})
        db.commit()
    finally:
        db.close()


def store_catalog(db: Session) -> str | None:
    """Lojas com apelidos, para o Gemini normalizar anotações à mão ("CD 300" -> CD300)."""
    lines = []
    for s in db.query(Store).filter(Store.active.is_(True)).order_by(Store.code):
        aliases = ", ".join(a for a in (s.aliases or []) if a)
        lines.append(f"- {s.code}" + (f" ({s.name})" if s.name else "") + (f" ← {aliases}" if aliases else ""))
    return "\n".join(lines) or None


def _fail(db: Session, job: Import, message: str) -> None:
    job.status = "failed"
    job.stage = "done"
    job.error = message
    db.commit()


def get_extraction(job: Import) -> BillExtraction | None:
    return BillExtraction.model_validate(job.extracted) if job.extracted else None


class UnitConflict(ValueError):
    pass


def create_unit(db: Session, store_id: int, number: str, description: str | None, record_type_id: int | None,
                user_id: int | None) -> ConsumerUnit:
    key = normalize_uc(number)
    if not key:
        raise UnitConflict("Informe o número da unidade consumidora.")
    existing = db.query(ConsumerUnit).filter(ConsumerUnit.number_normalized == key).first()
    if existing:
        raise UnitConflict(f"A unidade {existing.number} já está cadastrada (loja {existing.store.code}).")
    unit = ConsumerUnit(store_id=store_id, number=number.strip(), number_normalized=key,
                        description=(description or None), record_type_id=record_type_id)
    db.add(unit)
    db.flush()
    audit_service.log(db, user_id, "create", "consumer_unit", unit.id, {"number": unit.number, "store_id": store_id})
    return unit


def _snapshot(bill: EnergyBill) -> dict:
    return {f: (v.isoformat() if isinstance(v, date) else (str(v) if v is not None else None))
            for f in BILL_FIELDS for v in [getattr(bill, f)]}


def save_bill(db: Session, unit: ConsumerUnit, record_type_id: int, values: dict, user_id: int | None,
              document_id: int | None = None, line_items: list | None = None, source: str = "import",
              replace: EnergyBill | None = None) -> EnergyBill:
    """Cria a conta, ou (replace=...) substitui os dados de uma existente mantendo o histórico em auditoria."""
    payload = {f: values.get(f) for f in BILL_FIELDS}
    if replace is not None:
        before = _snapshot(replace)
        for f, v in payload.items():
            setattr(replace, f, v)
        replace.unit_id = unit.id
        replace.record_type_id = record_type_id
        if document_id:
            replace.document_id = document_id
            replace.source = source
        if line_items is not None:
            replace.line_items = line_items
        replace.updated_by = user_id
        replace.updated_at = utcnow()
        db.flush()
        audit_service.log(db, user_id, "replace", "energy_bill", replace.id, {"before": before, "after": _snapshot(replace)})
        return replace
    bill = EnergyBill(unit_id=unit.id, record_type_id=record_type_id, document_id=document_id, source=source,
                      line_items=line_items, created_by=user_id, updated_by=user_id, **payload)
    db.add(bill)
    db.flush()
    audit_service.log(db, user_id, "create", "energy_bill", bill.id, {"source": source, "after": _snapshot(bill)})
    return bill
