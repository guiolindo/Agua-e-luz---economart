import io
from datetime import date
from decimal import Decimal as D

from openpyxl import load_workbook

from app import database
from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _seed():
    with database.SessionLocal() as db:
        cemig = db.query(RecordType).filter_by(code="cemig").one()
        manual = db.query(RecordType).filter_by(kind="manual").first()
        for code, name in (("A1", "Loja A"), ("=HYPERLINK(\"http://x\")", "=cmd|' /C calc'!A0")):
            s = Store(code=code, name=name, region="MG")
            db.add(s)
            db.flush()
            u = ConsumerUnit(store_id=s.id, number=f"9{len(code)}", number_normalized=f"9{len(code)}", record_type_id=cemig.id)
            db.add(u)
            db.flush()
            for m, v in ((7, 1000), (8, 1200)):
                db.add(EnergyBill(unit_id=u.id, record_type_id=cemig.id, reference=date(2026, m, 1), total_value=D(v),
                                  due_date=date(2026, m, 20), invoice_number="=1+1"))
            db.add(ManualRecord(store_id=s.id, record_type_id=manual.id, reference=date(2026, 8, 1), value=D(300)))
        db.commit()


def _open(resp):
    return load_workbook(io.BytesIO(resp.content))


def test_director_xlsx_is_a_formatted_workbook_with_real_numbers(client):
    _seed()
    r = client.get("/diretoria/export.xlsx")
    assert r.status_code == 200 and r.headers["content-type"].startswith(XLSX)
    assert "painel-diretoria-economart.xlsx" in r.headers["content-disposition"]
    wb = _open(r)
    assert wb.sheetnames == ["Resumo", "Lojas", "Mês a mês", "Fornecedores", "Pendências"]
    lojas = wb["Lojas"]
    # cabeçalho na linha 5, dados a partir da 6; valores numéricos com formato de moeda (não texto)
    assert lojas["A5"].value == "Loja" and lojas.freeze_panes == "B6" and lojas.auto_filter.ref
    total = lojas["D6"]
    assert isinstance(total.value, (int, float)) and "R$" in total.number_format
    assert lojas["E6"].number_format.startswith("0.0%")
    assert wb["Mês a mês"]["A5"].value == "Loja"


def test_user_text_never_becomes_a_formula(client):
    _seed()
    wb = _open(client.get("/diretoria/export.xlsx"))
    cells = [c for row in wb["Lojas"].iter_rows(min_row=6, max_col=2) for c in row if isinstance(c.value, str)]
    evil = [c for c in cells if c.value.startswith("=")]
    assert evil and all(c.data_type == "s" for c in evil)
    # a loja maliciosa também aparece como texto na planilha de contas
    bills = _open(client.get("/notas/export.xlsx"))["Contas"]
    inv = [c for row in bills.iter_rows(min_row=6, min_col=7, max_col=7) for c in row if c.value == "=1+1"]
    assert inv and all(c.data_type == "s" for c in inv)


def test_bills_xlsx_has_typed_cells_and_respects_filters(client):
    _seed()
    ws = _open(client.get("/notas/export.xlsx"))["Contas"]
    assert ws["A5"].value == "Mês de referência" and ws.freeze_panes == "C6"
    first = ws["E6"]
    assert isinstance(first.value, (int, float)) and "R$" in first.number_format
    assert ws["F6"].number_format == "dd/mm/yyyy"
    # filtro: só Foto/IA -> nenhuma linha manual
    only_bills = _open(client.get("/notas/export.xlsx?origin=bill"))["Contas"]
    origins = {only_bills.cell(row=r, column=8).value for r in range(6, only_bills.max_row + 1) if only_bills.cell(row=r, column=8).value}
    assert origins == {"Foto/IA"}


def test_xlsx_exports_are_audited_and_need_login(client):
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app).get("/diretoria/export.xlsx", follow_redirects=False).status_code == 303
    assert TestClient(app).get("/notas/export.xlsx", follow_redirects=False).status_code == 303
    client.get("/diretoria/export.xlsx")
    from app.models import AuditLog

    with database.SessionLocal() as db:
        rows = db.query(AuditLog).filter_by(action="export").all()
    assert any((r.details or {}).get("formato") == "xlsx" for r in rows)
