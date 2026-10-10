"""Aceitação: a folha impressa do sistema reproduz a planilha 'ENERGIA — GRÁFICO POR LOJA' da CD300, ao centavo."""
import re

from sqlalchemy import select

from app.models import Store

# Linha "Total geral" da planilha impressa (agrupada por mês de VENCIMENTO), jan/2026 a out/2026, e o total final.
PLANILHA_TOTAIS = ["47.458,41", "52.912,20", "44.564,10", "85.703,20", "51.675,39", "46.157,01", "50.521,75", "50.304,35",
                   "46.785,96", "20.505,00"]
PLANILHA_TOTAL_FINAL = "496.587,37"
# Linhas da tabela do imóvel (CEMIG Distribuição), por mês de REFERÊNCIA, jan/2026 a set/2026.
PLANILHA_VALOR_FATURA = ["22.543,10", "19.560,38", "24.144,83", "23.153,69", "16.959,69", "18.020,14", "18.835,58", "19.536,31", "20.505,00"]
PLANILHA_DIAS = ["31", "28", "31", "30", "31", "30", "31", "31", "30"]


def _row(html: str, label: str) -> list[str]:
    m = re.search(r"<tr[^>]*>\s*<t[dh][^>]*>(?:<strong>)?" + re.escape(label) + r"(?:</strong>)?</t[dh]>(.*?)</tr>", html, re.S)
    assert m, f"linha '{label}' não encontrada"
    return [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]


def test_printed_sheet_matches_the_original_spreadsheet_to_the_cent(client):
    from scripts import seed_demo

    seed_demo.main()
    from app import database

    with database.SessionLocal() as db:
        sid = db.scalar(select(Store.id).where(Store.code == "CD300"))
    html = client.get(f"/stores/{sid}/report").text                       # padrão = "Como na planilha"
    totais = _row(html, "Total geral")
    assert totais[: len(PLANILHA_TOTAIS)] == PLANILHA_TOTAIS and PLANILHA_TOTAL_FINAL in totais
    assert "resumo por mês de vencimento" in html and "gráfico por mês de referência" in html
    valores = [v.replace("R$", "").strip() for v in _row(html, "Valor da fatura")]
    assert valores[-len(PLANILHA_VALOR_FATURA):] == PLANILHA_VALOR_FATURA          # a folha pode trazer dez/2025 antes de jan
    assert _row(html, "Dias de consumo")[-len(PLANILHA_DIAS):] == PLANILHA_DIAS


def test_report_modes_reference_and_due_still_work(client):
    from scripts import seed_demo

    seed_demo.main()
    from app import database

    with database.SessionLocal() as db:
        sid = db.scalar(select(Store.id).where(Store.code == "CD300"))
    ref = client.get(f"/stores/{sid}/report?by=reference&start=2026-01&end=2026-09").text
    due = client.get(f"/stores/{sid}/report?by=due&start=2026-01&end=2026-10").text
    assert _row(ref, "Total geral")[0] == "47.172,26" and _row(due, "Total geral")[0] == "47.458,41"


def test_nothing_from_the_original_spreadsheet_was_dropped_and_extras_were_added(client):
    from scripts import seed_demo

    seed_demo.main()
    from app import database

    with database.SessionLocal() as db:
        sid = db.scalar(select(Store.id).where(Store.code == "CD300"))
    html = client.get(f"/stores/{sid}/report").text
    # tudo o que a planilha tinha
    for item in ("ENERGIA — GRÁFICO POR LOJA", "RESUMO MENSAL", "IMÓVEL:", "Total geral", "Valor da fatura", "Dias de consumo", "Variação (%)",
                 "CEMIG Geração e Transmissão", "LL Energia", "Câmara de Comercialização de Energia", "Manutenção de Gerador",
                 "Compra de combustível para gerador", "Variação (%)", "<canvas"):
        assert item in html, item
    # melhorias somadas
    for extra in ("Média/mês", "% do total", "Variação do total (%)", "compo-bar", "MÉDIA MENSAL", "MAIOR MÊS", "MENOR MÊS"):
        assert extra.lower() in html.lower(), extra
    assert _row(html, "CEMIG")[-1].endswith("%") and _row(html, "Total geral")[-1] == "100%"


def _manual(db, store_id, type_id, ref, value, due=None, acct=None):
    from decimal import Decimal

    from app.models import ManualRecord

    db.add(ManualRecord(store_id=store_id, record_type_id=type_id, reference=ref, value=Decimal(value), due_date=due, accounting_date=acct))
    db.commit()


def test_manual_expense_month_follows_due_then_accounting_then_reference(client):
    """Gerador: na tabela 'por vencimento' vale o vencimento; sem ele, a data de contabilização; sem as duas, a referência."""
    from datetime import date

    from app import database
    from app.models import RecordType
    from app.services import chart_service
    from app.models import Store

    with database.SessionLocal() as db:
        s = Store(code="G1", name="Loja G1")
        db.add(s)
        db.flush()
        ger = db.query(RecordType).filter_by(code="manutencao-gerador").one() if db.query(RecordType).filter_by(code="manutencao-gerador").count() \
            else db.query(RecordType).filter(RecordType.kind == "manual").first()
        _manual(db, s.id, ger.id, date(2026, 3, 1), "100", acct=date(2026, 5, 20))                       # só contabilização -> maio
        _manual(db, s.id, ger.id, date(2026, 3, 1), "200", due=date(2026, 6, 10), acct=date(2026, 5, 20))  # as duas -> vale o vencimento (junho)
        _manual(db, s.id, ger.id, date(2026, 3, 1), "400")                                                # nenhuma -> referência (março)
        due = chart_service.report_data(db, s, date(2026, 3, 1), date(2026, 7, 1), "due", ger.id)
        ref = chart_service.report_data(db, s, date(2026, 3, 1), date(2026, 7, 1), "reference", ger.id)
    by_month = {m.month: t for m, t in zip(due["sum_months"], due["summary"]["totals"]) if t is not None}
    assert by_month == {3: 400, 5: 100, 6: 200}
    assert {m.month: t for m, t in zip(ref["sum_months"], ref["summary"]["totals"]) if t is not None} == {3: 700}


def test_manual_form_saves_and_shows_the_accounting_date(client, db):
    from datetime import date

    from app.models import ManualRecord, RecordType, Store

    s = Store(code="G2", name="Loja G2")
    db.add(s)
    db.flush()
    ger = db.query(RecordType).filter(RecordType.kind == "manual", RecordType.code != "ll-energia").first()
    db.commit()
    page = client.get("/manual?modo=loja").text
    assert "Data de contabilização (opcional)" in page and "Para despesas sem vencimento" in page
    r = client.post("/manual", {"store_id": s.id, "type_id": ger.id, "reference": "2026-03", "value": "1500,00", "accounting_date": "2026-05-20"})
    assert r.status_code in (303, 200)
    rec = db.query(ManualRecord).filter_by(store_id=s.id).one()
    assert rec.accounting_date == date(2026, 5, 20) and rec.due_date is None and rec.group_date == date(2026, 5, 20)
    assert "contab." in client.get("/notas").text
    bad = client.post("/manual", {"store_id": s.id, "type_id": ger.id, "reference": "2026-04", "value": "10", "accounting_date": "31/31/9999"})
    assert bad.status_code == 400 and "Data inválida" in bad.text
