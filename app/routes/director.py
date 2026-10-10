from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import director_required
from app.services import alert_service, executive_service
from app.utils.parsing import parse_reference
from app.web import render

router = APIRouter()


@router.get("/diretoria")
def executive_panel(request: Request, start: str | None = None, end: str | None = None, by: str = "reference",
                    region: str | None = None, types: list[int] | None = None,
                    user: User = Depends(director_required), db: Session = Depends(get_db)):
    data = executive_service.build(db, parse_reference(start), parse_reference(end), "due" if by == "due" else "reference",
                                   types or None, region or None)
    from app.models.mixins import utcnow

    return render(request, "director/panel.html", user=user, payload=executive_service.client_payload(data), printed_at=utcnow(), alerts_open=alert_service.counts(db),
                  insights=executive_service.insights(data), **data)


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
    w.writerow(["Loja", "Nome", "Região", "Total no período (R$)", "% da empresa", "Média por mês (R$)",
                "Variação média vs. período anterior (%)", f"{focus} (R$)", f"Variação vs. {prev} (%)", "R$/kWh", "Demanda usada (%)"])
    for r in data["rows"]:
        w.writerow([_csv_cell(r["code"]), _csv_cell(r["name"]), _csv_cell(r["region"]), num(r["total"]), num(r["share"], 1), num(r["avg"]),
                    num(r["vs_prev_period"]["pct"], 1), num(r["last"]), num(r["vs_last_month"]["pct"], 1), num(r["rs_kwh"], 3), num(r["demand_use"], 1)])
    audit_service.log(db, user.id, "export", "bills", None, {"painel": "diretoria", "lojas": len(data["rows"])})
    db.commit()
    return Response("\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="comparativo-lojas-economart.csv"'})
