import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import database, models  # noqa: F401  (registra os modelos no metadata)
from app.config import get_settings
from app.routes import admin, auth, charts, dashboard, documents, imports, manual, stores, types
from app.security import LoginRequired
from app.seed import seed
from app.services.retention_service import retention_loop
from app.web import render

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    secret = settings.secret_key
    if not secret:
        if not settings.debug:
            raise RuntimeError("SECRET_KEY é obrigatório fora do modo DEBUG.")
        secret = secrets.token_hex(32)
        logging.getLogger(__name__).warning("SECRET_KEY vazio: chave temporária (sessões caem a cada reinício).")

    app = FastAPI(title="Controle de Energia", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=secret, https_only=not settings.debug, same_site="lax",
                       max_age=60 * 60 * 12)
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    for module in (auth, dashboard, stores, types, imports, manual, charts, documents, admin):
        app.include_router(module.router)

    @app.get("/health", include_in_schema=False)
    def health():
        return PlainTextResponse("ok")

    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, exc: LoginRequired):
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        if "text/html" in request.headers.get("accept", ""):
            return render(request, "error.html", status_code=exc.status_code, code=exc.status_code,
                          message=exc.detail if isinstance(exc.detail, str) else "Algo deu errado.")
        return PlainTextResponse(str(exc.detail), status_code=exc.status_code)

    return app


app = create_app()
