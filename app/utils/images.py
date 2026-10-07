"""Prepara a imagem para o modelo: corrige rotação (EXIF) e reduz fotos enormes. O original guardado não é alterado."""
import io
import logging

log = logging.getLogger(__name__)

MAX_SIDE = 3000  # mantém legível o texto miúdo da conta, sem estourar tamanho/latência
BIG_BYTES = 4 * 1024 * 1024


def prepare_for_model(data: bytes, mime: str) -> tuple[bytes, str]:
    if not mime.startswith("image/"):
        return data, mime  # PDF segue como está
    try:
        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(data))
        oriented = ImageOps.exif_transpose(img)
        rotated = oriented is not img and img.getexif().get(0x0112, 1) != 1
        too_big = max(img.size) > MAX_SIDE or len(data) > BIG_BYTES
        if not rotated and not too_big:
            return data, mime
        img = oriented
        if max(img.size) > MAX_SIDE:
            img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=88, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception:  # imagem estranha: melhor enviar o original do que falhar aqui
        log.warning("Não foi possível pré-processar a imagem; enviando original.")
        return data, mime
