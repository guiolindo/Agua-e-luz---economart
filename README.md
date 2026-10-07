# Controle de Energia

Sistema web para controlar as contas de energia (CEMIG e outras despesas) por loja. O usuário envia a **foto da conta**,
a IA (Gemini) lê os dados, o sistema descobre sozinho a **loja e a unidade consumidora**, mostra uma tela de
**conferência** e, ao confirmar, atualiza o histórico e os gráficos.

Stack: Python · FastAPI · SQLAlchemy 2 · Jinja2 · Chart.js (embutido em `static/js/vendor`) · SQLite (dev) / PostgreSQL (produção).

> **Tutorial passo a passo (Railway + uso diário por perfil):** [`TUTORIAL.md`](TUTORIAL.md) · [PDF](docs/Tutorial_Controle_de_Energia.pdf).

> **Segurança:** veja [`SECURITY.md`](SECURITY.md). Em produção (`DEBUG=false`) o servidor só inicia com `SECRET_KEY`, `DOCUMENT_ENCRYPTION_KEY` e PostgreSQL configurados.

## Fluxo principal

```
Importar conta → foto/PDF → Gemini extrai (JSON validado) → unidade consumidora → loja
→ conferência (imagem ao lado, campos editáveis) → confirmar → histórico + gráficos
```

Reenviar o **mesmo arquivo** (mesmo hash) de uma conta já salva é recusado antes de chamar o Gemini. PDFs (a maioria dos casos) vão ao Gemini intactos; fotos são pré-processadas (rotação/tamanho).

A IA nunca grava sozinha: tudo passa pela tela de conferência. Unidade desconhecida não descarta a conta (cadastrar
ou associar), e duplicidades (mesma unidade + mês, ou mesma nota) exigem decisão: substituir ou salvar como novo.

## Perfis de usuário e painel da diretoria

| Perfil | O que faz |
|---|---|
| **Administrador** | Cria os usuários (senha provisória exibida uma vez) e os cadastros (lojas, unidades, tipos); vê tudo, inclusive a diretoria e a auditoria. |
| **Funcionário** | Envia as fotos/PDF das contas, confere, preenche lançamentos manuais, imprime. Não vê o painel da diretoria. |
| **Diretoria** | Só consulta. Ao entrar cai no **Painel da diretoria** (`/diretoria`) e pode abrir lojas e imprimir; não importa nem edita nada. |
| **Consulta** | Só visualiza e imprime. |

O **painel da diretoria** compara as lojas: KPIs (total, último mês, média, custo médio R$/kWh, maior gasto/alta/queda, pendências),
gasto da empresa por mês e fornecedor, ranking de lojas, variação do último mês por loja, composição por fornecedor, evolução
(com seleção de lojas), custo por kWh, uso da demanda contratada, **comparação de duas lojas** (com diferença em R$ e %),
mapa de calor loja × mês e tabela comparativa. Filtros: período, mês de referência/vencimento, **região** (campo “Região/UF” da loja) e
fornecedores. Para não enganar: um mês em que poucas lojas já lançaram é marcado com `*` e fica fora das variações (os indicadores usam o
último mês completo), e “vs. período anterior” compara a **média mensal** só das lojas com histórico. `python -m scripts.seed_demo_company`
cria lojas **fictícias** para visualizar o painel.

## Vencimentos, novo ponto de energia e usabilidade

- **+ Novo ponto de energia** (canto superior direito, em qualquer tela; admin e funcionário): loja, nº da unidade consumidora,
  distribuidora e **data de vencimento**. O ponto passa a vencer todo mês nesse dia (dia 31 em mês curto cai no último dia).
  Contas importadas ou lançadas também ensinam o dia de vencimento ao ponto.
- **Aviso de vencimento:** ao entrar no sistema, aparece um aviso do lado — “Vence hoje” (e “Venceu há N dias”, por até 15 dias) —
  que **some sozinho em 15 segundos** (passar o mouse ou focar com o teclado pausa; aparece uma vez por login por dia). O **sino**
  guarda a lista (inclui “vence amanhã/em N dias”); **Já paguei** dá baixa daquele vencimento. “Hoje” é o dia do Brasil
  (America/Sao_Paulo), não o do servidor. Diretoria e consulta veem os avisos, mas não dão baixa.
- **Usabilidade/acessibilidade:** link “Ir para o conteúdo”, navegação por teclado com foco visível, rótulos em todos os campos,
  mensagens de erro/sucesso anunciadas a leitores de tela (sucessos somem sozinhos), botões que mostram “Salvando…” e não permitem
  duplo clique, busca nas listas, estados vazios com orientação, página **Ajuda** por perfil e respeito a `prefers-reduced-motion`.
  Auditoria automática (axe-core, WCAG 2.1 A/AA + boas práticas) em 18 telas, no desktop e no celular: 0 violações. Isso não substitui
  teste com usuários nem leitor de tela real.

## Distribuidoras, anotação à mão, retenção e impressão

- **Várias distribuidoras:** CEMIG e COELBA (testada com a conta real “Neoenergia Coelba” de Feira de Santana) já vêm cadastradas como tipos de conta. A IA lê a distribuidora da própria
  conta; ao cadastrar uma unidade nova pela importação, o tipo é definido por ela. Para outra distribuidora, o admin cria
  um tipo “Conta de distribuidora” em *Tipos de registro* (o nome deve aparecer na conta, ex.: ENERGISA). Contas sem
  separação ponta/fora ponta usam o campo “Consumo único (kWh)”.
- **Anotação à mão (ex.: “CD 300” escrito na folha):** a IA a copia, e o sistema compara com o código/nome/apelidos da loja
  (*Cadastro da loja → Apelidos*). Serve para pré-selecionar a loja de uma unidade nova e para **avisar** quando a loja
  citada à mão difere da loja da unidade encontrada. A identificação oficial continua sendo pelo número da unidade.
- **Retenção:** a foto/PDF fica no PostgreSQL por 6 meses e então é apagada automaticamente (rotina na subida e a cada
  6 h; manual: `python -m scripts.purge_documents`). Os dados lidos, valores e gráficos permanecem; a tela mostra
  “Original expirado”.
- **Fornecedores da planilha atual:** já vêm cadastrados CEMIG (distribuição), COELBA, CEMIG Geração e Transmissão, LL Energia,
  Câmara de Comercialização de Energia (CCEE), Compra de combustível para gerador e Manutenção de Gerador. O relatório e o
  resumo mensal podem **agrupar por mês de referência (competência) ou por mês de vencimento** — a planilha impressa usa o
  vencimento (a conta de SET/2026, que vence em outubro, cai na coluna out/2026). Lançamentos manuais aceitam “Vencimento”
  opcional; sem ele, entram no mês de referência. O relatório também filtra por fornecedor. `python -m scripts.seed_demo`
  reproduz a folha do CD300 (o teste confere o Total Geral ao centavo).
- **Folha de impressão:** é a mesma para qualquer fornecedor (CEMIG, Coelba, LL Energia…). Traz indicadores resumidos, destaque do último mês com dados, consumo e demanda quando há leitura, e rodapé.
- **Folha de impressão (uma página A4 paisagem)**, no formato da planilha atual: cabeçalho da loja, *Resumo mensal* de todos os
  fornecedores com Total Geral, o *Imóvel/fornecedor* escolhido com faixa de informações da última conta, gráfico de barras com
  linha de variação e a tabela Valor da fatura / Dias / Variação. Em *Histórico da loja → Imprimir relatório*; dá para escolher
  o fornecedor e agrupar por referência ou vencimento (“um por folha” imprime uma folha para cada fornecedor). O conteúdo é
  reduzido automaticamente só o necessário para caber em uma página.
- **Imprimir uma conta com gráficos:** em *Unidade → Contas → Imprimir* (ou `/bills/<id>/print`). A ficha (uma página A4) traz os dados
  da conta, o comparativo com o mês anterior, os itens faturados e três gráficos dos últimos 12 meses (valor com linha de
  variação, consumo HP/HFP e demanda com a contratada), com o mês escolhido em destaque. Na própria tela dá para trocar
  de conta/mês e marcar “Incluir foto/PDF original” (se ainda não expirou).
- **Impressão:** em *Histórico da loja → Imprimir relatório* (A4 paisagem): resumo mensal, gráfico de barras com linha de
  variação e tabela Valor / Dias / Variação por tipo, no formato do relatório atual.
- **Limites e travamentos do Gemini (também do lancamento-automatico):** fotos grandes são reduzidas (lado maior ≤ 3000 px)
  e giradas conforme o EXIF antes do envio (o original guardado não muda); PDFs com mais de 10 páginas são recusados;
  no máximo 2 análises simultâneas (cota gratuita ~15/min), com retentativa em 429/5xx; importação “processando” há
  mais de 10 min vira falha com botão “Tentar novamente” (cobre reinício do servidor no meio da análise); chaves são
  redigidas de qualquer log; modelos descontinuados (2.0-flash-exp, 2.5-flash, 2.5-flash-lite, 1.0-pro…) em
  `GEMINI_MODEL` são trocados automaticamente por `gemini-3.5-flash-lite`.
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
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Criam o administrador no primeiro start (se não existir nenhum usuário). Em produção a senha precisa ter ≥12 caracteres e não ser fraca. Em `DEBUG` sem senha, usa `admin`/`admin`. |
| `DOCUMENT_ENCRYPTION_KEY` | Chave Fernet que criptografa fotos/PDFs no banco (obrigatória em produção). |
| `TRUSTED_PROXY_COUNT` | Proxies à frente do app (Railway = 1), para o IP real. |
| `TEMP_PASSWORD_HOURS` / `TEMP_MAX_LOGIN_ATTEMPTS` | Validade (padrão 48 h) e limite de tentativas (padrão 3) da senha provisória de 4 dígitos. |
| `MAX_UPLOAD_MB` | Limite do upload (padrão 12; o envio ao Gemini vai em base64, +33%, e o teto da requisição é ~20 MB). |
| `GEMINI_MAX_CONCURRENCY` | Chamadas simultâneas ao Gemini (padrão 2). |
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

Para rodar contra PostgreSQL (como no Railway): `TEST_DATABASE_URL=postgresql://usuario@localhost:5432/banco_de_teste pytest` — o banco precisa ser UTF-8 e será recriado a cada teste.

Cobrem variação %, parsing de valores/datas brasileiros, matching UC → loja (e sugestões para erro de leitura),
duplicidade, parsing/validação da resposta do Gemini, upload (magic bytes), cálculos dos gráficos e o fluxo HTTP completo
de importação — todos sem chamar a API (o Gemini é substituído por `MockExtractor`).

## Deploy no Railway

1. Crie um projeto no Railway a partir deste repositório do GitHub (build automático via Nixpacks; `railway.json` e `Procfile` já definem o start).
2. Adicione o plugin **PostgreSQL**. No serviço web, em *Variables*, referencie `DATABASE_URL` do Postgres.
3. Defina as variáveis do serviço web (atalho: abra *Variables → Raw Editor* e cole o conteúdo de `railway.env.example`, preenchendo `GEMINI_API_KEY`, `SECRET_KEY` e `ADMIN_PASSWORD`):
   `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.5-flash-lite`, `EXTRACTION_PROVIDER=gemini`, `SECRET_KEY`, `DOCUMENT_ENCRYPTION_KEY`,
   `DEBUG=false`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
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
- Sem 2FA e sem recuperação de senha por e-mail (o admin redefine em *Usuários*). Veja o risco residual em `SECURITY.md`.
- A leitura por IA nunca foi validada aqui com a API real do Gemini (sem chave neste ambiente): os testes usam o mock.
  Antes de usar em produção, importe algumas contas reais e confira a tela de revisão.
