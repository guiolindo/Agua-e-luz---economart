from app.routes.bills import _csv_cell
from tests.test_app_flow import _make_store
from tests.test_director import _user
from tests.test_roles import _seed_bill


def test_csv_export_matches_filters_and_is_excel_friendly(client, db):
    store_id = _make_store(client)
    _seed_bill(client, db, store_id)
    r = client.get("/notas/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    body = r.content.decode("utf-8")
    assert body.startswith("﻿") and "Mês de referência;Loja;" in body
    assert "08/2026" in body and "1000,00" in body
    assert len(client.get("/notas/export.csv?q=nada-que-exista").text.strip().splitlines()) == 1   # só o cabeçalho
    from app.models import AuditLog
    assert db.query(AuditLog).filter_by(action="export").count() == 2


def test_csv_neutralizes_spreadsheet_formulas():
    assert _csv_cell("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert _csv_cell("+1") == "'+1" and _csv_cell("@cmd") == "'@cmd" and _csv_cell("CD300") == "CD300" and _csv_cell(None) == ""


def test_viewer_can_export_but_anonymous_cannot(client, db):
    from fastapi.testclient import TestClient
    from app.main import app
    _make_store(client)
    assert _user(client, "con7", "viewer").get("/notas/export.csv").status_code == 200
    assert TestClient(app).get("/notas/export.csv", follow_redirects=False).status_code == 303
