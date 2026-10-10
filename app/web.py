"""Configuração do Jinja2 e helper de renderização."""
import hashlib
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.security import csrf_token
from app.utils import formatting as fmt
from app.utils.timezone import dt_br

BASE_DIR = Path(__file__).resolve().parent


def _asset_version() -> str:
    """Hash curto dos CSS/JS que mudam, para derrotar o cache do browser quando
    qualquer um deles mudar. Templates incluem ?v={{ ASSET_VERSION }} nos links.
    Vendor fixo (chart.umd.min.js) fica de fora — nunca muda."""
    h = hashlib.sha1()
    for rel in ("static/css/app.css", "static/js/app.js", "static/js/chart_panel.js", "static/js/director.js", "static/js/presentation.js", "static/css/presentation.css"):
        p = BASE_DIR / rel
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["retention_days"] = get_settings().document_retention_days
def greeting_now() -> str:
    from app.utils.timezone import local_now

    h = local_now().hour
    return "Bom dia" if h < 12 else "Boa tarde" if h < 18 else "Boa noite"


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def today_long() -> str:
    from app.utils.timezone import local_today

    d = local_today()
    dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    return f"{dias[d.weekday()]}, {d.day} de {meses[d.month - 1]} de {d.year}"


from app.utils.presentation import presentation_open  # noqa: E402

templates.env.globals["presentation_open"] = presentation_open   # chamada a cada render: o botão some sozinho no prazo
templates.env.globals["greeting_now"] = greeting_now
templates.env.globals["plural"] = plural
templates.env.globals["today_long"] = today_long
templates.env.globals["login_max_attempts"] = get_settings().max_login_attempts
templates.env.globals["login_block_minutes"] = get_settings().login_block_minutes
templates.env.globals["ASSET_VERSION"] = _asset_version()
templates.env.filters.update(brl=fmt.brl, num=fmt.num, pct=fmt.pct, month_label=fmt.month_label, date_br=fmt.date_br, dt_br=dt_br)


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
