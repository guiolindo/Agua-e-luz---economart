from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class CompanyNetwork(Base):
    """IP (ou faixa) público de um link de internet da empresa. Cadastrado pelo administrador na tela da rede."""

    __tablename__ = "company_networks"

    id: Mapped[int] = mapped_column(primary_key=True)
    cidr: Mapped[str] = mapped_column(String(64), unique=True)          # "187.32.111.41/32" ou "186.248.0.0/16"
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)  # "Link Algar", "Loja 24"...
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
