from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="operator")  # admin | operator (funcionário) | director | viewer ("user" = legado)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    failed_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    temp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # validade da senha provisória
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Incrementa em logout/troca de senha/desativação: sessões com época antiga deixam de valer.
    session_epoch: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    # 2FA (TOTP, Google Authenticator) — só administradores. Segredo cifrado com a chave dos documentos quando existe.
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    totp_last_step: Mapped[int | None] = mapped_column(Integer, nullable=True)   # anti-replay: janela de 30 s já usada
    totp_recovery: Mapped[list | None] = mapped_column(JSON, nullable=True)      # hashes SHA-256 dos códigos de recuperação

    @property
    def has_2fa(self) -> bool:
        return bool(self.totp_enabled and self.totp_secret)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_director(self) -> bool:
        return self.role == "director"

    @property
    def can_see_executive(self) -> bool:
        return self.role in ("director", "admin")

    @property
    def gets_due_alerts(self) -> bool:
        """Os avisos de vencimento são do funcionário (responsável pela gestão de energia)."""
        return self.role in ("operator", "user")

    @property
    def can_write(self) -> bool:
        """Importar/lançar. 'viewer' só consulta e imprime."""
        return self.role in ("admin", "operator", "user")

    @property
    def epoch(self) -> int:
        return self.session_epoch or 0
