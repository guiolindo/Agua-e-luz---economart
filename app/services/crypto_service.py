"""Criptografia em repouso dos documentos (Fernet/AES-128-CBC+HMAC). Protege contra vazamento de dump do banco.

DOCUMENT_ENCRYPTION_KEY aceita várias chaves separadas por vírgula (MultiFernet): a primeira cifra, todas decifram —
é a rotação de chave sem perder arquivos antigos. Sem chave (só em DEBUG) os bytes ficam sem cifra.
"""
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import get_settings


class CryptoError(RuntimeError):
    pass


def _fernet() -> MultiFernet | None:
    raw = get_settings().document_encryption_key.strip()
    if not raw:
        return None
    try:
        return MultiFernet([Fernet(k.strip().encode()) for k in raw.split(",") if k.strip()])
    except (ValueError, TypeError) as exc:
        raise CryptoError("DOCUMENT_ENCRYPTION_KEY inválida (use Fernet.generate_key()).") from exc


def generate_key() -> str:
    return Fernet.generate_key().decode()


def encryption_enabled() -> bool:
    return bool(get_settings().document_encryption_key.strip())


def encrypt(data: bytes) -> tuple[bytes, bool]:
    f = _fernet()
    return (f.encrypt(data), True) if f else (data, False)


def decrypt(data: bytes, encrypted: bool | None) -> bytes:
    if not encrypted:
        return data  # documento gravado antes da chave existir
    f = _fernet()
    if f is None:
        raise CryptoError("Documento cifrado, mas DOCUMENT_ENCRYPTION_KEY não está configurada.")
    try:
        return f.decrypt(data)
    except InvalidToken as exc:
        raise CryptoError("Não foi possível decifrar o documento (chave diferente da usada na gravação).") from exc
