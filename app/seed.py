import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import RecordType, User
from app.security import hash_password, validate_password

log = logging.getLogger(__name__)

DEFAULT_TYPES = [
    dict(code="cemig", name="CEMIG", kind="bill", sort_order=10, fields=[],
         aliases=["COMPANHIA ENERGETICA DE MINAS GERAIS", "CEMIG DISTRIBUICAO"],
         description="Conta de energia da CEMIG (Minas Gerais), lida por foto."),
    dict(code="coelba", name="COELBA", kind="bill", sort_order=11, fields=[],
         aliases=["COMPANHIA DE ELETRICIDADE DO ESTADO DA BAHIA"],
         description="Conta de energia da Coelba (Bahia), lida por foto."),
    dict(code="cemig-geracao", name="CEMIG Geração e Transmissão", kind="manual", sort_order=12,
         fields=[{"key": "energia_kwh", "label": "Energia", "unit": "kWh"}],
         description="Compra de energia (CEMIG Geração e Transmissão S.A.), lançamento mensal."),
    dict(code="ll-energia", name="LL Energia", kind="manual", sort_order=20,
         fields=[{"key": "consumo_kwh", "label": "Consumo", "unit": "kWh"}],
         description="LL Energia - Consultoria (lançamento mensal)."),
    dict(code="ccee", name="Câmara de Comercialização de Energia", kind="manual", sort_order=25,
         fields=[{"key": "energia_kwh", "label": "Energia", "unit": "kWh"}],
         description="CCEE: liquidações e encargos do mercado livre (lançamento mensal)."),
    dict(code="combustivel-gerador", name="Compra de combustível para gerador", kind="manual", sort_order=30,
         fields=[{"key": "horas", "label": "Horas de operação", "unit": "h"},
                 {"key": "litros", "label": "Combustível", "unit": "L"}],
         description="Combustível do gerador."),
    dict(code="manutencao-gerador", name="Manutenção de Gerador", kind="manual", sort_order=40,
         fields=[{"key": "ocorrencias", "label": "Ocorrências", "unit": ""}],
         description="Manutenções do gerador."),
]


def seed(db: Session) -> None:
    for t in DEFAULT_TYPES:
        existing = db.scalar(select(RecordType).where(RecordType.code == t["code"]))
        if existing is None:
            db.add(RecordType(**t))
        elif not existing.aliases and t.get("aliases"):
            existing.aliases = t["aliases"]  # bancos criados antes do campo existir
    settings = get_settings()
    if db.scalar(select(User).limit(1)) is None:
        password = settings.admin_password
        if not password and settings.debug:
            password = "admin"
            log.warning("ADMIN_PASSWORD vazio: usando senha 'admin' (apenas DEBUG).")
        if password:
            if not settings.debug:
                err = validate_password(password, settings.admin_username, min_length=12)
                if err:
                    raise RuntimeError(f"ADMIN_PASSWORD recusada: {err} (em produção: mínimo 12 caracteres)")
            db.add(User(username=settings.admin_username, password_hash=hash_password(password), role="admin"))
        else:
            log.warning("Nenhum usuário existe e ADMIN_PASSWORD não foi definido: defina-o para criar o admin.")
    db.commit()
