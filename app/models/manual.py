from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin
from app.models.record_type import RecordType
from app.models.store import ConsumerUnit, Store


class ManualRecord(TimestampMixin, Base):
    """Lançamento mensal manual (LL Energia, Gerador, Manutenção...). Campos extras seguem RecordType.fields."""

    __tablename__ = "manual_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("consumer_units.id"), nullable=True)
    record_type_id: Mapped[int] = mapped_column(ForeignKey("record_types.id"), index=True)
    reference: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # opcional: agrupar por mês de vencimento
    accounting_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # data de contabilização (despesas sem vencimento)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    store: Mapped[Store] = relationship()
    unit: Mapped[ConsumerUnit | None] = relationship()
    record_type: Mapped[RecordType] = relationship()

    @property
    def group_date(self) -> date | None:
        """Data que posiciona o lançamento na tabela 'por vencimento': contabilização (quando foi lançada no sistema), senão vencimento, senão (None) a referência."""
        return self.accounting_date or self.due_date
