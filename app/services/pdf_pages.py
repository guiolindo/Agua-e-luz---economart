"""Páginas de um PDF como imagem, para a conta original entrar na impressão (o navegador não imprime PDF embutido)."""
import io
import threading

import pypdfium2 as pdfium

MAX_PAGES = 6          # uma conta tem 1–2 páginas; mais que isso é arquivo errado, não vale imprimir
SCALE = 1.6            # ~115 dpi: legível no papel sem gerar imagens pesadas
_lock = threading.Lock()   # o pdfium não é thread-safe e o FastAPI roda rotas síncronas em threads


def page_count(data: bytes) -> int:
    """Quantas páginas serão impressas (0 se o PDF não puder ser lido)."""
    try:
        with _lock:
            pdf = pdfium.PdfDocument(data)
            try:
                return min(len(pdf), MAX_PAGES)
            finally:
                pdf.close()
    except Exception:
        return 0


def render_page(data: bytes, number: int) -> bytes | None:
    """PNG da página `number` (1-based), ou None se não existir/ilegível."""
    if not 1 <= number <= MAX_PAGES:
        return None
    try:
        with _lock:
            pdf = pdfium.PdfDocument(data)
            try:
                if number > len(pdf):
                    return None
                image = pdf[number - 1].render(scale=SCALE).to_pil().convert("RGB")
            finally:
                pdf.close()
        out = io.BytesIO()
        image.save(out, "PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None
