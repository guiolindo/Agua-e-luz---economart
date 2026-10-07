# Controle de Energia

Sistema web para controlar as contas de energia (CEMIG e outras despesas) por loja. O usuário envia a **foto da conta**,
a IA (Gemini) lê os dados, o sistema descobre sozinho a **loja e a unidade consumidora**, mostra uma tela de
**conferência** e, ao confirmar, atualiza o histórico e os gráficos.

Stack: Python · FastAPI · SQLAlchemy 2 · Jinja2 · Chart.js (embutido em `static/js/vendor`) · SQLite (dev) / PostgreSQL (produção).

## Fluxo principal

```
Importar conta → foto/PDF → Gemini extrai (JSON validado) → unidade consumidora → loja
→ conferência (imagem ao lado, campos editáveis) → confirmar → histórico + gráficos
```

A IA nunca grava sozinha: tudo passa pela tela de conferência. Unidade desconhecida não descarta a conta (cadastrar
ou associar), e duplicidades (mesma unidade + mês, ou mesma nota) exigem decisão: substituir ou salvar como novo.

## Distribuidoras, anotação à mão, retenção e impressão

- **Várias distribuidoras:** CEMIG e COELBA já vêm cadastradas como tipos de conta. A IA lê a distribuidora da própria
  conta; ao cadastrar uma unidade nova pela importação, o tipo é definido por ela. Para outra distribuidora, o admin cria
  um tipo “Conta de distribuidora” em *Tipos de registro* (o nome deve aparecer na conta, ex.: ENERGISA). Contas sem
  separação ponta/fora ponta usam o campo “Consumo único (kWh)”.
- **Anotação à mão (ex.: “CD 300” escrito na folha):** a IA a copia, e o sistema compara com o código/nome/apelidos da loja
  (*Cadastro da loja → Apelidos*). Serve para pré-selecionar a loja de uma unidade nova e para **avisar** quando a loja
  citada à mão difere da loja da unidade encontrada. A identificação oficial continua sendo pelo número da unidade.
- **Retenção:** a foto/PDF fica no PostgreSQL por 6 meses e então é apagada automaticamente (rotina na subida e a cada
  6 h; manual: `python -m scripts.purge_documents`). Os dados lidos, valores e gráficos permanecem; a tela mostra
  “Original expirado”.
- **Impressão:** em *Histórico da loja → Imprimir relatório* (A4 paisagem): resumo mensal, gráfico de barras com linha de
  variação e tabela Valor / Dias / Variação por tipo, no formato do relatório atual.
- **Gemini (lições do projeto lancamento-automatico):** erros traduzidos para português sem expor chave/URL, retentativa
  em 429/5xx, timeout de 120 s, “zero chute” e parsing tolerante do JSON.

## Requisitos

- Python 3.12+ (testado em 3.13)
- Uma chave da API do Gemini (https://aistudio.google.com/apikey) — opcional para desenvolvimento (use o modo mock)

## Instalação e execução local

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                 # Windows: copy .env.example .env
```

Edite o `.env`:

| Variável | Para quê |
|---|---|
| `GEMINI_API_KEY` | Chave do Gemini. **Só no `.env`/variáveis do servidor, nunca no código.** |
| `GEMINI_MODEL` | Padrão `gemini-3.5-flash-lite`. Para trocar (ex.: `gemini-3.5-flash`) basta mudar aqui. |
| `EXTRACTION_PROVIDER` | `gemini` (real) ou `mock` (responde sempre com `tests/fixtures/cemig_set_2026.json`, sem custo). |
| `DATABASE_URL` | `sqlite:///app.db` (dev) ou a URL do PostgreSQL. `postgres://` é convertido automaticamente. |
| `SECRET_KEY` | Obrigatória fora do `DEBUG`. Gere com `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Criam o administrador no primeiro start (se não existir nenhum usuário). Em `DEBUG` sem senha, usa `admin`/`admin`. |
| `MAX_UPLOAD_MB` | Limite do upload (padrão 15). |
| `DOCUMENT_RETENTION_DAYS` | Dias até a foto/PDF original ser apagada do banco (padrão 183 ≈ 6 meses). |

```bash
python run.py                        # http://127.0.0.1:8000
python -m scripts.seed_demo          # (opcional) carrega a loja CD300 com o histórico jan–ago/2026
```

As tabelas são criadas automaticamente na inicialização (`create_all`) e os tipos CEMIG, LL Energia, Gerador e
Manutenção de Gerador são semeados.

## Testes

```bash
pytest
```

Cobrem variação %, parsing de valores/datas brasileiros, matching UC → loja (e sugestões para erro de leitura),
duplicidade, parsing/validação da resposta do Gemini, upload (magic bytes), cálculos dos gráficos e o fluxo HTTP completo
de importação — todos sem chamar a API (o Gemini é substituído por `MockExtractor`).

## Deploy no Railway

1. Crie um projeto no Railway a partir deste repositório do GitHub (build automático via Nixpacks; `railway.json` e `Procfile` já definem o start).
2. Adicione o plugin **PostgreSQL**. No serviço web, em *Variables*, referencie `DATABASE_URL` do Postgres.
3. Defina as variáveis do serviço web (atalho: abra *Variables → Raw Editor* e cole o conteúdo de `railway.env.example`, preenchendo `GEMINI_API_KEY`, `SECRET_KEY` e `ADMIN_PASSWORD`):
   `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.5-flash-lite`, `EXTRACTION_PROVIDER=gemini`, `SECRET_KEY`, `DEBUG=false`,
   `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
4. Gere um domínio público (*Settings → Networking*). O healthcheck é `/health`.

As imagens das contas ficam **no banco** (tabela `documents`), então não é preciso volume e nada se perde em redeploys.
Cookies de sessão são `Secure` quando `DEBUG=false` (o Railway serve HTTPS).

## Estrutura

```
app/
  main.py            fábrica da aplicação, middlewares, handlers
  config/            Settings (.env)
  database.py        engine/sessão (SQLite ↔ PostgreSQL)
  security.py        login por sessão, CSRF, papéis (admin/operador)
  models/            Store, ConsumerUnit, RecordType, EnergyBill, ManualRecord, Document, Import, AuditLog, User
  schemas/           extraction.py (contrato JSON da IA) e forms.py (validação de formulários)
  services/
    gemini_service.py          ÚNICO ponto que usa o SDK do Gemini
    extraction_service.py      escolhe Gemini ou Mock (EXTRACTION_PROVIDER)
    import_service.py          upload → extração em background → salvar/substituir conta
    matching_service.py        UC → unidade → loja (+ sugestões de UC parecida)
    duplicate_service.py       detecção de duplicidade
    calculation_service.py     variação %, intervalo de meses
    chart_service.py           séries dos gráficos, resumo mensal, KPIs da unidade
    dashboard_service.py       contadores e pendências
  repositories/      consultas
  routes/            auth, dashboard, stores/unidades, tipos, importação, manual, API de gráficos, documentos, usuários
  templates/ static/ interface (Jinja2 + CSS próprio + Chart.js local)
scripts/seed_demo.py dados de demonstração
tests/               pytest + fixtures/cemig_set_2026.json
```

## Decisões de modelagem

- **`EnergyBill`** (conta com leitura estruturada: valor, dias, consumo HP/HFP/HR, demanda, impostos, itens) e
  **`ManualRecord`** (valor + campos numéricos definidos pelo próprio tipo) são tabelas separadas; novos tipos
  (Água, Gás, Solar…) são criados pelo admin em *Tipos de registro* sem alterar código.
- A UC é guardada com a formatação original **e** normalizada (só dígitos) — o matching ignora pontos/hífens.
- Cada importação registra arquivo, resposta bruta da IA, provedor/modelo, usuário e data (`imports`); alterações e
  substituições vão para `audit_log` com o antes/depois.

## Limitações conhecidas / próximos passos

- Migrações: `create_all` + adição automática de colunas novas anuláveis (`ensure_columns`). Mudanças maiores exigem Alembic.
- Importação em lote e exportação (Excel/CSV/PDF) não foram implementadas; a arquitetura (`Import` + `run_import`) já comporta.
- Sem limitação de tentativas de login e sem recuperação de senha (o admin cria/desativa usuários em *Usuários*).
- A leitura por IA nunca foi validada aqui com a API real do Gemini (sem chave neste ambiente): os testes usam o mock.
  Antes de usar em produção, importe algumas contas reais e confira a tela de revisão.
