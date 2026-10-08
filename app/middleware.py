"""Camadas HTTP de segurança: cabeçalhos/CSP, checagem de origem (CSRF), limite de corpo e de requisições."""
import re
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings
from app.security import client_ip

MUTATIONS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


# ------------------------------------------------------------ cabeçalhos
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
        response = await call_next(request)
        h = response.headers
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "SAMEORIGIN"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        if not get_settings().debug:
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        path = request.url.path
        if "Content-Security-Policy" not in h and not path.startswith("/documents/"):
            # scripts só do próprio site ou com o nonce desta resposta (sem 'unsafe-inline' em script)
            h["Content-Security-Policy"] = (
                f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src 'self'; "
                "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
        if not path.startswith("/static/") and "Cache-Control" not in h:
            h["Cache-Control"] = "no-store"  # dados da empresa: nada fica no cache/bfcache do navegador
        return response


# ------------------------------------------------------------ CSRF (origem)
class CSRFOriginMiddleware(BaseHTTPMiddleware):
    """2ª camada além do token: recusa mutações cujo Origin/Fetch-Metadata indique outro site."""

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() in MUTATIONS:
            if request.headers.get("sec-fetch-site", "") == "cross-site":
                return _deny("Origem não permitida para esta operação.")
            origin = request.headers.get("origin", "")
            if origin and origin != "null":
                host = request.headers.get("host", "").lower()
                allowed = {o.strip().lower() for o in get_settings().csrf_allowed_origins.split(",") if o.strip()}
                if urlparse(origin).netloc.lower() != host and origin.lower() not in allowed:
                    return _deny("Origem não permitida para esta operação.")
            elif origin == "null":
                return _deny("Origem não permitida para esta operação.")
        return await call_next(request)


def _deny(msg: str, status: int = 403, headers: dict | None = None):
    return JSONResponse({"detail": msg}, status_code=status, headers=headers)


# ------------------------------------------------------------ tamanho do corpo
class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Corta requisições gigantes ANTES do parse multipart (evita gastar CPU/memória com flood)."""

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() in MUTATIONS:
            try:
                size = int(request.headers.get("content-length", "0"))
            except ValueError:
                size = 0
            s = get_settings()
            upload = request.method == "POST" and request.url.path == "/import"
            limit = s.max_upload_bytes + 1024 * 1024 if upload else 1024 * 1024
            if size > limit:
                return _deny(f"Requisição excede o limite de {limit // (1024 * 1024)} MB.", 413)
        return await call_next(request)


# ------------------------------------------------------------ limite de requisições (por processo)
@dataclass(frozen=True)
class Policy:
    name: str
    methods: frozenset
    pattern: re.Pattern
    max_requests: int
    window: int


POLICIES = (
    Policy("login", frozenset({"POST"}), re.compile(r"^/login$"), 10, 60),
    Policy("login2fa", frozenset({"POST"}), re.compile(r"^/login/2fa$"), 10, 60),
    Policy("password", frozenset({"POST"}), re.compile(r"^/account/password$"), 10, 600),
    Policy("upload", frozenset({"POST"}), re.compile(r"^/import$"), 20, 60),
    Policy("documents", frozenset({"GET"}), re.compile(r"^/documents/"), 60, 60),
    Policy("api", frozenset({"GET"}), re.compile(r"^/api/"), 240, 60),
    Policy("mutations", MUTATIONS, re.compile(r"^/"), 120, 60),
)
_buckets: dict[str, deque] = defaultdict(deque)


def reset_rate_limits() -> None:
    _buckets.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Janela deslizante em memória: vale por processo (Railway com 1 instância). Para várias instâncias, usar Redis."""

    async def dispatch(self, request: Request, call_next):
        if get_settings().rate_limit_enabled:
            policy = next((p for p in POLICIES if request.method.upper() in p.methods and p.pattern.match(request.url.path)), None)
            if policy:
                now = time.monotonic()
                q = _buckets[f"{policy.name}:{client_ip(request)}"]
                while q and q[0] <= now - policy.window:
                    q.popleft()
                if len(q) >= policy.max_requests:
                    return _deny("Muitas tentativas. Aguarde um pouco e tente novamente.", 429,
                                 {"Retry-After": str(policy.window)})
                q.append(now)
                if len(_buckets) > 5000:  # contém crescimento sob ataque distribuído
                    for k in [k for k, v in _buckets.items() if not v or v[-1] <= now - 600]:
                        _buckets.pop(k, None)
        return await call_next(request)
