# Créditos

## Autor

**Guilherme Júnio** — requisitos, validação com os dados reais, testes de campo e decisões de produto.
O código foi desenvolvido com apoio do Claude Code (Anthropic).

## Origem do projeto

O sistema nasceu para substituir a planilha de Excel "ENERGIA — GRÁFICO POR LOJA", montada à mão a partir
dos dados lançados no sistema da empresa. A folha impressa por loja mantém todas as informações dessa planilha
(os totais batem ao centavo; ver `tests/test_report_sheet.py`).

## Bibliotecas de código aberto usadas em execução

| Biblioteca | Uso | Licença |
|---|---|---|
| [FastAPI](https://fastapi.tiangolo.com/) | framework web | MIT |
| [Uvicorn](https://www.uvicorn.org/) | servidor ASGI | BSD-3 |
| [SQLAlchemy](https://www.sqlalchemy.org/) | ORM | MIT |
| [Alembic](https://alembic.sqlalchemy.org/) | migrações do banco | MIT |
| [Jinja2](https://jinja.palletsprojects.com/) | templates | BSD-3 |
| [Pydantic Settings](https://docs.pydantic.dev/) | configuração por variáveis de ambiente | MIT |
| [psycopg](https://www.psycopg.org/) | driver PostgreSQL | LGPL-3.0 |
| [google-genai](https://github.com/googleapis/python-genai) | cliente do Gemini (leitura das contas) | Apache-2.0 |
| [Pillow](https://python-pillow.org/) | imagens | HPND |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | renderização de PDF | Apache-2.0 / BSD-3 |
| [cryptography](https://cryptography.io/) | criptografia dos documentos (Fernet) | Apache-2.0 / BSD-3 |
| [itsdangerous](https://itsdangerous.palletsprojects.com/) | assinatura de sessão | BSD-3 |
| [segno](https://github.com/heuer/segno) | QR code do 2FA | BSD-3 |
| [python-multipart](https://github.com/Kludex/python-multipart) | upload de arquivos | Apache-2.0 |
| [tzdata](https://github.com/python/tzdata) | fuso horário (Brasília) | Apache-2.0 |
| [Chart.js](https://www.chartjs.org/) | gráficos (embutido em `app/static/js/vendor`) | MIT |

Ferramentas de desenvolvimento: pytest, httpx, ruff, pip-audit, Playwright (conferência visual).
