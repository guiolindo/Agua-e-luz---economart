# Guia para agentes de IA (e para quem chega novo no projeto)

<!--
Convenção agente-agnóstica `AGENTS.md` (Codex, Cursor, Aider, Claude Code e outros).
O `CLAUDE.md` é só um ponteiro para este arquivo, para não duplicar conteúdo.
-->

> **Nome:** Controle de Energia / Economart Energia (repo `Agua-e-luz---economart`).
> Sistema web que recebe a foto ou o PDF da conta de energia, extrai os dados com o Gemini,
> mostra uma tela de conferência e, ao confirmar, atualiza o histórico por loja, os gráficos,
> a folha impressa da loja e os painéis da diretoria. Nasceu para substituir uma planilha de Excel
> ("ENERGIA — GRÁFICO POR LOJA") e virou um sistema de gestão das contas de energia.
> Stack: FastAPI · SQLAlchemy 2 · Alembic · Jinja2 · Chart.js · SQLite (dev) / PostgreSQL (produção, Railway).

## Leia isto antes de tudo

Este arquivo é o mapa. Ele não substitui a documentação: aponta para ela. Leia só o que a tarefa exige.
O índice completo está em [`docs/README.md`](docs/README.md).

## Para fazer X, leia Y

| Tarefa | Leia (nesta ordem) |
|---|---|
| Rodar em dev pela primeira vez | `docs/getting-started.md` |
| Entender o sistema | `docs/architecture.md` → `docs/domain-model.md` |
| Mexer em modelos ou banco | `docs/database.md` → `app/models/` → `app/db_migrate.py` |
| Criar migração | `docs/database.md` (seção de migrações) → `docs/operations.md` |
| Mexer em login, 2FA, sessão, auditoria | `docs/security.md` → `app/security.py`, `app/services/auth_service.py`, `totp_service.py`, `audit_service.py` |
| Mexer em relatório, folha da loja, painel da diretoria | `docs/domain-model.md` (agrupamento) → `app/services/chart_service.py`, `executive_service.py` → `tests/test_report_sheet.py` |
| Mexer em alertas | `app/services/alert_service.py` → `tests/test_alerts.py` |
| Mexer na leitura da conta (Gemini) | `app/services/import_service.py`, `circuit_breaker.py` → `docs/security.md` (rejeição de arquivo que não é conta) |
| Mexer em telas, CSS ou JS | `docs/frontend.md` → `app/static/css/app.css` (tokens em `:root`) |
| Procurar um endpoint | `docs/api-reference.md` |
| Fazer deploy ou resolver incidente | `docs/operations.md` → `docs/faq.md` |
| Adicionar teste | `docs/testing.md` → `tests/conftest.py` |
| Entender por que algo é como é | `DECISIONS.md` |
| Ver o que mudou | `CHANGELOG.md` |

## Nunca faça isto

- **Não apague uma migração do Alembic que já foi aplicada em produção.** Em 2026-10-10 a produção deixou de subir
  (`Can't locate revision identified by '0003'`) porque a revisão 0003 foi removida do repositório depois de aplicada no banco.
  Se uma mudança for abandonada, mantenha a revisão como migração vazia. Ver `DECISIONS.md` §3.
- **Não faça o lançamento manual depender do vencimento.** Despesa manual (gerador, manutenção, LL Energia etc.) vale sempre pelo
  mês de referência escolhido. O campo vencimento é só informativo. Ver `DECISIONS.md` §2.
- **Não mude o resumo da folha da loja sem rodar `tests/test_report_sheet.py`.** Ele confere os totais da planilha original ao centavo.
- **Não misture este sistema com o Notas-despesas.** O Notas-despesas é referência visual e de segurança; os bancos, usuários e chaves são separados.
- **Não anonimize o IP na auditoria.** O IP real é gravado de propósito; só o nome de usuário digitado em tentativas falhas é pseudonimizado.
- **Não coloque segredos no repositório.** `railway.env.example` só tem nomes de variáveis.
- **Não derrube a validação de configuração.** Com `DEBUG=false`, o servidor recusa subir sem `SECRET_KEY` e `DOCUMENT_ENCRYPTION_KEY` fortes.
- **Não use textos genéricos ou condescendentes nas telas.** O sistema é profissional e simplificado; mensagens curtas, específicas e sem tom de assistente.

## Antes de commitar

```bash
ruff check --select F,E9 .        # é o que o CI roda; imports não usados quebram o CI
python -m pytest -q               # 284 testes
```

O CI (`.github/workflows/ci.yml`) roda ruff, pytest e pip-audit.

## Branches e deploy

Desenvolva na branch indicada pela tarefa; não abra pull request sem pedido. O deploy é no Railway; antes de subir,
faça backup do Postgres e leia o log de inicialização (deve terminar em `Application startup complete`).
