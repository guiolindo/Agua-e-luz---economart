"""Executa a retenção manualmente. Uso: python -m scripts.purge_documents"""
from app import database, models  # noqa: F401
from app.services.retention_service import purge_expired_documents

if __name__ == "__main__":
    with database.SessionLocal() as db:
        print(f"{purge_expired_documents(db)} documento(s) removido(s).")
