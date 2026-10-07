from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin
from app.models.store import ConsumerUnit


class EnergyBill(TimestampMixin, Base):
    """Conta de energia de uma unidade consumidora em um mês de referência."""

    __tablename__ = "energy_bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("consumer_units.id"), index=True)
    record_type_id: Mapped[int] = mapped_column(ForeignKey("record_types.id"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="import")  # import | manual

    reference: Mapped[date] = mapped_column(Date, index=True)  # sempre dia 1 do mês
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    series: Mapped[str | None] = mapped_column(String(20), nullable=True)
    total_value: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_reading_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_reading_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_reading_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    consumption_hp: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    consumption_hfp: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    consumption_hr: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    demand_hp: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    demand_hfp: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    contracted_demand: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)

    pis_cofins_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    icms_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    bill_class: Mapped[str | None] = mapped_column(String(80), nullable=True)
    subclass: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tariff_modality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    line_items: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    unit: Mapped[ConsumerUnit] = relationship()

    @property
    def consumption_total(self) -> Decimal | None:
        parts = [v for v in (self.consumption_hp, self.consumption_hfp, self.consumption_hr) if v is not None]
        return sum(parts, Decimal("0")) if parts else None
