"""Páginas de um PDF como imagem, para a conta original entrar na impressão (o navegador não imprime PDF embutido)."""
import io
import threading

import pypdfium2 as pdfium

MAX_PAGES = 6          # uma conta tem 1–2 páginas; mais que isso é arquivo errado, não vale imprimir
SCALE = 1.6            # ~115 dpi: legível no papel sem gerar imagens pesadas
_lock = threading.Lock()   # o pdfium não é thread-safe e o FastAPI roda rotas síncronas em threads


def page_count(data: bytes) -> int:
    """Quantas páginas serão impressas (0 se o PDF não puder ser lido)."""
    return min(true_page_count(data), MAX_PAGES)


def true_page_count(data: bytes) -> int:
    """Número real de páginas, sem o corte de MAX_PAGES (0 se o PDF não puder ser lido).

    Usado também na validação do upload: contar com o mesmo leitor que vai abrir o arquivo depois evita que um PDF
    com páginas em object streams comprimidos (invisíveis para quem só procura "/Type /Page" nos bytes crus) escape
    do limite de páginas."""
    try:
        with _lock:
            pdf = pdfium.PdfDocument(data)
            try:
                return len(pdf)
            finally:
                pdf.close()
    except Exception:
        return 0


def page_sizes(data: bytes) -> list[tuple[float, float]]:
    """(largura, altura) de cada página impressa, já considerando a rotação da página (vazio se ilegível)."""
    try:
        with _lock:
            pdf = pdfium.PdfDocument(data)
            try:
                return [tuple(pdf[i].get_size()) for i in range(min(len(pdf), MAX_PAGES))]
            finally:
                pdf.close()
    except Exception:
        return []


def image_display_size(data: bytes) -> tuple[int, int] | None:
    """Tamanho com que o navegador MOSTRA a foto (a orientação EXIF de foto de celular troca largura e altura)."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            if im.getexif().get(0x0112) in (5, 6, 7, 8):
                w, h = h, w
            return w, h
    except Exception:
        return None


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
