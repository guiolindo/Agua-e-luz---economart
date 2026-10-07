"""Contrato de extração de uma conta. Também é o response_schema enviado ao Gemini.

Todos os campos são opcionais: o que a IA não conseguir ler vem como null (nunca inventado).
"""
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str | None = Field(None, description="Nome do item como impresso na fatura")
    unit: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    value: float | None = Field(None, description="Valor faturado do item em R$ (negativo para descontos)")


class FieldConfidence(BaseModel):
    consumer_unit_number: float | None = Field(None, ge=0, le=1)
    reference_month: float | None = Field(None, ge=0, le=1)
    total_value: float | None = Field(None, ge=0, le=1)
    dates: float | None = Field(None, ge=0, le=1)


class BillExtraction(BaseModel):
    utility: str | None = Field(None, description="Concessionária, ex.: CEMIG")
    consumer_unit_number: str | None = Field(
        None, description="Número da unidade consumidora exatamente como impresso, ex.: 12.060.073.018-19"
    )
    customer_name: str | None = None
    reference_month: str | None = Field(None, description="Mês de referência no formato YYYY-MM (SET/2026 -> 2026-09)")
    issue_date: str | None = Field(None, description="Data de emissão da nota, YYYY-MM-DD")
    due_date: str | None = Field(None, description="Vencimento, YYYY-MM-DD")
    invoice_number: str | None = Field(None, description="Número da nota fiscal")
    series: str | None = None
    bill_class: str | None = Field(None, description="Classe, ex.: Comercial")
    subclass: str | None = None
    tariff_modality: str | None = Field(None, description="Modalidade tarifária, ex.: TUSD Livre A4 Verde")

    previous_reading_date: str | None = Field(None, description="Leitura anterior, YYYY-MM-DD")
    current_reading_date: str | None = Field(None, description="Leitura atual, YYYY-MM-DD")
    next_reading_date: str | None = Field(None, description="Próxima leitura, YYYY-MM-DD")
    days: int | None = Field(None, description="Número de dias do período de leitura")

    total_value: float | None = Field(None, description="Valor total a pagar em R$ (ex.: 20505.00)")
    consumption_hp_kwh: float | None = Field(None, description="Energia ponta (HP) do mês, kWh")
    consumption_hfp_kwh: float | None = Field(None, description="Energia fora ponta (HFP) do mês, kWh")
    consumption_hr_kwh: float | None = Field(None, description="Energia horário reservado (HR) do mês, kWh")
    demand_hp_kw: float | None = Field(None, description="Demanda ponta (HP) do mês, kW")
    demand_hfp_kw: float | None = Field(None, description="Demanda fora ponta (HFP) do mês, kW")
    contracted_demand_kw: float | None = Field(None, description="Demanda contratada, kW")
    pis_cofins_value: float | None = Field(None, description="Soma de PIS/COFINS em R$ (coluna total, se houver)")
    icms_value: float | None = Field(None, description="ICMS em R$ (0 se constar 0,00)")

    line_items: list[LineItem] = Field(default_factory=list, description="Itens da fatura / valores faturados")
    notes: str | None = Field(None, description="Informações gerais relevantes, resumidas")
    confidence: FieldConfidence | None = Field(None, description="Confiança (0 a 1) nos campos críticos")
