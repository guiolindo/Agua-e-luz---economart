import json
import re
from datetime import date, timedelta
from decimal import Decimal
from decimal import Decimal as D
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app import database
from app.models import ConsumerUnit, Document, EnergyBill, RecordType, Store
from app.models.mixins import utcnow
from app.services import chart_service, import_service
from app.services.extraction_service import MockExtractor
from app.services.gemini_service import (
    ExtractionError,
    GeminiService,
    build_prompt,
    message_for_code,
    parse_response_text,
)
from app.services.matching_service import find_store_by_hint, type_for_utility
from app.services.retention_service import purge_expired_documents
from tests.test_app_flow import _form_from_review, _make_store, _upload

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "cemig_set_2026.json").read_text())


# ---------- retenção de 6 meses ----------
def test_retention_purges_only_old_documents_and_keeps_data(db):
    old = Document(filename="a.png", content_type="image/png", size=3, sha256="a", data=b"abc",
                   created_at=utcnow() - timedelta(days=200))
    new = Document(filename="b.png", content_type="image/png", size=3, sha256="b", data=b"abc",
                   created_at=utcnow() - timedelta(days=30))
    db.add_all([old, new])
    db.commit()
    assert purge_expired_documents(db) == 1
    db.expire_all()
    assert old.data is None and old.purged_at and old.filename == "a.png" and not old.available
    assert new.data == b"abc" and new.available
    assert purge_expired_documents(db) == 0  # idempotente


def test_expired_document_returns_410_and_bill_survives(client, png, db):
    _make_store(client)
    job = _upload(client, png)
    form = {**_form_from_review(client.get(f"/import/{job}/review").text), "unit_mode": "matched"}
    client.post(f"/import/{job}/confirm", form)
    bill = db.query(EnergyBill).one()
    doc = db.get(Document, bill.document_id)
    doc.created_at = utcnow() - timedelta(days=400)
    db.commit()
    purge_expired_documents(db)
    r = client.get(f"/documents/{bill.document_id}")
    assert r.status_code == 410
    page = client.get(f"/units/{bill.unit_id}").text
    assert "Original expirado" in page and "Ver documento original" not in page
    db.expire_all()
    assert str(db.get(EnergyBill, bill.id).total_value) == "20505.00"  # dados ficam


# ---------- Gemini: erros, retentativa, parsing ----------
def test_friendly_error_messages_never_leak_details():
    assert "Limite de uso" in message_for_code(429) and "indisponível" in message_for_code(503)
    assert "chave" in message_for_code(403).lower() and "modelo" in message_for_code(404).lower()


def test_parse_tolerates_markdown_wrapped_json():
    wrapped = "Aqui está:\n```json\n" + json.dumps(FIXTURE) + "\n```"
    assert parse_response_text(wrapped).total_value == 20505.0


def test_prompt_includes_catalog_and_no_guess_rules():
    p = build_prompt("- CD300 (CD Ribeirão) ← CD 300")
    assert "ZERO CHUTE" in p and "- CD300" in p and "À MÃO" in p
    assert "Catálogo" not in build_prompt(None)


def _fake_genai(monkeypatch, outcomes):
    """Substitui genai.Client; cada chamada consome um resultado (exceção ou texto)."""
    from google import genai

    calls = []

    class Models:
        def generate_content(self, **kw):
            calls.append(kw)
            out = outcomes.pop(0)
            if isinstance(out, Exception):
                raise out
            return type("R", (), {"text": out})()

    class Client:
        def __init__(self, **kw):
            self.models = Models()

    monkeypatch.setattr(genai, "Client", Client)
    return calls


def test_gemini_retries_on_429_then_succeeds(monkeypatch):
    from google.genai import errors

    calls = _fake_genai(monkeypatch, [errors.APIError(429, {"error": {"message": "x"}}), json.dumps(FIXTURE)])
    sleeps = []
    svc = GeminiService(api_key="k", model="m", sleep=sleeps.append)
    assert svc.extract(b"x", "image/png", "- CD300").total_value == 20505.0
    assert len(calls) == 2 and sleeps == [2]


def test_gemini_does_not_retry_on_auth_error_and_hides_details(monkeypatch):
    from google.genai import errors

    calls = _fake_genai(monkeypatch, [errors.APIError(403, {"error": {"message": "key=SECRET123"}})])
    with pytest.raises(ExtractionError) as exc:
        GeminiService(api_key="k", model="m", sleep=lambda s: None).extract(b"x", "image/png")
    assert len(calls) == 1 and "SECRET123" not in str(exc.value) and "chave" in str(exc.value).lower()


def test_gemini_gives_up_after_three_503(monkeypatch):
    from google.genai import errors

    calls = _fake_genai(monkeypatch, [errors.APIError(503, {}) for _ in range(3)])
    with pytest.raises(ExtractionError, match="indisponível"):
        GeminiService(api_key="k", model="m", sleep=lambda s: None).extract(b"x", "image/png")
    assert len(calls) == 3


# ---------- anotação à mão e distribuidora ----------
def test_store_hint_matches_code_alias_and_ignores_formatting(db):
    db.add_all([Store(code="CD300", aliases=["CD Rib Neves"]), Store(code="CD301", name="Campina Verde")])
    db.commit()
    assert find_store_by_hint(db, "CD 300").code == "CD300" and find_store_by_hint(db, "cd-rib neves").code == "CD300"
    assert find_store_by_hint(db, "campina  verde").code == "CD301"
    assert find_store_by_hint(db, "CD 30") is None and find_store_by_hint(db, "") is None  # nunca chuta


def test_type_for_utility(db):
    types = db.query(RecordType).all()
    assert type_for_utility(types, "COMPANHIA DE ELETRICIDADE DO ESTADO DA BAHIA - COELBA").code == "coelba"
    assert type_for_utility(types, "CEMIG Distribuição S.A.").code == "cemig"
    assert type_for_utility(types, "Outra Energia") is None


def test_review_warns_when_handwritten_store_differs_from_unit_store(client, png):
    _make_store(client, code="CD300", unit=None)   # a anotação à mão na foto diz "CD 300"
    _make_store(client, code="LOJA9")              # mas a UC lida está cadastrada em outra loja
    job = _upload(client, png)
    html = client.get(f"/import/{job}/review").text
    assert "anotação à mão" in html and "LOJA9" in html


def test_no_warning_when_handwritten_note_matches(client, png):
    _make_store(client, code="CD300")
    job = _upload(client, png)
    assert "anotação à mão" not in client.get(f"/import/{job}/review").text


def test_coelba_bill_creates_unit_with_coelba_type_and_hint_preselects_store(client, png, db, monkeypatch):
    payload = {"utility": "COELBA", "consumer_unit_number": "0123456789", "reference_month": "2026-09",
               "total_value": 3500.5, "consumption_kwh": 4200, "days": 30, "handwritten_note": "SAJ"}
    monkeypatch.setattr(import_service, "get_extractor", lambda: MockExtractor(payload))
    r = client.post("/stores", {"code": "CD400", "aliases": "SAJ, Santo Antonio"})
    store_id = int(r.headers["location"].split("/")[2])
    job = _upload(client, png)
    html = client.get(f"/import/{job}/review").text
    assert "Unidade consumidora não cadastrada" in html and f'<option value="{store_id}" selected>' in html
    form = {**_form_from_review(html), "unit_mode": "new", "new_store_id": str(store_id), "new_number": "0123456789"}
    assert client.post(f"/import/{job}/confirm", form).status_code == 303
    db.expire_all()
    unit = db.query(ConsumerUnit).one()
    bill = db.query(EnergyBill).one()
    assert unit.record_type.code == "coelba" and bill.record_type_id == unit.record_type_id
    assert bill.consumption_total == Decimal("4200") and bill.consumption_hp is None


def test_admin_can_create_bill_type_for_new_utility(client, db):
    client.post("/types", {"name": "ENERGISA", "kind": "bill"})
    rt = db.query(RecordType).filter_by(code="energisa").one()
    assert rt.is_bill and rt.fields == []


# ---------- relatório impresso ----------
def test_print_report_has_summary_blocks_and_variation(client, db):
    store_id = _make_store(client)
    unit = db.query(ConsumerUnit).one()
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    for m, v in ((8, "19536.31"), (9, "20505.00")):
        client.post("/manual", {"store_id": store_id, "unit_id": unit.id, "type_id": cemig.id, "reference": f"2026-{m:02d}",
                                "total_value": v, "days": "31"})
    html = client.get(f"/stores/{store_id}/report?start=2026-08&end=2026-09").text
    assert "GRÁFICO POR LOJA" in html and "CD300" in html and "↑ 4,96%" in html and "Dias de consumo" in html
    assert "R$ 20.505,00" in html and "data-print" in html


# ---------- migração leve de colunas ----------
def test_ensure_columns_adds_missing_nullable_columns(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE stores (id INTEGER PRIMARY KEY, code VARCHAR(40), name VARCHAR(200), "
                       "location VARCHAR(200), notes TEXT, active BOOLEAN, created_at DATETIME, updated_at DATETIME)"))
    database.ensure_columns(eng)
    with eng.begin() as c:
        cols = {r[1] for r in c.execute(text("PRAGMA table_info(stores)"))}
    assert "aliases" in cols


# ---------- impressão de uma conta com gráficos ----------
def _seed_bills(client, db):
    store_id = _make_store(client)
    unit = db.query(ConsumerUnit).one()
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    for m, v in ((7, "18835.58"), (8, "19536.31"), (9, "20505.00")):
        client.post("/manual", {"store_id": store_id, "unit_id": unit.id, "type_id": cemig.id, "reference": f"2026-{m:02d}",
                                "total_value": v, "days": "30", "consumption_hp": "5.388", "consumption_hfp": "58.372",
                                "demand_hp": "132", "demand_hfp": "181", "contracted_demand": "210"})
    return unit


def test_bill_print_page_shows_selected_bill_variation_and_charts(client, db):
    unit = _seed_bills(client, db)
    sep = db.query(EnergyBill).filter_by(unit_id=unit.id).order_by(EnergyBill.reference.desc()).first()
    r = client.get(f"/bills/{sep.id}/print")
    assert r.status_code == 200
    html = r.text
    assert "SET/2026" in html and "R$ 20.505,00" in html and "↑ 4,96%" in html and "vs. AGO/2026" in html
    assert 'id="c-value"' in html and 'id="c-cons"' in html and 'id="c-dem"' in html and "data-print" in html
    assert html.count("<option value=") >= 3                              # seletor para trocar de conta/mês
    payload = json.loads(re.search(r'id="bill-data">(.*?)</script>', html, re.S).group(1))
    assert payload["selected"] == 11 and payload["labels"][11] == "SET/26"   # mês da conta em destaque no gráfico
    assert payload["series"]["value"][9:] == [18835.58, 19536.31, 20505.0] and payload["series"]["contracted"][11] == 210.0
    assert client.get(f"/units/{unit.id}").text.count("/print") == 3      # botão Imprimir em cada conta


def test_bill_print_includes_original_photo_only_when_asked_and_available(client, png, db):
    _make_store(client)
    job = _upload(client, png)
    client.post(f"/import/{job}/confirm", {**_form_from_review(client.get(f"/import/{job}/review").text), "unit_mode": "matched"})
    bill = db.query(EnergyBill).one()
    assert "Documento original" not in client.get(f"/bills/{bill.id}/print").text
    with_doc = client.get(f"/bills/{bill.id}/print?doc=1").text
    assert f'src="/documents/{bill.document_id}"' in with_doc and "Itens faturados" in with_doc
    doc = db.get(Document, bill.document_id)
    doc.data, doc.purged_at = None, utcnow()
    db.commit()
    assert f'src="/documents/{bill.document_id}"' not in client.get(f"/bills/{bill.id}/print?doc=1").text  # expirado


def test_bill_print_404_and_requires_login(client):
    assert client.get("/bills/9999/print").status_code == 404


# ---------- folha de impressão: UMA folha com resumo + gráfico + dados ----------
def test_print_sheet_is_a_single_sheet_with_summary_chart_and_info_for_one_supplier(client, db):
    from scripts import seed_demo
    seed_demo.main()
    store = db.query(Store).filter_by(code="CD300").one()
    html = client.get(f"/stores/{store.id}/report?start=2026-01&end=2026-10&by=due").text
    assert html.count("<canvas") == 1 and 'data-fit="700"' in html                 # 1 gráfico, ajustado a 1 página
    assert "RESUMO MENSAL" in html and "IMÓVEL: CEMIG" in html and "496.587,37" in html  # resumo de todos + 1 imóvel
    assert 'class="infostrip"' in html and "12.060.073.018-19" in html and "Dias de consumo" in html
    assert 'class="rblock pagebreak"' not in html


def test_print_sheet_can_pick_the_supplier_or_print_all_one_per_sheet(client, db):
    from scripts import seed_demo
    seed_demo.main()
    store = db.query(Store).filter_by(code="CD300").one()
    ll = db.query(RecordType).filter_by(code="ll-energia").one()
    one = client.get(f"/stores/{store.id}/report?start=2026-01&end=2026-09&type_id={ll.id}").text
    assert "IMÓVEL: LL ENERGIA" in one and one.count("<canvas") == 1 and 'class="infostrip"' not in one
    every = client.get(f"/stores/{store.id}/report?start=2026-01&end=2026-10&all=1").text
    assert every.count("<canvas") == 6 and every.count("pagebreak") == 5 and "data-fit" not in every


def test_print_sheet_has_kpis_extra_rows_footer_and_highlights_last_month_with_data(client, db):
    from scripts import seed_demo
    seed_demo.main()
    store = db.query(Store).filter_by(code="CD300").one()
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    unit = db.query(ConsumerUnit).filter_by(store_id=store.id).one()
    for b in db.query(EnergyBill).filter_by(unit_id=unit.id).all():                 # consumo/demanda só nas contas com leitura
        b.consumption_hfp, b.demand_hfp = D("50000"), D("180")
    db.commit()
    data = chart_service.report_data(db, store, date(2026, 1, 1), date(2026, 10, 1), by="reference", type_id=cemig.id)
    assert data["last_idx"] == 8                                                     # SET/2026 (out/2026 está vazio na referência)
    blk = data["blocks"][0]
    assert [k["label"] for k in blk["kpis"]] == ["Total no período", "Média mensal", "Maior mês", "Menor mês", "Última variação"]
    assert blk["kpis"][2]["sub"] == "MAR/2026" and blk["kpis"][3]["sub"] == "MAI/2026"       # maior e menor mês
    assert blk["cons"][0] == D("50000") and blk["dem"][0] == D("180")
    html = client.get(f"/stores/{store.id}/report?start=2026-01&end=2026-10&type_id={cemig.id}").text
    assert 'class="chips"' in html and "Consumo (kWh)" in html and "Demanda HFP (kW)" in html and 'class="sheet-foot"' in html
    assert html.count("lastcol") >= 2 and "ENERGIA — GRÁFICO POR LOJA" in html
