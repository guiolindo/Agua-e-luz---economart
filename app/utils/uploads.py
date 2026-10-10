import hashlib

ALLOWED = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
}


MAX_PDF_PAGES = 10  # uma conta tem 1–2 páginas; PDFs enormes travam/estouram o tempo do modelo
MAX_IMAGE_PIXELS = 40_000_000  # ~6300×6300: bem acima de qualquer foto de celular, barra "bomba de descompressão"
                                # (PNG pequeno em bytes, mas gigante decodificado — ex.: 10000×10000 em poucos KB)


class UploadError(ValueError):
    pass


def sniff_content_type(data: bytes) -> str | None:
    """Confere o conteúdo real (magic bytes) — nunca confiar só em extensão/Content-Type."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def validate_upload(filename: str, data: bytes, max_bytes: int) -> tuple[str, str]:
    """Retorna (nome_seguro, content_type) ou levanta UploadError."""
    if not data:
        raise UploadError("O arquivo está vazio.")
    if len(data) > max_bytes:
        raise UploadError(f"O arquivo excede o limite de {max_bytes // (1024 * 1024)} MB.")
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in ALLOWED:
        raise UploadError("Formato não suportado. Envie JPG, PNG, WEBP ou PDF.")
    real = sniff_content_type(data)
    if real is None or real != ALLOWED[ext]:
        raise UploadError("O conteúdo do arquivo não corresponde ao formato informado.")
    if real == "application/pdf":
        pages = _pdf_page_count(data)
        if pages == 0:
            raise UploadError("Não foi possível abrir este PDF. Confira se o arquivo não está corrompido ou protegido por senha.")
        if pages > MAX_PDF_PAGES:
            raise UploadError(f"O PDF tem {pages} páginas. Envie apenas a(s) página(s) da conta (até {MAX_PDF_PAGES}).")
    else:
        w, h = _image_size(data)
        if w and h and w * h > MAX_IMAGE_PIXELS:
            raise UploadError("A imagem é grande demais para processar. Envie uma foto comum (sem redimensionar artificialmente).")
    safe = "".join(c for c in filename.replace("\\", "/").rsplit("/", 1)[-1] if c.isalnum() or c in "._- ")[:120]
    return safe or f"conta.{ext}", real


def _pdf_page_count(data: bytes) -> int:
    """Conta as páginas com o mesmo leitor usado depois (pypdfium2), não por regex nos bytes crus: um PDF com
    páginas em object streams comprimidos (comum em PDFs gerados por scanner) escondem "/Type /Page" do regex
    e passariam pelo limite sem serem contadas. Devolve 0 se o PDF não abrir (o chamador rejeita: ele também não
    abriria depois, na impressão da conta)."""
    from app.services.pdf_pages import true_page_count

    return true_page_count(data)


def _image_size(data: bytes) -> tuple[int, int] | tuple[None, None]:
    """Dimensões sem decodificar os pixels (leitura do cabeçalho: barata mesmo para um arquivo hostil).

    Uma imagem absurdamente grande faz o próprio Pillow recusar já no Image.open (DecompressionBombError, bem
    acima do nosso MAX_IMAGE_PIXELS): trata isso como "maior que o limite", em vez de engolir a exceção e deixar
    passar sem checar o tamanho."""
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as img:
            return img.size
    except Image.DecompressionBombError:
        return MAX_IMAGE_PIXELS + 1, 1
    except Exception:
        return None, None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
