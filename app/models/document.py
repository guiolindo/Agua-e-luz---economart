from datetime import datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class Document(TimestampMixin, Base):
    """Arquivo original enviado (foto/PDF). Guardado no banco: o disco do Railway é efêmero."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # None após a retenção
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    @property
    def available(self) -> bool:
        return self.data is not None

    def expires_at(self, retention_days: int) -> datetime:
        return self.created_at + timedelta(days=retention_days)
