from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import director_required
from app.services import alert_service, executive_service
from app.utils import formatting as fmt
from app.utils.parsing import parse_reference
from app.web import render

router = APIRouter()


TABS = (("geral", "Visão geral", "Quanto gastamos e se está pior"),
        ("lojas", "Lojas", "Ranking, variação, evolução, custo por kWh e comparação entre lojas"),
        ("evitavel", "Gasto evitável", "Ultrapassagem, energia reativa, juros e multa: o que se paga à toa"),
        ("contratos", "Contratos", "Demanda contratada × usada: quem deve aumentar ou reduzir"),
        ("ano", "Ano", "Acumulado do ano, projeção e por que o gasto mudou"))


@router.get("/diretoria")
def executive_panel(request: Request, start: str | None = None, end: str | None = None, by: str = "reference",
                    region: str | None = None, types: list[int] | None = None, aba: str = "geral",
                    user: User = Depends(director_required), db: Session = Depends(get_db)):
    from urllib.parse import urlencode

    from app.models.mixins import utcnow
    from app.services import director_extra as extra

    from app.services.demand_flag import demand_in_use

    by = "due" if by == "due" else "reference"
    dem = demand_in_use()                        # nenhuma conta com demanda (lojas de baixa tensão): o assunto some das telas
    tabs = [t for t in TABS if dem or t[0] != "contratos"]
    aba = aba if aba in {t[0] for t in tabs} else "geral"
    data = executive_service.build(db, parse_reference(start), parse_reference(end), by, types or None, region or None)
    focus = data["months"][data["focus_idx"]] if data["months"] else data["end"]
    avoid = extra.avoidable(db, data["start"], data["end"], by, region or None, types or None)
    contracts = extra.contracts(db, data["end"], region or None) if dem else {"rows": [], "counts": {}}
    year = extra.year_view(db, focus, by, region or None, types or None)
    insights = executive_service.insights(data)
    why = extra.decomposition_sentence(year["mom"], *year["mom_label"])
    if why:
        insights.insert(1 if insights else 0, why)
    if avoid["total"]:
        insights.append({"tone": "bad", "text": f"Gasto evitável no período (ultrapassagem, energia reativa, juros e multa): "
                                                f"{fmt.brl(avoid['total'], 0)}. Veja a aba Gasto evitável."})
    base_qs = urlencode([(k, v) for k, v in request.query_params.multi_items() if k != "aba" and v])
    extra_payload = {
        "avoid": {"labels": avoid["labels"], "series": [{"label": s["label"], "data": s["data"]} for s in avoid["series"]]},
        "year": {"year": year["year"], **year["chart"]},
        "contracts": {r["label"]: r["series"] for r in contracts["rows"]},
    }
    return render(request, "director/panel.html", user=user, payload=executive_service.client_payload(data), printed_at=utcnow(),
                  alerts_open=alert_service.counts(db), insights=insights, aba=aba, tabs=tabs, base_qs=base_qs,
                  avoid_cats=[c for c in avoid["categories"] if dem or c["key"] != "ultrapassagem" or c["total"]],
                  avoid=avoid, avoid_labels=extra.CAT_LABEL, contracts=contracts, year=year, extra_payload=extra_payload,
                  avoid_share=float(avoid["total"]) / data["kpi"]["total"] * 100 if data["kpi"]["total"] else None, **data)


@router.get("/diretoria/export.csv")
def executive_csv(start: str | None = None, end: str | None = None, by: str = "reference", region: str | None = None,
                  types: list[int] | None = None, user: User = Depends(director_required), db: Session = Depends(get_db)):
    """Comparativo entre lojas em CSV (mesmos filtros da tela), pronto para o Excel."""
    import csv
    import io

    from fastapi.responses import Response

    from app.routes.bills import _csv_cell
    from app.services import audit_service

    data = executive_service.build(db, parse_reference(start), parse_reference(end), "due" if by == "due" else "reference",
                                   types or None, region or None)

    def num(v, places=2):
        return "" if v is None else f"{v:.{places}f}".replace(".", ",")

    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\r\n")
    focus, prev = data["focus_label"], data["prev_label"]
    dem = data.get("has_demand")
    w.writerow(["Loja", "Nome", "Região", "Total no período (R$)", "% da empresa", "Média por mês (R$)",
                "Variação média vs. período anterior (%)", f"{focus} (R$)", f"Variação vs. {prev} (%)", "R$/kWh"] + (["Demanda usada (%)"] if dem else []))
    for r in data["rows"]:
        w.writerow([_csv_cell(r["code"]), _csv_cell(r["name"]), _csv_cell(r["region"]), num(r["total"]), num(r["share"], 1), num(r["avg"]),
                    num(r["vs_prev_period"]["pct"], 1), num(r["last"]), num(r["vs_last_month"]["pct"], 1), num(r["rs_kwh"], 3)]
                   + ([num(r["demand_use"], 1)] if dem else []))
    audit_service.log(db, user.id, "export", "bills", None, {"painel": "diretoria", "lojas": len(data["rows"])})
    db.commit()
    return Response("\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="comparativo-lojas-economart.csv"'})


@router.get("/diretoria/export.pptx")
def executive_pptx(start: str | None = None, end: str | None = None, by: str = "reference", region: str | None = None,
                   types: list[int] | None = None, user: User = Depends(director_required), db: Session = Depends(get_db)):
    """Apresentação PowerPoint do painel (capa, destaques, gráficos nativos, um slide por loja), mesmos filtros da tela."""
    from fastapi.responses import Response

    from app.services import audit_service, dashboard_service, pptx_service
    from app.services.calculation_service import add_months

    data = executive_service.build(db, parse_reference(start), parse_reference(end), "due" if by == "due" else "reference",
                                   types or None, region or None)
    pending = []
    if data["months"]:
        month = data["months"][data["focus_idx"]]
        pending = dashboard_service.pending_items(db, month, add_months(month, -1))
    filters = ("por vencimento" if by == "due" else "por mês de referência") + (f" · região {region}" if region else "")
    body = pptx_service.executive_deck(data, executive_service.insights(data), pending, filters, user.username)
    audit_service.log(db, user.id, "export", "bills", None, {"painel": "diretoria", "formato": "pptx", "lojas": len(data["rows"])})
    db.commit()
    return Response(body, media_type=pptx_service.PPTX_MIME,
                    headers={"Content-Disposition": 'attachment; filename="painel-diretoria-economart.pptx"'})


@router.get("/diretoria/export.xlsx")
def executive_xlsx(start: str | None = None, end: str | None = None, by: str = "reference", region: str | None = None,
                   types: list[int] | None = None, user: User = Depends(director_required), db: Session = Depends(get_db)):
    """Planilha formatada do painel (Resumo, Lojas, Mês a mês, Fornecedores, Pendências), mesmos filtros da tela."""
    from fastapi.responses import Response

    from app.services import audit_service, dashboard_service, xlsx_service
    from app.services.calculation_service import add_months

    data = executive_service.build(db, parse_reference(start), parse_reference(end), "due" if by == "due" else "reference",
                                   types or None, region or None)
    pending = []
    if data["months"]:
        month = data["months"][data["focus_idx"]]
        pending = dashboard_service.pending_items(db, month, add_months(month, -1))
    filters = ("por vencimento" if by == "due" else "por mês de referência") + (f" · região {region}" if region else "")
    body = xlsx_service.executive_workbook(data, executive_service.insights(data), pending, filters)
    audit_service.log(db, user.id, "export", "bills", None, {"painel": "diretoria", "formato": "xlsx", "lojas": len(data["rows"])})
    db.commit()
    return Response(body, media_type=xlsx_service.EXCEL_MIME,
                    headers={"Content-Disposition": 'attachment; filename="painel-diretoria-economart.xlsx"'})
