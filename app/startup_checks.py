"""Verificação de segredos na subida. Fora do DEBUG o servidor se recusa a iniciar com configuração insegura."""
from app.config import Settings

WEAK_SECRETS = {"changeme", "secret", "trocar", "troque-em-producao", "test-secret"}


def security_problems(s: Settings) -> list[str]:
    if s.debug:
        return []
    problems = []
    if len(s.secret_key) < 32 or s.secret_key.lower() in WEAK_SECRETS:
        problems.append("SECRET_KEY ausente/curta (mínimo 32 caracteres; gere com secrets.token_hex(32))")
    if not s.document_encryption_key.strip():
        problems.append("DOCUMENT_ENCRYPTION_KEY ausente (gere com: python -c \"from cryptography.fernet import Fernet; "
                        "print(Fernet.generate_key().decode())\")")
    else:
        from cryptography.fernet import Fernet

        try:
            for k in s.document_encryption_key.split(","):
                Fernet(k.strip().encode())
        except (ValueError, TypeError):
            problems.append("DOCUMENT_ENCRYPTION_KEY inválida (precisa ser uma chave Fernet)")
    if s.database_url.startswith("sqlite"):
        problems.append("DATABASE_URL aponta para SQLite (em produção use o PostgreSQL; o disco do Railway é efêmero)")
    return problems
