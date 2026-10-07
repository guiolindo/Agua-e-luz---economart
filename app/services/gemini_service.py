"""Única integração com o Gemini. Nenhum outro módulo importa o SDK do Google."""
import json
import logging

from app.config import get_settings
from app.schemas.extraction import BillExtraction

log = logging.getLogger(__name__)

PROMPT = """Você é um extrator de dados de contas de energia elétrica brasileiras (principalmente CEMIG).
Analise a imagem/PDF da conta e preencha o JSON conforme o schema.

Regras:
- NUNCA invente valores. Se um campo não estiver visível ou legível, use null.
- Números no formato brasileiro: ponto é separador de milhar e vírgula é decimal
  (ex.: "20.505,00" -> 20505.00; "58.372" kWh -> 58372). Devolva como número JSON.
- Datas no formato YYYY-MM-DD. "reference_month" no formato YYYY-MM (campo "Referente a", ex.: SET/2026 -> 2026-09).
- "consumer_unit_number": o "N.º DA UNIDADE CONSUMIDORA" exatamente como impresso, com pontos e hífen.
- "total_value": o "Valor a pagar (R$)" / "Total a pagar".
- Consumo e demanda do mês corrente: use a primeira linha do "Histórico de Consumo" (mês de referência) e/ou os itens
  faturados. HP = ponta, HFP = fora ponta, HR = horário reservado.
- "line_items": os itens de "Valores Faturados", inclusive descontos (valores negativos).
- "confidence": sua confiança de 0 a 1 em cada campo crítico (unidade consumidora, mês, valor, datas).
  Use valores baixos quando a foto estiver borrada, cortada, inclinada ou com reflexo.
- Se o documento não for uma conta de energia, devolva tudo null."""


class ExtractionError(RuntimeError):
    """Falha de extração com mensagem apresentável ao usuário."""


class GeminiService:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.name = f"gemini:{self.model}"

    def extract(self, data: bytes, mime_type: str) -> BillExtraction:
        if not self.api_key:
            raise ExtractionError("A chave do Gemini (GEMINI_API_KEY) não está configurada no servidor.")
        from google import genai
        from google.genai import types

        try:
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=[types.Part.from_bytes(data=data, mime_type=mime_type), PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=BillExtraction,
                    temperature=0,
                ),
            )
        except Exception as exc:  # erro de rede/quota/modelo: não vaza detalhes técnicos para a tela
            log.exception("Falha ao chamar o Gemini")
            raise ExtractionError("Não foi possível analisar a conta agora. Tente novamente em instantes.") from exc
        return parse_response_text(response.text)


def parse_response_text(text: str | None) -> BillExtraction:
    """Valida o JSON devolvido pela IA contra o schema."""
    if not text:
        raise ExtractionError("A IA não retornou dados para este documento.")
    try:
        return BillExtraction.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ExtractionError("A resposta da IA veio em formato inválido. Tente enviar a foto novamente.") from exc
