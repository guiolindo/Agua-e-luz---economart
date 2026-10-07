from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
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
    def can_write(self) -> bool:
        """Importar/lançar. 'viewer' só consulta e imprime."""
        return self.role in ("admin", "operator", "user")

    @property
    def epoch(self) -> int:
        return self.session_epoch or 0
