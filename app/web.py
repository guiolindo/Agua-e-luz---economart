"""Configuração do Jinja2 e helper de renderização."""
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.security import csrf_token
from app.utils import formatting as fmt

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["retention_days"] = get_settings().document_retention_days
templates.env.filters.update(brl=fmt.brl, num=fmt.num, pct=fmt.pct, month_label=fmt.month_label, date_br=fmt.date_br)


def flash(request: Request, message: str, level: str = "ok") -> None:
    request.session.setdefault("flash", []).append({"text": message, "level": level})


def render(request: Request, name: str, status_code: int = 200, **ctx):
    ctx.setdefault("user", None)
    ctx["csrf_token"] = csrf_token(request)
    ctx["csp_nonce"] = getattr(request.state, "csp_nonce", "")
    ctx["login_stamp"] = request.session.get("iat", "")
    ctx["flashes"] = request.session.pop("flash", [])
    ctx["path"] = request.url.path
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
