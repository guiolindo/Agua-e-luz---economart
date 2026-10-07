from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.document import Document
from app.models.mixins import TimestampMixin

# status: processing -> ready -> confirmed | cancelled ;  processing -> failed
# stage (para o feedback visual): received -> extracting -> matching -> done


class Import(TimestampMixin, Base):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    store_hint_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="processing", index=True)
    stage: Mapped[str] = mapped_column(String(20), default="received")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # resposta da IA, sem alterações
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    matched_unit_id: Mapped[int | None] = mapped_column(ForeignKey("consumer_units.id"), nullable=True)
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("energy_bills.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    document: Mapped[Document] = relationship()
