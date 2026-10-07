"""Lista única de contas e lançamentos — a tela para quem só quer achar e abrir uma nota."""
from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store, User
from app.security import current_user
from app.utils.parsing import normalize_uc
from app.web import render

router = APIRouter()


def _parse_month(s: str | None) -> date | None:
    if not s:
        return None
    try:
        y, m = s.split("-")
        return date(int(y), int(m), 1)
    except (ValueError, AttributeError):
        return None


@router.get("/notas")
def notas(request: Request, store_id: int | None = None, type_id: int | None = None,
          start: str | None = None, end: str | None = None, q: str = "",
          origin: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Tela única de contas: uma lista plana filtrável. Mescla contas (EnergyBill) e lançamentos
    manuais (ManualRecord) na mesma visualização, ordenada pelo mês mais recente."""
    s0, e0 = _parse_month(start), _parse_month(end)
    stores = list(db.scalars(select(Store).where(Store.active.is_(True)).order_by(Store.code)))
    types = list(db.scalars(select(RecordType).where(RecordType.active.is_(True)).order_by(RecordType.sort_order, RecordType.name)))

    # record_type não tem relationship no modelo; carrego por lookup para evitar N+1.
    types_by_id = {t.id: t for t in types}

    bills = []
    if origin in ("", "bill"):
        b_stmt = select(EnergyBill).options(joinedload(EnergyBill.unit).joinedload(ConsumerUnit.store), joinedload(EnergyBill.document))
        if store_id: b_stmt = b_stmt.join(ConsumerUnit, EnergyBill.unit_id == ConsumerUnit.id).where(ConsumerUnit.store_id == store_id)
        if type_id:  b_stmt = b_stmt.where(EnergyBill.record_type_id == type_id)
        if s0:       b_stmt = b_stmt.where(EnergyBill.reference >= s0)
        if e0:       b_stmt = b_stmt.where(EnergyBill.reference <= e0)
        bills = list(db.scalars(b_stmt.order_by(EnergyBill.reference.desc(), EnergyBill.id.desc())))

    manuals = []
    if origin in ("", "manual"):
        m_stmt = select(ManualRecord).options(joinedload(ManualRecord.store), joinedload(ManualRecord.unit))
        if store_id: m_stmt = m_stmt.where(ManualRecord.store_id == store_id)
        if type_id:  m_stmt = m_stmt.where(ManualRecord.record_type_id == type_id)
        if s0:       m_stmt = m_stmt.where(ManualRecord.reference >= s0)
        if e0:       m_stmt = m_stmt.where(ManualRecord.reference <= e0)
        manuals = list(db.scalars(m_stmt.order_by(ManualRecord.reference.desc(), ManualRecord.id.desc())))

    rows: list[dict] = []
    for b in bills:
        store = b.unit.store if b.unit else None
        rows.append({
            "reference": b.reference, "store_code": store.code if store else "—",
            "store_id": store.id if store else None,
            "unit_number": b.unit.number if b.unit else "—",
            "unit_id": b.unit_id, "bill_id": b.id, "record_id": None,
            "type_name": (types_by_id[b.record_type_id].name if b.record_type_id in types_by_id else "Conta"),
            "value": b.total_value, "due_date": b.due_date,
            "doc_id": b.document_id if (b.document and b.document.available) else None,
            "origin": "bill", "invoice_number": b.invoice_number,
        })
    for r in manuals:
        rows.append({
            "reference": r.reference, "store_code": r.store.code if r.store else "—",
            "store_id": r.store_id, "unit_number": (r.unit.number if r.unit else "—"),
            "unit_id": r.unit_id, "bill_id": None, "record_id": r.id,
            "type_name": types_by_id[r.record_type_id].name if r.record_type_id in types_by_id else "Lançamento",
            "value": r.value, "due_date": r.due_date, "doc_id": None,
            "origin": "manual", "invoice_number": None,
        })
    rows.sort(key=lambda r: (r["reference"], r["store_code"], r["unit_number"]), reverse=True)

    # Busca livre: nº UC (normaliza pontos/traços), código da loja, tipo, nº da nota, referência MM/AAAA.
    q_norm = (q or "").strip().lower()
    q_digits = normalize_uc(q)
    if q_norm:
        def hit(r):
            parts = [r["store_code"], r["unit_number"], r["type_name"], r["invoice_number"] or "",
                     f"{r['reference'].month:02d}/{r['reference'].year}", f"{r['reference'].year}"]
            text = " ".join(p.lower() for p in parts if p)
            if q_norm in text:
                return True
            # fallback por dígitos do UC: ajuda quando o usuário digitou "1206" ou "12060073018"
            return bool(q_digits and r["unit_number"] and q_digits in normalize_uc(r["unit_number"]))
        rows = [r for r in rows if hit(r)]

    return render(request, "bills/list.html", user=user, rows=rows[:500], total=len(rows),
                  stores=stores, types=types, q=q, store_id=store_id, type_id=type_id,
                  start=start or "", end=end or "", origin=origin)
