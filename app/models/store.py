from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin
from app.models.record_type import RecordType


class Store(TimestampMixin, Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    region: Mapped[str | None] = mapped_column(String(20), nullable=True)  # UF/região, p.ex. MG, BA (comparação na diretoria)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Apelidos usados em anotações à mão/relatórios (ex.: "CD 300", "CD Rib Neves")
    aliases: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    units: Mapped[list["ConsumerUnit"]] = relationship(
        back_populates="store", order_by="ConsumerUnit.number", cascade="all, delete-orphan"
    )

    @property
    def label(self) -> str:
        return f"{self.code} — {self.name}" if self.name else self.code


class ConsumerUnit(TimestampMixin, Base):
    __tablename__ = "consumer_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    record_type_id: Mapped[int | None] = mapped_column(ForeignKey("record_types.id"), nullable=True)
    number: Mapped[str] = mapped_column(String(40))
    # Somente dígitos: é a chave de busca do matching ("12.060.073.018-19" == "1206007301819").
    number_normalized: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    internal_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    store: Mapped[Store] = relationship(back_populates="units")
    record_type: Mapped[RecordType | None] = relationship()

    @property
    def label(self) -> str:
        return f"{self.number} — {self.description}" if self.description else self.number
