import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app import (  # noqa: F401  (models registra as tabelas no metadata)
    database,
    db_migrate,
    models,
    security,
)
from app.config import get_settings
from app.middleware import (
    DropEmptyQueryParamsMiddleware,
    RequestIdMiddleware,
    install_request_id_logging,
    StaticCacheMiddleware,
    BodySizeLimitMiddleware,
    CSRFOriginMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.routes import (
    account,
    alerts,
    admin,
    auth,
    bills,
    charts,
    company,
    dashboard,
    director,
    documents,
    help,
    presentation,
    imports,
    manual,
    manual_batch,
    points,
    stores,
    trash,
    types,
)
from app.security import LoginRequired, MustChangePassword, MustSetup2FA
from app.seed import seed
from app.services.retention_service import retention_loop
from app.startup_checks import security_problems
from app.utils.log_safety import install_log_redaction
from app.web import render, templates

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    if get_settings().run_migrations:
        db_migrate.upgrade()
    else:                                  # desenvolvimento/testes rápidos
        database.Base.metadata.create_all(database.engine)
        database.ensure_columns()
    with database.SessionLocal() as db:
        seed(db)
    task = asyncio.create_task(retention_loop())
    try:
        yield
    finally:
        task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    problems = security_problems(settings)
    if problems:
        raise RuntimeError("Configuração insegura — o servidor não inicia em produção sem corrigir:\n - " +
                           "\n - ".join(problems))
    secret = settings.secret_key
    if not secret:  # só chega aqui em DEBUG
        secret = secrets.token_hex(32)
        logging.getLogger(__name__).warning("SECRET_KEY vazio: chave temporária (sessões caem a cada reinício).")
    security.configure(secret)

    install_log_redaction(settings.gemini_api_key)
    install_request_id_logging()
    app = FastAPI(title="Economart · Controle de Energia", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # Ordem: o último adicionado é o mais externo (cabeçalhos envolvem tudo; a sessão fica por dentro).
    app.add_middleware(SessionMiddleware, secret_key=secret, session_cookie="energia_session",
                       https_only=not settings.debug, same_site="strict", max_age=settings.session_max_hours * 3600)
    app.add_middleware(CSRFOriginMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(DropEmptyQueryParamsMiddleware)
    app.add_middleware(RequestIdMiddleware)          # o mais externo: o código vale até para o erro 500
    # Só os estáticos vão comprimidos (CSS/JS/fontes: ~70% menores). Páginas com dados ficam de fora de propósito:
    # gzip em HTML com token CSRF + texto refletido da busca abre o ataque BREACH.
    app.mount("/static", GZipMiddleware(StaticCacheMiddleware(StaticFiles(directory=BASE_DIR / "static")),
                                        minimum_size=1000), name="static")

    for module in (auth, account, alerts, dashboard, director, stores, bills, types, imports, manual, manual_batch, points, charts, documents, help, presentation, company, admin, trash):
        app.include_router(module.router)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return RedirectResponse("/static/img/favicon.png", status_code=301)

    sw_source = (BASE_DIR / "static" / "sw.js").read_text(encoding="utf-8").replace("__V__", templates.env.globals["ASSET_VERSION"])

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        """Service worker na raiz (para valer no site todo). A versão dos arquivos entra no código: deploy novo troca o
        worker e limpa a cópia antiga da tela offline."""
        return Response(sw_source, media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

    @app.get("/offline", include_in_schema=False)
    def offline(request: Request):
        """Tela "sem conexão" (guardada pelo service worker; não tem dado nenhum)."""
        resp = templates.TemplateResponse(request, "offline.html", {})
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.get("/health", include_in_schema=False)
    def health():
        """Saúde do serviço: confirma que o banco responde (o Railway só promove o deploy se isto der 200)."""
        from sqlalchemy import text

        try:
            with database.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            logging.getLogger(__name__).exception("Health check: banco indisponível")
            return PlainTextResponse("banco indisponível", status_code=503)
        return PlainTextResponse("ok")

    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, exc: LoginRequired):
        from urllib.parse import quote

        here = request.url.path + (f"?{request.url.query}" if request.method == "GET" and request.url.query else "")
        return RedirectResponse(f"/login?next={quote(here, safe='/')}", status_code=303)   # volta com a busca/filtros

    @app.exception_handler(MustChangePassword)
    async def _must_change(request: Request, exc: MustChangePassword):
        return RedirectResponse("/account/password", status_code=303)

    @app.exception_handler(MustSetup2FA)
    async def _must_setup_2fa(request: Request, exc: MustSetup2FA):
        return RedirectResponse("/account/2fa", status_code=303)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        logging.getLogger(__name__).exception("Erro não tratado em %s %s", request.method, request.url.path)
        return render(request, "error.html", status_code=500, code=500, request_id=getattr(request.state, "request_id", ""),
                      message="Ocorreu um erro inesperado. Tente novamente; se continuar, avise o administrador.")

    # também os erros do próprio roteador (endereço que não existe, método errado), não só os HTTPException das rotas
    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        generic = {404: "Esta página não existe ou foi removida.", 405: "Esta ação não está disponível por aqui."}
        detail = exc.detail if isinstance(exc.detail, str) else ""
        if detail in ("Not Found", "Method Not Allowed", "") or not detail:
            detail = generic.get(exc.status_code, "Algo deu errado.")
        if "text/html" in request.headers.get("accept", ""):
            return render(request, "error.html", status_code=exc.status_code, code=exc.status_code, message=detail)
        return PlainTextResponse(detail, status_code=exc.status_code)

    return app


app = create_app()
