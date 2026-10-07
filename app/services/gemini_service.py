"""Única integração com o Gemini. Nenhum outro módulo importa o SDK do Google.

Práticas herdadas do projeto "lancamento-automatico": erros traduzidos para mensagens amigáveis em português
(sem vazar URL/chave/stack para a tela), retentativa curta em 429/5xx, timeout explícito, catálogo de lojas no
prompt, "zero chute" e parsing tolerante do JSON.
"""
import json
import logging
import re
import time

from app.config import get_settings
from app.schemas.extraction import BillExtraction

log = logging.getLogger(__name__)

TIMEOUT_MS = 120_000
RETRY_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3

PROMPT = """Você é um extrator estruturado de dados de contas de energia elétrica brasileiras
(CEMIG em Minas Gerais, Coelba na Bahia e outras distribuidoras). Analise a imagem/PDF e preencha o JSON do schema.

## Regras gerais
- ZERO CHUTE: se um campo não estiver visível ou legível, devolva null. Nunca invente nem complete valores.
- Números no formato brasileiro: ponto é milhar e vírgula é decimal ("20.505,00" -> 20505.00; "58.372" kWh -> 58372).
  Devolva sempre número JSON, sem "R$" nem separador de milhar.
- Datas em YYYY-MM-DD. "reference_month" em YYYY-MM (campo "Referente a"/"Mês de referência"; SET/2026 -> 2026-09).
- "utility": nome da distribuidora emissora (ex.: "CEMIG", "COELBA").
- "consumer_unit_number": o número da unidade consumidora / instalação / código do cliente exatamente como impresso
  (CEMIG: "N.º DA UNIDADE CONSUMIDORA"; Coelba: "Código da instalação"/"Conta contrato"). Mantenha pontos e hífens.
- "total_value": o "Valor a pagar"/"Total a pagar" da fatura.
- Consumo: se a conta separa ponta (HP) e fora ponta (HFP) (e HR), preencha consumption_hp_kwh / consumption_hfp_kwh /
  consumption_hr_kwh e demand_*_kw com os valores do MÊS de referência (primeira linha do histórico de consumo e/ou os
  itens faturados). Se a conta tem um consumo único (tarifa convencional), preencha só "consumption_kwh".
- "line_items": os itens faturados, inclusive descontos (valores negativos).
- "confidence": sua confiança (0 a 1) em unidade consumidora, mês, valor e datas. Use valores baixos para foto
  borrada, cortada, inclinada ou com reflexo.

## Anotações à mão
- Se houver texto escrito À MÃO na folha (caneta/marcador, ex.: "CD 300", "SAJ"), copie-o em "handwritten_note".
  Sem texto manuscrito legível: null.
- Marcações como √, X, riscos e destaques de marca-texto NÃO são dados e não mudam nenhum valor: ignore-os.
- Nunca use a anotação à mão para preencher outros campos.
{catalogo}
Se o documento não for uma conta de energia, devolva todos os campos null."""


class ExtractionError(RuntimeError):
    """Falha de extração com mensagem apresentável ao usuário (nunca contém chave, URL ou stack)."""


def message_for_code(code: int | None) -> str:
    if code == 400:
        return "O Gemini rejeitou o arquivo (formato inválido ou muito grande). Verifique a foto/PDF e tente de novo."
    if code in (401, 403):
        return "A chave da API do Gemini é inválida ou foi revogada. Peça ao administrador para atualizar a GEMINI_API_KEY."
    if code == 404:
        return "O modelo do Gemini configurado (GEMINI_MODEL) não foi encontrado. Peça ao administrador para conferir o nome."
    if code == 429:
        return "Limite de uso do Gemini atingido. Aguarde cerca de 1 minuto e tente novamente."
    if code is not None and code >= 500:
        return "O serviço do Google está indisponível no momento. Tente novamente em instantes."
    return "Não foi possível analisar a conta agora. Tente novamente em instantes."


def build_prompt(catalog: str | None) -> str:
    block = ""
    if catalog:
        block = (
            "\n## Catálogo de lojas (apenas para normalizar a anotação à mão)\n"
            "Se \"handwritten_note\" corresponder a uma loja do catálogo (por código, nome ou apelido, ignorando caixa, "
            "espaços e hífens: \"CD 300\" = \"CD300\"), devolva o CÓDIGO canônico da loja. Se não houver correspondência "
            "clara, devolva o texto como está escrito. O catálogo NÃO serve para descobrir a unidade consumidora.\n"
            f"{catalog}\n"
        )
    return PROMPT.format(catalogo=block)


class GeminiService:
    def __init__(self, api_key: str | None = None, model: str | None = None, sleep=time.sleep):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.name = f"gemini:{self.model}"
        self._sleep = sleep

    def extract(self, data: bytes, mime_type: str, catalog: str | None = None) -> BillExtraction:
        if not self.api_key:
            raise ExtractionError("A chave do Gemini (GEMINI_API_KEY) não está configurada no servidor.")
        from google import genai
        from google.genai import errors, types

        client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        contents = [types.Part.from_bytes(data=data, mime_type=mime_type), build_prompt(catalog)]
        config = types.GenerateContentConfig(response_mime_type="application/json", response_schema=BillExtraction,
                                             temperature=0)
        last: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = client.models.generate_content(model=self.model, contents=contents, config=config)
                return parse_response_text(response.text)
            except ExtractionError:
                raise
            except errors.APIError as exc:
                last = exc
                code = getattr(exc, "code", None)
                log.warning("Gemini HTTP %s (tentativa %d/%d)", code, attempt, MAX_ATTEMPTS)
                if code in RETRY_CODES and attempt < MAX_ATTEMPTS:
                    self._sleep(2 ** attempt)
                    continue
                raise ExtractionError(message_for_code(code)) from exc
            except Exception as exc:  # rede, timeout, SSL... nunca expor str(exc): pode conter URL
                last = exc
                log.exception("Falha ao chamar o Gemini")
                if attempt < MAX_ATTEMPTS and _is_transient(exc):
                    self._sleep(2 ** attempt)
                    continue
                raise ExtractionError(message_for_exception(exc)) from exc
        raise ExtractionError(message_for_code(None)) from last


def _is_transient(exc: Exception) -> bool:
    name = type(exc).__name__
    return any(k in name for k in ("Timeout", "Connect", "Remote"))


def message_for_exception(exc: Exception) -> str:
    name = type(exc).__name__
    if "SSL" in name or "Certificate" in name:
        return ("Não foi possível verificar o certificado HTTPS do Google. Se a rede usa proxy/antivírus, peça ao TI "
                "para liberar generativelanguage.googleapis.com.")
    if "Timeout" in name:
        return "O Gemini demorou demais para responder. Tente novamente ou envie uma imagem menor."
    if "Connect" in name:
        return "Sem conexão com o Google no momento. Tente novamente em instantes."
    return message_for_code(None)


def parse_response_text(text: str | None) -> BillExtraction:
    """Valida o JSON devolvido pela IA. Tolera texto/markdown ao redor do objeto JSON."""
    if not text:
        raise ExtractionError("A IA não retornou dados para este documento.")
    candidates = [text]
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m and m.group(0) != text:
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            return BillExtraction.model_validate(json.loads(cand))
        except (json.JSONDecodeError, ValueError):
            continue
    raise ExtractionError("A resposta da IA veio em formato inválido. Tente enviar a foto novamente.")
