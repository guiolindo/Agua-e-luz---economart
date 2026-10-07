import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import RecordType, User
from app.security import hash_password

log = logging.getLogger(__name__)

DEFAULT_TYPES = [
    dict(code="cemig", name="CEMIG", kind="bill", sort_order=10, fields=[],
         description="Conta de energia da distribuidora (leitura por foto)."),
    dict(code="ll-energia", name="LL Energia", kind="manual", sort_order=20,
         fields=[{"key": "consumo_kwh", "label": "Consumo", "unit": "kWh"}],
         description="Comercializadora de energia (lançamento mensal)."),
    dict(code="gerador", name="Gerador", kind="manual", sort_order=30,
         fields=[{"key": "horas", "label": "Horas de operação", "unit": "h"},
                 {"key": "litros", "label": "Combustível", "unit": "L"}],
         description="Custos do gerador, incluindo compra de combustível."),
    dict(code="manutencao-gerador", name="Manutenção de Gerador", kind="manual", sort_order=40,
         fields=[{"key": "ocorrencias", "label": "Ocorrências", "unit": ""}],
         description="Manutenções do gerador."),
]


def seed(db: Session) -> None:
    for t in DEFAULT_TYPES:
        if db.scalar(select(RecordType).where(RecordType.code == t["code"])) is None:
            db.add(RecordType(**t))
    settings = get_settings()
    if db.scalar(select(User).limit(1)) is None:
        password = settings.admin_password
        if not password and settings.debug:
            password = "admin"
            log.warning("ADMIN_PASSWORD vazio: usando senha 'admin' (apenas DEBUG).")
        if password:
            db.add(User(username=settings.admin_username, password_hash=hash_password(password), role="admin"))
        else:
            log.warning("Nenhum usuário existe e ADMIN_PASSWORD não foi definido: defina-o para criar o admin.")
    db.commit()
