from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_MODEL = "gemini-3.5-flash-lite"
OBSOLETE_MODELS = {"gemini-2.0-flash-exp", "gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-1.0-pro",
                   "gemini-pro", "gemini-pro-vision"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = DEFAULT_MODEL
    extraction_provider: str = "gemini"  # gemini | mock

    database_url: str = "sqlite:///app.db"
    secret_key: str = ""
    debug: bool = False

    admin_username: str = "admin"
    admin_password: str = ""

    # O envio inline ao Gemini vai em base64 (+33%) e o limite da requisição é ~20 MB: 12 MB brutos deixam folga.
    max_upload_mb: int = 12
    gemini_max_concurrency: int = 2  # a cota gratuita (~15 pedidos/min) estoura com rajadas
    stale_import_minutes: int = 10
    # Foto/PDF original some do banco após este prazo (os dados lidos permanecem). ~6 meses.
    document_retention_days: int = 183
    retention_check_hours: int = 6

    @field_validator("gemini_model")
    @classmethod
    def _migrate_obsolete_model(cls, v: str) -> str:
        # Modelos descontinuados (lista do projeto lancamento-automatico) são trocados pelo padrão atual.
        if v.strip() in OBSOLETE_MODELS:
            import logging

            logging.getLogger(__name__).warning("GEMINI_MODEL=%s foi descontinuado; usando %s.", v, DEFAULT_MODEL)
            return DEFAULT_MODEL
        return v.strip()

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # Railway entrega "postgres://" / "postgresql://"; usamos o driver psycopg (v3).
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
