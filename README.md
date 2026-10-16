# Economart — Controle de Energia

Sistema web para controlar as contas de energia (CEMIG, COELBA, Energisa e outras despesas de energia) de cada loja
da Economart Atacadista. Quem lança envia a **foto ou o PDF da conta**, a IA (Gemini) lê os dados, o sistema acha
sozinho a **unidade consumidora e a loja**, mostra a **conferência** ao lado da imagem e, ao confirmar, atualiza o
histórico, os gráficos, a folha impressa da loja e o painel da diretoria.

[![Deploy on Railway](https://img.shields.io/badge/Deploy-Railway-violet)](https://railway.app)
[![Python](https://img.shields.io/badge/Python-3.12+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Railway-336791)](https://www.postgresql.org/)
[![Testes](https://img.shields.io/badge/testes-451%20passando-brightgreen)](docs/testing.md)

> **Vai usar o sistema?** [`TUTORIAL.md`](TUTORIAL.md) ([PDF](docs/Tutorial_Controle_de_Energia.pdf)) e a tela
> **Ajuda** dentro do sistema, diferente para cada perfil.
> **Vai programar nele?** [`docs/README.md`](docs/README.md) (documentação técnica) e [`AGENTS.md`](AGENTS.md)
> ("para fazer X, leia Y", para pessoas e agentes de IA).
> **Segurança:** [`SECURITY.md`](SECURITY.md) e [`docs/security.md`](docs/security.md).

---

## Sumário

- [Visão geral](#visão-geral)
- [Stack tecnológica](#stack-tecnológica)
- [Perfis de usuário](#perfis-de-usuário)
- [Funcionalidades](#funcionalidades)
- [Fluxo de uma conta](#fluxo-de-uma-conta)
- [Segurança e LGPD](#segurança-e-lgpd)
- [Setup local](#setup-local)
- [Deploy no Railway](#deploy-no-railway)
- [Configurações](#configurações)
- [Endpoints HTTP](#endpoints-http)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Testes e CI](#testes-e-ci)
- [Convenções de código](#convenções-de-código)
- [Limitações conhecidas](#limitações-conhecidas)
- [Mudanças recentes](#mudanças-recentes)
- [Licença e créditos](#licença-e-créditos)

---

## Visão geral

O sistema substitui a planilha "ENERGIA — GRÁFICO POR LOJA", montada à mão. A folha impressa por loja mantém o
formato e os números da planilha (o Total Geral bate ao centavo; `tests/test_report_sheet.py`).

A IA nunca grava sozinha: toda leitura passa pela tela de conferência. Unidade desconhecida não descarta a conta
(cadastrar ou associar), e duplicidades (mesma unidade + mês, ou mesma nota fiscal) pedem decisão: substituir ou
salvar como nova. Arquivo que não é conta de energia é recusado e apagado. O original (foto/PDF) fica cifrado no
banco por 6 meses; os números lidos ficam para sempre.

## Stack tecnológica

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI 0.115+, Uvicorn |
| ORM e migrações | SQLAlchemy 2, Alembic (aplicadas ao subir) |
| Banco | PostgreSQL (Railway) / SQLite (dev local) |
| Templates | Jinja2 (autoescape), sem framework de JavaScript |
| Gráficos | Chart.js embutido em `static/js/vendor` (sem CDN) |
| Leitura das contas | Google Gemini (`google-genai`), com modo `mock` para dev e testes |
| PDF e imagem | pypdfium2 (páginas), pypdf (conteúdo ativo), Pillow (rotação/tamanho) |
| Exportações | openpyxl (XLSX), python-pptx (PowerPoint), CSV |
| Criptografia | `cryptography` (Fernet) para os originais e o segredo do 2FA |
| 2FA | TOTP (Google Authenticator) para administradores; QR com `segno` |
| Deploy | Railway (Nixpacks, `railway.json`, `Procfile`) |

## Perfis de usuário

| Perfil | Código | O que faz |
|---|---|---|
| **Administrador** | `admin` | Usuários e perfis, auditoria, lista oficial de lojas, rede da empresa, lixeira geral. Pode operar o sistema, mas o dia a dia é do funcionário |
| **Funcionário** | `operator` | Toda a gestão de energia: lojas, unidades, fornecedores, envio das contas, lançamento manual (também em lote), correções, vencimentos, impressão |
| **Diretoria** | `director` | Só consulta. Entra direto no **Painel executivo** (`/diretoria`), abre lojas e imprime |
| **Consulta** | `viewer` | Só visualiza e imprime |

## Funcionalidades

### Para o funcionário
- **Importar conta** por foto ou PDF: leitura pelo Gemini, unidade e loja identificadas pelo número da unidade
  consumidora (com sugestão quando a leitura erra um dígito), conferência com a imagem ao lado.
- **Anotação à mão** na folha (ex.: "CD 300") é lida e comparada com o código, o nome e os apelidos da loja.
- **Lançamento manual** (uma conta ou várias em lote) para fornecedores sem conta lida por foto.
- **+ Novo ponto de energia** em qualquer tela: loja, unidade, distribuidora e dia de vencimento.
- **Vencimentos**: aviso ao entrar ("Vence hoje", "Venceu há N dias"), sino com a lista e **Já paguei**.
- **Excluiu errado?** Botão **Desfazer** na hora e **Lixeira** pessoal de 30 dias.
- **Folha de impressão** por loja (A4 paisagem, formato da planilha, agrupada por referência ou vencimento) e
  **ficha da conta** com três gráficos dos últimos 12 meses.

### Para a diretoria — Painel executivo em 5 abas
- **Visão geral:** destaques, indicadores, gasto mensal da empresa, ranking e pendências.
- **Lojas:** variação, composição por fornecedor, evolução, custo por kWh comparado com a média da própria
  distribuidora, comparação de duas lojas, mapa de calor loja × mês e tabela comparativa.
- **Gasto evitável:** ultrapassagem de demanda, energia reativa excedente e juros/multa, somados a partir dos itens
  da fatura, por loja e por mês.
- **Contratos:** demanda contratada × maior medida em 12 meses (aparece só quando alguma conta tem demanda).
- **Ano:** acumulado, comparação com o ano anterior e projeção (com 12 meses de histórico) e "por que o gasto
  mudou", separando efeito consumo e efeito preço.
- Filtros de período, região e fornecedor; exportação em **XLSX**, **PowerPoint** e CSV; impressão.

### Para o administrador
- Usuários com senha provisória de 4 dígitos (48 h), redefinição, desbloqueio, troca de perfil e desativação;
  ações sobre outro administrador pedem a senha de quem age.
- **Painel admin:** uso do sistema por pessoa, quem está on-line, coluna **Rede** (último login na empresa ou fora).
- **Auditoria** à prova de adulteração, com filtro, exportação CSV, *Verificar integridade* e a marca "na
  empresa"/"fora" em cada evento.
- **Rede da empresa:** cadastro dos IPs dos links da empresa; IPs de login frequentes ainda não cadastrados
  aparecem para cadastrar com um clique.
- **Lista oficial de lojas** (importada pela tela, não fica no repositório) e vínculo das lojas do sistema.
- **Lixeira geral** (180 dias), com "restaurar tudo de uma pessoa".

### Recursos transversais
- **Central de alertas:** cada conta nova é comparada com o histórico da própria unidade (valor, R$/kWh, demanda
  acima do contratado com tolerância de 5%, nota fiscal repetida, itens que não fecham, período de leitura estranho).
- **Demanda só aparece quando existe:** sem nenhuma conta com demanda, o assunto some de todas as telas, exportações
  e da ajuda.
- **Ajuda por perfil** e atalhos de teclado (`?` mostra a lista).
- **Sem tela branca entre páginas** (View Transitions) e relatórios abertos na mesma aba com **Voltar**.
- **Fora do ar:** faixa avisando que o servidor não respondeu e página offline (service worker só para ela).
- **Aviso antes de a sessão expirar** e proteção contra sair de um formulário com alterações não salvas.
- **Acessibilidade:** "Ir para o conteúdo", foco visível, rótulos em todos os campos, mensagens anunciadas a
  leitores de tela, `prefers-reduced-motion`.

## Fluxo de uma conta

```
  Foto/PDF ──► validação (tipo real, tamanho, ≤10 páginas, PDF sem JavaScript)
                 │  mesmo arquivo já salvo? ──► recusado sem chamar o Gemini
                 ▼
          ┌──────────────┐   não é conta   ┌──────────┐
          │  processing  │ ──────────────► │ rejected │  bytes apagados
          └──────┬───────┘                 └──────────┘
                 │ Gemini lê → JSON validado → unidade → loja
                 ▼                 erro ──► failed (Tentar novamente)
          ┌──────────────┐
          │    ready     │  conferência: imagem ao lado, campos editáveis,
          └──────┬───────┘  duplicidade (substituir / salvar como nova)
        confirma │ cancela ──► cancelled
                 ▼
          ┌──────────────┐
          │  confirmed   │ ──► histórico, gráficos, alertas, folha, painel
          └──────────────┘
```

Importação parada em `processing` por mais de 10 minutos vira `failed` (cobre reinício do servidor no meio da
leitura). No máximo 2 leituras simultâneas no Gemini, com retentativa em 429/5xx e disjuntor depois de 5 falhas.

## Segurança e LGPD

Resumo; o detalhe está em [`docs/security.md`](docs/security.md).

- **Senhas** com scrypt; bloqueio após 5 erros por 15 min (3 para senha provisória). **2FA** (TOTP) para
  administradores, obrigatório com `REQUIRE_ADMIN_2FA=true`.
- **Sessão** em cookie assinado (`Secure` em produção), 60 min de inatividade e 12 h no máximo; logout, troca de
  senha e mudança de perfil derrubam as outras sessões.
- **CSRF** por token e por origem; **CSP** com nonce; HSTS e demais cabeçalhos.
- **Limite de requisições** por usuário com login (por IP antes do login), limite de corpo da requisição.
- **IP real** pelo `X-Real-IP` do Railway (há uma CDN no caminho); tela para conferir.
- **Auditoria encadeada** (HMAC): qualquer alteração feita fora do sistema aparece em *Verificar integridade*.
- **Originais cifrados** (Fernet) no banco, com rotação de chave; apagados depois de 6 meses.
- **Upload:** tipo conferido pelos bytes, PDF com JavaScript ou ação automática recusado, chaves nunca em log.
- **Nada se perde:** exclusões vão para a lixeira e podem ser restauradas.
- **Produção não sobe** sem `SECRET_KEY`, `DOCUMENT_ENCRYPTION_KEY`, PostgreSQL e senha forte do admin.

## Setup local

### Pré-requisitos
- Python 3.12+ (testado em 3.13)
- Chave do Gemini (<https://aistudio.google.com/apikey>), opcional em dev: o modo `mock` não chama a API

### Instalação

```bash
git clone https://github.com/guiolindo/Agua-e-luz---economart.git
cd Agua-e-luz---economart
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                 # Windows: copy .env.example .env
```

No `.env`, para começar basta:

```env
DEBUG=true
EXTRACTION_PROVIDER=mock             # ou gemini + GEMINI_API_KEY
DATABASE_URL=sqlite:///app.db
```

### Rodar

```bash
python run.py                        # http://127.0.0.1:8000
python -m scripts.seed_demo          # opcional: loja CD300 com o histórico jan–ago/2026
python -m scripts.seed_demo_company  # opcional: lojas fictícias para ver o painel executivo
```

**Primeiro login:** com `DEBUG=true` e sem `ADMIN_PASSWORD`, o administrador é `admin`/`admin`. Em produção,
`ADMIN_USERNAME`/`ADMIN_PASSWORD` criam o primeiro administrador (senha com 12+ caracteres, não fraca).

Passo a passo completo e erros comuns: [`docs/getting-started.md`](docs/getting-started.md).

## Deploy no Railway

1. Crie o projeto a partir deste repositório (Nixpacks; `railway.json` e `Procfile` já definem o start e o
   healthcheck `/health`).
2. Adicione o **PostgreSQL** e referencie `DATABASE_URL` no serviço web.
3. Em *Variables → Raw Editor*, cole `railway.env.example` e preencha:

| Variável | Valor |
|---|---|
| `DATABASE_URL` | Referência ao Postgres |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DOCUMENT_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | primeiro administrador |
| `GEMINI_API_KEY` | chave do Gemini |
| `DEBUG` | `false` |
| `REQUIRE_ADMIN_2FA` | `true` (recomendado) |

4. Gere o domínio público em *Settings → Networking*.

Os originais ficam no banco (tabela `documents`): não há volume nem armazenamento externo. Migrações rodam sozinhas
a cada deploy. Backup, troca de chaves e incidentes: [`docs/operations.md`](docs/operations.md).

## Configurações

Todas as variáveis, com padrão e efeito, estão em [`docs/operations.md`](docs/operations.md#variáveis-de-ambiente).
As mais usadas:

| Grupo | Variáveis |
|---|---|
| Banco e início | `DATABASE_URL`, `RUN_MIGRATIONS`, `DEBUG`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` |
| Segurança | `SECRET_KEY`, `DOCUMENT_ENCRYPTION_KEY` (várias = rotação), `PSEUDONYM_KEY`, `REQUIRE_ADMIN_2FA`, `MAX_LOGIN_ATTEMPTS`, `LOGIN_BLOCK_MINUTES`, `SESSION_IDLE_MINUTES`, `SESSION_MAX_HOURS` |
| IP e rede | `CLIENT_IP_SOURCE` (`real-ip`), `TRUSTED_PROXY_COUNT`, `COMPANY_NETWORKS` |
| Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL` (`gemini-3.5-flash-lite`), `EXTRACTION_PROVIDER` (`gemini`/`mock`), `GEMINI_MAX_CONCURRENCY`, `MAX_UPLOAD_MB` |
| Retenção e lixeira | `DOCUMENT_RETENTION_DAYS` (183), `TRASH_DAYS` (180), `TRASH_PERSONAL_DAYS` (30), `MAX_DELETES_PER_HOUR` (15) |

Variável com nome errado é ignorada sem aviso: confira com a tabela.

## Endpoints HTTP

Referência completa, com perfil exigido e códigos de resposta: [`docs/api-reference.md`](docs/api-reference.md).

| Área | Caminhos principais | Perfil |
|---|---|---|
| Entrada | `/login`, `/login/2fa`, `/logout`, `/account/password`, `/account/2fa` | público / logado |
| Painel | `/`, `/alertas`, `/ajuda` | logado |
| Lojas e unidades | `/stores`, `/stores/{id}`, `/stores/{id}/report`, `/units/{id}` | logado (editar: escrita) |
| Contas | `/notas` (+ `export.xlsx`/`.csv`), `/bills/{id}/print` | logado |
| Importação | `/import`, `/import/{id}`, `/import/{id}/review`, `/import/{id}/confirm` | escrita |
| Lançamento e lixeira | `/manual`, `/manual/lote`, `/points/new`, `/lixeira` | escrita |
| Diretoria | `/diretoria?aba=geral\|lojas\|evitavel\|contratos\|ano`, `/diretoria/export.xlsx`/`.pptx`/`.csv` | diretoria, admin |
| Administração | `/admin`, `/admin/users`, `/admin/audit`, `/admin/ip`, `/admin/lojas` | admin |
| Infra | `/health`, `/sw.js`, `/offline`, `/static/*` | público |

## Estrutura do projeto

```
app/
  main.py              fábrica da aplicação, middlewares, handlers de erro, /health, /sw.js
  config/              Settings (variáveis de ambiente / .env)
  database.py          engine e sessão (SQLite ↔ PostgreSQL, keepalive)
  db_migrate.py        aplica as migrações do Alembic ao subir
  security.py          senha, sessão, CSRF, perfis, IP real
  middleware.py        cabeçalhos/CSP, rate limit, limite de corpo, ID da requisição, cache do /static
  models/              lojas, unidades, tipos, contas, lançamentos, documentos, importações, auditoria,
                       usuários, lixeira, rede da empresa
  schemas/             contrato JSON da IA e validação de formulários
  services/
    gemini_service.py      ÚNICO ponto que usa o SDK do Gemini (+ circuit_breaker.py)
    import_service.py      upload → leitura em segundo plano → salvar/substituir
    matching_service.py    unidade consumidora → loja (+ sugestões)
    alert_service.py       central de alertas
    executive_service.py   painel executivo; director_extra.py: gasto evitável, contratos, ano
    trash_service.py       lixeira, Desfazer, limite de exclusões
    network_service.py     rede da empresa
    audit_service.py       auditoria encadeada
    xlsx_service.py, pptx_service.py   exportações
  routes/              uma área por arquivo (auth, imports, stores, director, admin, trash...)
  templates/, static/  Jinja2, CSS próprio, JavaScript sem framework, Chart.js local
migrations/versions/   0001–0007 (Alembic)
scripts/               seed_demo, seed_demo_company, purge_documents, reset_2fa, unlock_user
tests/                 pytest (Gemini substituído pelo MockExtractor)
docs/                  documentação técnica
```

## Testes e CI

```bash
pytest -q                            # 451 testes, SQLite, sem chamar o Gemini
TEST_DATABASE_URL=postgresql://usuario@localhost:5432/banco_teste pytest -q   # contra PostgreSQL (UTF-8)
```

O CI (`.github/workflows/ci.yml`) roda a cada push: `ruff` (erros de sintaxe e nomes), `node --check` em todo o
JavaScript do navegador (um erro de sintaxe desligaria todos os botões da tela), `pytest` e `pip-audit` nas
dependências. Organização da suíte e o que não é coberto: [`docs/testing.md`](docs/testing.md).

## Convenções de código

- **Python 3.12**, type hints, `snake_case`; regras de negócio em `services/`, rotas finas.
- **Datas:** gravadas em UTC, exibidas em Brasília (`America/Sao_Paulo`); o "hoje" dos vencimentos é o de Brasília.
- **Texto para quem usa:** português, direto, sem jargão técnico e sem "(s)" de formulário (`plural()` no template).
- **Auditoria:** toda ação que muda dado registra em `audit_log`, com antes/depois quando há edição.
- **Banco:** toda mudança de esquema é uma revisão nova do Alembic; nunca apague uma revisão já aplicada.
- **Frontend sem build:** JavaScript puro, sem CDN; scripts com nonce por causa da CSP.
- **Segredos** só em variável de ambiente; a lista de lojas da empresa não entra no repositório.

## Limitações conhecidas

- Uma conta por envio (não há envio de vários arquivos de uma vez; há lançamento manual em lote).
- Sem recuperação de senha por e-mail: o administrador redefine em *Usuários*.
- 2FA só para administradores.
- O limite de requisições é em memória, por processo: com mais de uma instância, cada uma conta separado.
- Leitura pelo Gemini testada com contas reais de CEMIG e COELBA. Em contas de média tensão (Grupo A, ex.: Verde),
  a demanda e o consumo em kWh ainda podem vir vazios: a conferência mostra os campos para preencher. Distribuidora
  nova pede atenção nas primeiras contas.

Riscos residuais de segurança: [`SECURITY.md`](SECURITY.md). Próximos passos: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Mudanças recentes

Histórico completo, dia a dia, em [`CHANGELOG.md`](CHANGELOG.md); o porquê das decisões em
[`DECISIONS.md`](DECISIONS.md).

- **Painel executivo em 5 abas** com Gasto evitável, Contratos e Ano (projeção só com 12 meses de dados).
- **Desfazer e lixeira:** pessoal de 30 dias para quem excluiu, geral de 180 dias para o administrador.
- **Demanda só aparece quando existe** em alguma conta.
- **IP real na auditoria** (`X-Real-IP`, a CDN do Railway ficava no lugar) e **rede da empresa** cadastrada pelo
  administrador, gravada em cada evento.
- **Limites de acesso por pessoa**, não por IP (escritório e CGNAT saem todos pelo mesmo IP).
- **Sem tela branca entre páginas**, faixa de servidor fora do ar e página offline, aviso de sessão expirando.
- **Limpeza de texto:** plurais certos em todas as telas e detalhes da auditoria em português.

## Licença e créditos

Software proprietário da Economart Atacadista, de uso interno.

Autoria, origem do projeto e bibliotecas usadas: [`CREDITS.md`](CREDITS.md).
