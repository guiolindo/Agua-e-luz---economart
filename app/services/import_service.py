"""Ciclo de vida de uma importação: upload -> extração (background) -> conferência -> persistência."""
import logging
import threading
from datetime import date, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import ConsumerUnit, Document, EnergyBill, Import, Store
from app.models.mixins import utcnow
from app.schemas.extraction import BillExtraction
from app.services import audit_service
from app.services.crypto_service import CryptoError, encrypt
from app.services.extraction_service import Extractor, get_extractor
from app.services.gemini_service import ExtractionError
from app.services.matching_service import find_unit_by_number
from app.utils.parsing import normalize_uc
from app.utils.uploads import sha256, validate_upload

log = logging.getLogger(__name__)

# Limita chamadas simultâneas ao Gemini (cota gratuita ~15/min): o excedente espera sua vez.
_SLOTS = threading.BoundedSemaphore(max(1, get_settings().gemini_max_concurrency))

BILL_FIELDS = [
    "reference", "issue_date", "due_date", "invoice_number", "series", "total_value", "days",
    "previous_reading_date", "current_reading_date", "next_reading_date",
    "consumption_kwh", "consumption_hp", "consumption_hfp", "consumption_hr", "demand_hp", "demand_hfp", "contracted_demand",
    "pis_cofins_value", "icms_value", "bill_class", "subclass", "tariff_modality", "notes",
]


def create_import(db: Session, filename: str, data: bytes, user_id: int | None,
                  store_hint_id: int | None = None) -> Import:
    safe_name, content_type = validate_upload(filename, data, get_settings().max_upload_bytes)
    stored, encrypted = encrypt(data)
    doc = Document(filename=safe_name, content_type=content_type, size=len(data), sha256=sha256(data),
                   data=stored, encrypted=encrypted, uploaded_by=user_id)
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
            with _SLOTS:
                extraction = extractor.extract(job.document.plain(), job.document.content_type, store_catalog(db))
        except (ExtractionError, CryptoError) as exc:
            _fail(db, job, str(exc))
            return
        except Exception:
            log.exception("Erro inesperado na extração da importação %s", import_id)
            _fail(db, job, "Ocorreu um erro inesperado ao analisar a conta.")
            return

        reason = rejection_reason(extraction)
        if reason:
            _reject(db, job, extractor.name, reason, extraction)
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


def rejection_reason(e: BillExtraction) -> str | None:
    """Motivo para barrar o arquivo (não é conta de energia), ou None se parece uma conta.
    Barra quando a IA disse que não é conta, ou quando não leu NADA que identifique uma conta."""
    if e.is_energy_bill is False:
        return (e.not_bill_reason or "documento que não é conta de energia").strip()[:120]
    identifies = (e.consumer_unit_number, e.total_value, e.reference_month, e.invoice_number, e.due_date)
    if not any(v not in (None, "") for v in identifies) and not e.line_items:
        return "não foi possível reconhecer uma conta de energia no arquivo"
    return None


def _reject(db: Session, job: Import, provider: str, reason: str, extraction: BillExtraction) -> None:
    """Arquivo que não é conta: nada é lançado e os bytes são APAGADOS na hora (só ficam nome e motivo, na auditoria)."""
    doc = job.document
    audit_service.log(db, job.created_by, "import_rejected", "import", job.id,
                      {"filename": doc.filename, "reason": reason, "provider": provider, "bytes_deleted": True})
    doc.data = None
    job.status, job.stage, job.provider, job.extracted = "rejected", "done", provider, None
    job.error = ("Este arquivo não parece ser uma conta de energia (" + reason + "). Ele foi descartado e não foi "
                 "salvo. Envie a foto ou o PDF da conta de energia.")
    db.commit()


def store_catalog(db: Session) -> str | None:
    """Lojas com apelidos, para o Gemini normalizar anotações à mão ("CD 300" -> CD300)."""
    lines = []
    for s in db.query(Store).filter(Store.active.is_(True)).order_by(Store.code):
        aliases = ", ".join(a for a in (s.aliases or []) if a)
        lines.append(f"- {s.code}" + (f" ({s.name})" if s.name else "") + (f" ← {aliases}" if aliases else ""))
    return "\n".join(lines) or None


def expire_if_stale(db: Session, job: Import) -> bool:
    """Importação 'processing' parada há muito tempo (processo reiniciado, travamento) vira falha com opção de retry."""
    if job.status != "processing":
        return False
    updated = job.updated_at if job.updated_at.tzinfo else job.updated_at.replace(tzinfo=timezone.utc)
    if utcnow() - updated < timedelta(minutes=get_settings().stale_import_minutes):
        return False
    _fail(db, job, "A análise demorou demais e foi interrompida. Clique em “Tentar novamente”.")
    return True


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
    if unit.due_day is None and values.get("due_date"):
        unit.due_day = values["due_date"].day  # o lembrete de vencimento nasce sozinho a partir da conta
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
