from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class LoginThrottle(TimestampMixin, Base):
    """Falhas de login com um nome de usuário que NÃO existe.

    Existe para o bloqueio parecer igual com usuário real ou inventado: sem isso, só os nomes reais mostrariam
    "acesso bloqueado" depois de N tentativas e a mensagem revelaria quais usuários existem. A chave é um HMAC do
    nome digitado (o nome bruto não é guardado)."""

    __tablename__ = "login_throttle"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
