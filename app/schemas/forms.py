"""Parsing/validação dos formulários de conta (revisão da importação e lançamento manual de CEMIG)."""
from collections.abc import Mapping
from datetime import date
from decimal import Decimal

from app.schemas.extraction import BillExtraction
from app.utils.parsing import clean_str, parse_date, parse_decimal, parse_int, parse_reference

DATE_FIELDS = ["issue_date", "due_date", "previous_reading_date", "current_reading_date", "next_reading_date"]
MONEY_FIELDS = ["total_value", "pis_cofins_value", "icms_value"]
QUANT_FIELDS = ["consumption_kwh", "consumption_hp", "consumption_hfp", "consumption_hr", "demand_hp", "demand_hfp", "contracted_demand"]
TEXT_FIELDS = {"invoice_number": 60, "series": 20, "bill_class": 80, "subclass": 120, "tariff_modality": 80,
               "notes": 2000}
FIELD_LABELS = {
    "reference": "Mês de referência", "total_value": "Valor da fatura", "issue_date": "Emissão", "due_date": "Vencimento",
    "invoice_number": "Nº da nota", "series": "Série", "days": "Dias", "previous_reading_date": "Leitura anterior",
    "current_reading_date": "Leitura atual", "next_reading_date": "Próxima leitura",
    "consumption_kwh": "Consumo único (kWh)", "consumption_hp": "Consumo HP (kWh)", "consumption_hfp": "Consumo HFP (kWh)", "consumption_hr": "Consumo HR (kWh)",
    "demand_hp": "Demanda HP (kW)", "demand_hfp": "Demanda HFP (kW)", "contracted_demand": "Demanda contratada (kW)",
    "pis_cofins_value": "PIS/COFINS (R$)", "icms_value": "ICMS (R$)", "bill_class": "Classe", "subclass": "Subclasse",
    "tariff_modality": "Modalidade tarifária", "notes": "Observações",
}


def parse_bill_form(form: Mapping) -> tuple[dict, dict[str, str]]:
    """Devolve (valores tipados, erros por campo). O frontend nunca é confiável: tudo é revalidado aqui."""
    values: dict = {}
    errors: dict[str, str] = {}

    ref_raw = form.get("reference")
    values["reference"] = parse_reference(ref_raw)
    if values["reference"] is None:
        errors["reference"] = "Informe o mês de referência."

    for f in DATE_FIELDS:
        raw = form.get(f)
        values[f] = parse_date(raw)
        if clean_str(raw) and values[f] is None:
            errors[f] = "Data inválida."
    for f in MONEY_FIELDS + QUANT_FIELDS:
        raw = form.get(f)
        values[f] = parse_decimal(raw)
        if clean_str(raw) and values[f] is None:
            errors[f] = "Número inválido."
    raw_days = form.get("days")
    values["days"] = parse_int(raw_days)
    if clean_str(raw_days) and values["days"] is None:
        errors["days"] = "Número inválido."
    for f, size in TEXT_FIELDS.items():
        values[f] = clean_str(form.get(f), size)

    if values["total_value"] is None and "total_value" not in errors:
        errors["total_value"] = "Informe o valor da fatura."
    if values["total_value"] is not None and values["total_value"] < 0:
        errors["total_value"] = "O valor da fatura não pode ser negativo."
    if values["days"] is not None and not 0 < values["days"] <= 370:
        errors["days"] = "Dias fora do intervalo esperado."
    return values, errors


def _money(v) -> str:
    return "" if v is None else f"{Decimal(str(v)):.2f}".replace(".", ",")


def _qty(v) -> str:
    if v is None:
        return ""
    d = Decimal(str(v)).normalize()
    return format(d, "f").replace(".", ",")


def extraction_to_form(e: BillExtraction) -> dict[str, str]:
    """Valores iniciais do formulário de conferência (datas ISO para <input type=date/month>)."""
    ref = parse_reference(e.reference_month)
    iso = lambda s: (parse_date(s).isoformat() if parse_date(s) else "")  # noqa: E731
    return {
        "reference": ref.strftime("%Y-%m") if ref else "",
        "issue_date": iso(e.issue_date), "due_date": iso(e.due_date),
        "previous_reading_date": iso(e.previous_reading_date), "current_reading_date": iso(e.current_reading_date),
        "next_reading_date": iso(e.next_reading_date),
        "invoice_number": e.invoice_number or "", "series": e.series or "",
        "total_value": _money(e.total_value), "days": "" if e.days is None else str(e.days),
        "consumption_kwh": _qty(e.consumption_kwh), "consumption_hp": _qty(e.consumption_hp_kwh), "consumption_hfp": _qty(e.consumption_hfp_kwh),
        "consumption_hr": _qty(e.consumption_hr_kwh),
        "demand_hp": _qty(e.demand_hp_kw), "demand_hfp": _qty(e.demand_hfp_kw),
        "contracted_demand": _qty(e.contracted_demand_kw),
        "pis_cofins_value": _money(e.pis_cofins_value), "icms_value": _money(e.icms_value),
        "bill_class": e.bill_class or "", "subclass": e.subclass or "",
        "tariff_modality": e.tariff_modality or "", "notes": e.notes or "",
    }


def bill_to_form(bill) -> dict[str, str]:
    """Valores de uma conta já salva (para exibir/editar)."""
    out = {"reference": bill.reference.strftime("%Y-%m"), "days": "" if bill.days is None else str(bill.days)}
    for f in DATE_FIELDS:
        v: date | None = getattr(bill, f)
        out[f] = v.isoformat() if v else ""
    for f in MONEY_FIELDS:
        out[f] = _money(getattr(bill, f))
    for f in QUANT_FIELDS:
        out[f] = _qty(getattr(bill, f))
    for f in TEXT_FIELDS:
        out[f] = getattr(bill, f) or ""
    return out


def low_confidence_fields(e: BillExtraction, threshold: float = 0.85) -> set[str]:
    """Campos críticos que a IA não leu ou leu com baixa confiança -> destacados na conferência."""
    flagged: set[str] = set()
    c = e.confidence
    checks = {
        "consumer_unit": (e.consumer_unit_number, c.consumer_unit_number if c else None),
        "reference": (e.reference_month, c.reference_month if c else None),
        "total_value": (e.total_value, c.total_value if c else None),
        "due_date": (e.due_date, c.dates if c else None),
        "issue_date": (e.issue_date, c.dates if c else None),
    }
    for key, (value, conf) in checks.items():
        if value is None or (conf is not None and conf < threshold):
            flagged.add(key)
    return flagged
