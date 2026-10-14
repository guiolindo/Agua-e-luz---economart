"""Lista única de contas e lançamentos — a tela para quem só quer achar e abrir uma nota."""
from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store, User
from app.security import current_user
from app.utils import formatting as fmt
from app.utils.parsing import normalize_uc
from app.web import render

router = APIRouter()
MONTH_NAMES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
               "novembro", "dezembro"]


def _plain(text: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()



def _parse_month(s: str | None) -> date | None:
    if not s:
        return None
    try:
        y, m = s.split("-")
        return date(int(y), int(m), 1)
    except (ValueError, AttributeError):
        return None


def _collect(db: Session, store_id, type_id, start, end, q, origin):
    """Lista plana filtrável (usada pela tela e pelo CSV). Mescla contas (EnergyBill) e lançamentos
    manuais (ManualRecord), ordenada pelo mês mais recente. Devolve (linhas, lojas, tipos)."""
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
            "reference": b.reference, "store_code": store.short_label if store else "—",
            "store_search": f"{store.code} {store.name or ''}" if store else "",
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
            "reference": r.reference, "store_code": r.store.short_label if r.store else "—",
            "store_search": f"{r.store.code} {r.store.name or ''}" if r.store else "",
            "store_id": r.store_id, "unit_number": (r.unit.number if r.unit else "—"),
            "unit_id": r.unit_id, "bill_id": None, "record_id": r.id,
            "type_name": types_by_id[r.record_type_id].name if r.record_type_id in types_by_id else "Lançamento",
            "value": r.value, "due_date": r.due_date, "doc_id": None,
            "origin": "manual", "invoice_number": None,
        })
    rows.sort(key=lambda r: (r["reference"], r["store_code"], r["unit_number"]), reverse=True)

    # Busca livre por palavras (todas precisam aparecer, em qualquer ordem): código e nome da loja, nº da UC
    # (com ou sem pontos), fornecedor, nº da nota e o mês em vários formatos ("jan/2026", "01/2026", "janeiro", "2026").
    # Assim "L05 jan/2026", "contagem colonial", "coelba setembro" e "1206" funcionam.
    words = [w for w in (q or "").strip().lower().split() if w]
    if words:
        def month_terms(ref):
            name = MONTH_NAMES[ref.month - 1]
            return [fmt.month_label(ref).lower(), f"{ref.month:02d}/{ref.year}", f"{ref.month}/{ref.year}",
                    f"{name}/{ref.year}", name, f"{name[:3]}/{str(ref.year)[2:]}", str(ref.year)]

        def hit(r):
            parts = [r["store_code"], r.get("store_search", ""), r["unit_number"], r["type_name"],
                     r["invoice_number"] or "", *month_terms(r["reference"])]
            text = " ".join(_plain(p) for p in parts if p)
            uc = normalize_uc(r["unit_number"] or "")
            for w in words:
                pw = _plain(w)
                if pw in text:
                    continue
                d = normalize_uc(w)
                if d and len(d) >= 3 and uc and d in uc:      # dígitos da UC: "1206" ou "12060073018"
                    continue
                return False
            return True
        rows = [r for r in rows if hit(r)]

    return rows, stores, types


@router.get("/notas")
def notas(request: Request, store_id: int | None = None, type_id: int | None = None,
          start: str | None = None, end: str | None = None, q: str = "",
          origin: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Tela única de contas: uma lista plana filtrável."""
    rows, stores, types = _collect(db, store_id, type_id, start, end, q, origin)
    return render(request, "bills/list.html", user=user, rows=rows[:500], total=len(rows),
                  stores=stores, types=types, q=q, store_id=store_id, type_id=type_id,
                  start=start or "", end=end or "", origin=origin)


def _csv_cell(v) -> str:
    """Texto seguro para planilha: neutraliza fórmulas (=, +, -, @) vindas de campos digitados por pessoas."""
    t = "" if v is None else str(v)
    return "'" + t if t[:1] in ("=", "+", "-", "@", "\t", "\r") else t


@router.get("/notas/export.xlsx")
def notas_xlsx(store_id: int | None = None, type_id: int | None = None, start: str | None = None, end: str | None = None,
               q: str = "", origin: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Mesmos filtros da tela, em planilha formatada (valores como número, datas como data)."""
    from fastapi.responses import Response

    from app.services import audit_service, xlsx_service

    rows, _, _ = _collect(db, store_id, type_id, start, end, q, origin)
    filters = "filtrado" if (store_id or type_id or start or end or q or origin) else "todos os registros"
    body = xlsx_service.bills_workbook(rows, filters)
    audit_service.log(db, user.id, "export", "bills", None, {"rows": len(rows), "formato": "xlsx", "q": q, "store_id": store_id})
    db.commit()
    return Response(body, media_type=xlsx_service.EXCEL_MIME,
                    headers={"Content-Disposition": 'attachment; filename="contas-economart.xlsx"'})


@router.get("/notas/export.csv")
def notas_csv(store_id: int | None = None, type_id: int | None = None, start: str | None = None, end: str | None = None,
              q: str = "", origin: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Mesmos filtros da tela, em CSV para Excel (separador ';', vírgula decimal, UTF-8 com BOM)."""
    import csv
    import io

    from fastapi.responses import Response

    rows, _, _ = _collect(db, store_id, type_id, start, end, q, origin)
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\r\n")
    w.writerow(["Mês de referência", "Loja", "Unidade consumidora", "Tipo", "Valor (R$)", "Vencimento", "Nota fiscal", "Origem"])
    for r in rows:
        w.writerow([f"{r['reference'].month:02d}/{r['reference'].year}", _csv_cell(r["store_code"]), _csv_cell(r["unit_number"]),
                    _csv_cell(r["type_name"]), f"{r['value']:.2f}".replace(".", ",") if r["value"] is not None else "",
                    r["due_date"].strftime("%d/%m/%Y") if r["due_date"] else "", _csv_cell(r["invoice_number"]),
                    "Foto/IA" if r["origin"] == "bill" else "Manual"])
    from app.services import audit_service

    audit_service.log(db, user.id, "export", "bills", None, {"rows": len(rows), "q": q, "store_id": store_id})
    db.commit()
    return Response("\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="contas-economart.csv"'})
