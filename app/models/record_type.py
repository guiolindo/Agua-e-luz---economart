from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin

KIND_BILL = "bill"      # conta com leitura estruturada (ex.: CEMIG) -> tabela energy_bills
KIND_MANUAL = "manual"  # lançamento mensal com valor + campos próprios -> tabela manual_records


class RecordType(TimestampMixin, Base):
    """Tipo de registro (CEMIG, LL Energia, Gerador...). Novos tipos são cadastrados pelo admin."""

    __tablename__ = "record_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default=KIND_MANUAL)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Campos numéricos extras de tipos manuais: [{"key": "horas", "label": "Horas", "unit": "h"}]
    fields: Mapped[list] = mapped_column(JSON, default=list)
    # Nomes alternativos da distribuidora como aparecem na conta (ex.: razão social)
    aliases: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def is_bill(self) -> bool:
        return self.kind == KIND_BILL
