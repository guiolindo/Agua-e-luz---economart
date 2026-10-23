"""Site encerrado (fim do projeto): qualquer endereço responde 404 com uma tela verde "404 Not Found", sem logo nem
nada do sistema. A partir de SITE_BLACK_AT, só uma tela preta. Liga com SITE_CLOSED=true (o padrão).

Nada é apagado: banco, documentos e código continuam como estão; o aplicativo só deixa de ser alcançado. Ficam de
fora apenas /health (o Railway precisa dele para publicar) e /sw.js, que passa a ser um service worker que se
desinstala, para não sobrar a tela offline antiga (com logo) guardada no navegador de quem já usou o sistema.
"""
import random
import secrets
from datetime import datetime

from app.config import get_settings
from app.utils.timezone import TZ, local_now


def black_at() -> datetime | None:
    raw = (get_settings().site_black_at or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def is_black() -> bool:
    when = black_at()
    return when is not None and local_now() >= when


def _binary_columns(n: int = 48, length: int = 64) -> tuple[str, str]:
    """Colunas de 0 e 1 caindo. Posição e ritmo vão em classes: a CSP não aceita style="..." no HTML."""
    rnd = random.Random(404)
    css, cols = [], []
    for i in range(n):
        bits = "".join(rnd.choice("01") for _ in range(length))
        dur = rnd.uniform(7, 16)
        css.append(f".c{i}{{left:{i * 100 / n:.3f}%;animation-duration:{dur:.1f}s;"
                   f"animation-delay:-{rnd.uniform(0, dur):.1f}s;opacity:{rnd.uniform(.25, .7):.2f}}}")
        cols.append(f'<i class="c{i}">{bits}</i>')
    return "\n".join(css), "".join(cols)


_COLUMN_CSS, _COLUMNS = _binary_columns()

GREEN = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>404 Not Found</title><style nonce="__NONCE__">
html,body{margin:0;height:100%;background:#010a03;overflow:hidden}
body{font-family:"Courier New",Consolas,monospace;color:#22ff5a}
.rain{position:fixed;inset:0;pointer-events:none}
.rain i{position:absolute;top:0;width:1ch;font-style:normal;font-size:18px;line-height:1.15;word-break:break-all;
  color:#1fd14c;text-shadow:0 0 6px #0f8a2e;animation:fall linear infinite;transform:translateY(-100%)}
@keyframes fall{from{transform:translateY(-100%)}to{transform:translateY(100vh)}}
.shade{position:fixed;inset:0;background:radial-gradient(ellipse at center,rgba(1,10,3,.92) 0,rgba(1,10,3,.75) 38%,rgba(1,10,3,.25) 75%)}
main{position:relative;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;
  text-align:center;padding:0 16px}
h1{margin:0;font-size:clamp(96px,22vw,220px);line-height:1;letter-spacing:.06em;color:#39ff6e;
  text-shadow:0 0 12px #22ff5a,0 0 34px #0fbf3c,0 0 70px #0a7a27}
p{margin:.6em 0 0;font-size:clamp(20px,4.4vw,38px);letter-spacing:.32em;text-transform:uppercase;
  text-shadow:0 0 10px #18c544}
p::after{content:"_";animation:blink 1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
body::after{content:"";position:fixed;inset:0;pointer-events:none;
  background:repeating-linear-gradient(0deg,rgba(0,0,0,.18) 0 1px,transparent 1px 3px)}
""" + _COLUMN_CSS + """
@media (prefers-reduced-motion:reduce){.rain i,p::after{animation:none}.rain i{transform:none}}
</style></head><body><div class="rain" aria-hidden="true">""" + _COLUMNS + """</div><div class="shade"></div>
<main><h1>404</h1><p>Not Found</p></main></body></html>"""

BLACK = """<!doctype html><html><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow">
<style nonce="__NONCE__">html,body{margin:0;height:100%;background:#000}</style></head><body></body></html>"""

SW_UNINSTALL = """self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(
  caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k)))).then(() => self.registration.unregister())));
"""


class SiteClosedMiddleware:
    """O mais externo de todos: responde antes de sessão, banco ou rota. Desligado (SITE_CLOSED=false), não faz nada."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not get_settings().site_closed or scope["path"] == "/health":
            return await self.app(scope, receive, send)
        if scope["path"] == "/sw.js":
            await self._send(send, 200, SW_UNINSTALL.encode(), "text/javascript; charset=utf-8", "default-src 'none'")
            return
        nonce = secrets.token_urlsafe(16)
        page = (BLACK if is_black() else GREEN).replace("__NONCE__", nonce).encode()
        await self._send(send, 404, b"" if scope["method"] == "HEAD" else page, "text/html; charset=utf-8",
                         f"default-src 'none'; style-src 'nonce-{nonce}'; base-uri 'none'; form-action 'none'; "
                         "frame-ancestors 'none'", length=len(page))

    @staticmethod
    async def _send(send, status, body, ctype, csp, length=None):
        headers = [(b"content-type", ctype.encode()), (b"content-length", str(length or len(body)).encode()),
                   (b"cache-control", b"no-store"), (b"content-security-policy", csp.encode()),
                   (b"x-robots-tag", b"noindex, nofollow"), (b"x-content-type-options", b"nosniff"),
                   (b"referrer-policy", b"no-referrer")]
        if ctype.startswith("text/html"):
            # apaga o que o navegador guardou do sistema: cookie de sessão, cache e o service worker antigo
            headers.append((b"clear-site-data", b'"cache", "cookies", "storage"'))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
