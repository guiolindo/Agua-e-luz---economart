"""Seleciona o provedor de extração (Gemini real ou mock de fixture)."""
import json
from pathlib import Path
from typing import Protocol

from app.config import get_settings
from app.schemas.extraction import BillExtraction
from app.services.gemini_service import GeminiService

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "cemig_set_2026.json"


class Extractor(Protocol):
    name: str

    def extract(self, data: bytes, mime_type: str) -> BillExtraction: ...


class MockExtractor:
    """Devolve sempre a mesma resposta (JSON de fixture). Para desenvolvimento e testes, sem custo de API."""

    def __init__(self, payload: dict | None = None, path: Path = FIXTURE):
        self._payload = payload
        self._path = path
        self.name = "mock"

    def extract(self, data: bytes, mime_type: str) -> BillExtraction:
        payload = self._payload if self._payload is not None else json.loads(self._path.read_text(encoding="utf-8"))
        return BillExtraction.model_validate(payload)


def get_extractor() -> Extractor:
    if get_settings().extraction_provider == "mock":
        return MockExtractor()
    return GeminiService()
