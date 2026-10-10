import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import (  # noqa: F401  (models registra as tabelas no metadata)
    database,
    db_migrate,
    models,
    security,
)
from app.config import get_settings
from app.middleware import (
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
    types,
)
from app.security import LoginRequired, MustChangePassword, MustSetup2FA
from app.seed import seed
from app.services.retention_service import retention_loop
from app.startup_checks import security_problems
from app.utils.log_safety import install_log_redaction
from app.web import render

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
    app = FastAPI(title="Economart · Controle de Energia", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # Ordem: o último adicionado é o mais externo (cabeçalhos envolvem tudo; a sessão fica por dentro).
    app.add_middleware(SessionMiddleware, secret_key=secret, session_cookie="energia_session",
                       https_only=not settings.debug, same_site="strict", max_age=settings.session_max_hours * 3600)
    app.add_middleware(CSRFOriginMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    for module in (auth, account, alerts, dashboard, director, stores, bills, types, imports, manual, manual_batch, points, charts, documents, help, presentation, admin):
        app.include_router(module.router)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return RedirectResponse("/static/img/favicon.png", status_code=301)

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
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)

    @app.exception_handler(MustChangePassword)
    async def _must_change(request: Request, exc: MustChangePassword):
        return RedirectResponse("/account/password", status_code=303)

    @app.exception_handler(MustSetup2FA)
    async def _must_setup_2fa(request: Request, exc: MustSetup2FA):
        return RedirectResponse("/account/2fa", status_code=303)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        logging.getLogger(__name__).exception("Erro não tratado em %s %s", request.method, request.url.path)
        return render(request, "error.html", status_code=500, code=500,
                      message="Ocorreu um erro inesperado. Tente novamente; se persistir, avise o administrador.")

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        if "text/html" in request.headers.get("accept", ""):
            return render(request, "error.html", status_code=exc.status_code, code=exc.status_code,
                          message=exc.detail if isinstance(exc.detail, str) else "Algo deu errado.")
        return PlainTextResponse(str(exc.detail), status_code=exc.status_code)

    return app


app = create_app()
