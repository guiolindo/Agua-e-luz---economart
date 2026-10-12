"""Páginas de um PDF como imagem, para a conta original entrar na impressão (o navegador não imprime PDF embutido)."""
import io
import threading

import pypdfium2 as pdfium
from PIL import Image

MAX_PAGES = 6          # uma conta tem 1–2 páginas; mais que isso é arquivo errado, não vale imprimir
SCALE = 1.6            # ~115 dpi: legível na tela (conferência) sem gerar imagens pesadas
PRINT_SCALE = 2.6      # ~190 dpi: para o papel (impressão para assinatura); 115 dpi esticado em A4 fica borrado
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


def _rotated(image, rotate: bool):
    # Impressão para assinatura: o trabalho inteiro é A4 deitado (uma orientação só, que toda impressora aceita).
    # A página em pé é girada 90° para ocupar a folha deitada: no papel, virando a folha, ela fica em pé, inteira.
    return image.transpose(Image.Transpose.ROTATE_90) if rotate else image


def render_page(data: bytes, number: int, scale: float = SCALE, rotate: bool = False) -> bytes | None:
    """PNG da página `number` (1-based), ou None se não existir/ilegível. `rotate` gira 90° (ver `_rotated`)."""
    if not 1 <= number <= MAX_PAGES:
        return None
    try:
        with _lock:
            pdf = pdfium.PdfDocument(data)
            try:
                if number > len(pdf):
                    return None
                image = pdf[number - 1].render(scale=scale).to_pil().convert("RGB")
            finally:
                pdf.close()
        image = _rotated(image, rotate)
        out = io.BytesIO()
        image.save(out, "PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None


def render_photo(data: bytes, rotate: bool = False, max_side: int = 3000) -> bytes | None:
    """Foto da conta pronta para o papel: aplica a rotação EXIF do celular, limita o tamanho e (opcional) gira 90°."""
    try:
        from PIL import ImageOps

        with Image.open(io.BytesIO(data)) as im:
            image = ImageOps.exif_transpose(im).convert("RGB")
        image.thumbnail((max_side, max_side))
        image = _rotated(image, rotate)
        out = io.BytesIO()
        image.save(out, "JPEG", quality=90)
        return out.getvalue()
    except Exception:
        return None
