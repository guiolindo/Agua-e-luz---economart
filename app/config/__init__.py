from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    extraction_provider: str = "gemini"  # gemini | mock

    database_url: str = "sqlite:///app.db"
    secret_key: str = ""
    debug: bool = False

    admin_username: str = "admin"
    admin_password: str = ""

    max_upload_mb: int = 15
    # Foto/PDF original some do banco após este prazo (os dados lidos permanecem). ~6 meses.
    document_retention_days: int = 183
    retention_check_hours: int = 6

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
