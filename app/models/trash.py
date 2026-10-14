from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class TrashItem(Base):
    """Conta ou lançamento excluído: a linha inteira fica guardada aqui e o administrador pode restaurar.

    A foto/PDF original não é apagada enquanto o item está na lixeira (segue só a retenção normal de documentos)."""

    __tablename__ = "trash_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)            # energy_bill | manual_record
    original_id: Mapped[int] = mapped_column(Integer)
    store_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    summary: Mapped[str] = mapped_column(String(300))                    # "L05 · CEMIG · SET/2026 · R$ 1.234,56"
    payload: Mapped[dict] = mapped_column(JSON)                          # todas as colunas da linha excluída
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    restored_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
