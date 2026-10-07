import hashlib

ALLOWED = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
}


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
    safe = "".join(c for c in filename.replace("\\", "/").rsplit("/", 1)[-1] if c.isalnum() or c in "._- ")[:120]
    return safe or f"conta.{ext}", real


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
