# Testes — suíte automatizada e estratégia

Como rodar a suíte pytest, o que cada arquivo cobre, como adicionar
testes e o que **não** é coberto.

## Estado atual

- **311 testes** passando na última execução completa (2026-10-10). Dos 311, 61 estão em
  `test_security.py`. O número cresce a cada mudança; confira com
  `python -m pytest --collect-only -q | tail -1`.
- Tempo: cerca de 2 minutos numa execução local com SQLite (a maior
  parte é hash de senha real, scrypt, nos testes de login). Medido uma
  vez, num Python 3.13; o CI usa 3.12.
- Sem testes E2E de navegador. Cobertura de código não é medida
  (`coverage` não está nas dependências).

## Como rodar

Do zero:

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest -q
```

`requirements-dev.txt` inclui `requirements.txt` e acrescenta `pytest`
e `httpx` (necessário ao `TestClient` do FastAPI).

Variações úteis:

```bash
python -m pytest tests/test_security.py            # um arquivo
python -m pytest tests/test_migrations.py::test_upgrade_is_idempotent   # um teste
python -m pytest -x -q                             # para no primeiro erro
python -m pytest -k "lockout or 2fa"               # por nome
python -m pytest -s tests/test_due.py              # mostra print()
```

Não é preciso `.env`, chaves nem rede: o `conftest.py` define tudo.

---

## Organização de `tests/`

Contagens medidas com `--collect-only`.

| Arquivo | Testes | O que cobre |
|---|---|---|
| `conftest.py` | – | Ambiente de teste, fixtures `db`, `client`, `png` e a classe `Client` (login e CSRF automáticos) |
| `fixtures/` | – | JSONs de resposta do Gemini usados pelo mock e pelos testes de parsing: `cemig_set_2026.json`, `cemig_gt_ago_2026.json`, `coelba_ago_2026.json`, `energisa_set_2026.json` |
| `test_2fa_audit.py` | 23 | 2FA TOTP do administrador (vetor RFC 6238, anti-replay, códigos de recuperação, `REQUIRE_ADMIN_2FA`, reset por outro admin), cadeia de integridade da auditoria, disjuntor do Gemini, `/health` e CSV da auditoria |
| `test_alerts.py` | 10 | Central de alertas: regras sobre o histórico da própria unidade, "Conferido" (`AlertAck`) e permissões |
| `test_app_flow.py` | 9 | Fluxo principal: login, CSRF, upload inválido, importação completa, decisão de duplicata, cadastro de unidade na importação, lançamentos manuais. Define os helpers `_make_store`, `_upload`, `_form_from_review` |
| `test_calculation.py` | 4 | `calculation_service`: variação percentual, `add_months`, `month_range` |
| `test_cemig_gt.py` | 8 | Conta da CEMIG Geração e Transmissão (tipo `bill` com unidade própria), conversão do tipo manual legado pelo `seed` sem mexer nos lançamentos antigos, e R$/kWh sem contar o kWh duas vezes |
| `test_coelba_and_limits.py` | 9 | Conta COELBA, redução de foto grande, rotação EXIF, PDF com páginas demais, importação travada (stale), modelo Gemini obsoleto, chaves redigidas nos logs |
| `test_director.py` | 20 | Painel da diretoria: totais, ranking, custo por kWh, filtros, mês parcial, comparação ano a ano, exportação CSV, perfil executivo da loja, perfis com acesso. Define `_user` (cria e loga usuário de um perfil) |
| `test_due.py` | 16 | Vencimentos: dia 31 em mês curto, "hoje" no fuso do Brasil, baixa ("Já paguei"), "+ Novo ponto de energia", avisos só para o funcionário, página de ajuda por perfil |
| `test_energisa.py` | 3 | Conta ENERGISA (baixa tensão, consumo único) |
| `test_export_csv.py` | 3 | CSV de contas (filtros, compatível com Excel, neutralização de fórmulas em `_csv_cell`, acesso da consulta) |
| `test_extraction.py` | 10 | `parse_response_text` (resposta válida, inválida, campos nulos), Gemini sem chave, formulário da conferência (formatos brasileiros e validação), casamento de unidade com a loja |
| `test_lote_unlock.py` | 15 | Desbloqueio de usuário pelo admin e lançamento em lote (várias lojas) |
| `test_migrations.py` | 5 | Alembic: banco novo igual aos modelos, `upgrade` idempotente, adoção de banco pré-Alembic sem perda de dados, revisões `0001`–`0003` mantidas na cadeia |
| `test_parsing.py` | 19 | `utils.parsing` (decimais e datas em formato brasileiro, UC, referência) e `validate_upload` |
| `test_print_original.py` | 4 | Impressão da conta com o original: PDF página a página, imagem, e fallback para link se o PDF estiver corrompido ou expirado |
| `test_reject_non_bill.py` | 6 | Arquivo que não é conta: barrado, nada lançado, bytes apagados, motivo na auditoria |
| `test_report_sheet.py` | 3 | **Aceitação**: a folha impressa reproduz ao centavo a planilha da CD300 (totais por vencimento; tabela do imóvel por referência) |
| `test_roles.py` | 6 | Permissões por perfil (admin, funcionário, diretoria, consulta) e rastreabilidade na auditoria |
| `test_security.py` | 61 | Login obrigatório, bloqueio de conta, limite de requisições, sessão (ociosidade e duração máxima), cookies, política de senha, CSP e cabeçalhos, CSRF, limite de corpo, IP via proxy, criptografia de documentos e rotação de chave, recusa de configuração insegura. Define `_new_client`, `_create_user`, `_login` |
| `test_services.py` | 10 | Duplicatas por mês e nota, séries e variação dos gráficos, resumo da loja por mês de vencimento (reproduz a folha impressa) e por referência, filtro por fornecedor |
| `test_temp_password.py` | 6 | Senha provisória de 4 dígitos: validade, bloqueio na 3ª falha, só permite trocar a senha |
| `test_timezone.py` | 3 | Conversão UTC para Brasília (`utils.timezone`) |
| `test_unit_edit.py` | 8 | Edição de unidade e do dia de vencimento |
| `test_v2_features.py` | 22 | Retenção de documentos (410 em original expirado), tentativas e mensagens de erro do Gemini, apelido de loja à mão, tipos de conta novos, folha impressa, `ensure_columns` |

(As descrições vêm da leitura dos nomes e do início de cada arquivo;
não foram lidos todos os corpos de teste.)

---

## Fixtures (`tests/conftest.py`)

O arquivo define o ambiente **antes** de importar `app.main`:

```python
os.environ.update(DEBUG="true", EXTRACTION_PROVIDER="mock", GEMINI_API_KEY="",
    ADMIN_USERNAME="admin", ADMIN_PASSWORD="admin-pass-123", SECRET_KEY="test-secret",
    RUN_MIGRATIONS="false",
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db",
    DOCUMENT_ENCRYPTION_KEY=Fernet.generate_key().decode())
```

Consequências: SQLite num diretório temporário, sem Gemini real, sem
Alembic (as tabelas vêm de `create_all`), chave de documentos aleatória
por execução. O admin dos testes é `admin` / `admin-pass-123`.

| Fixture | Escopo | O que faz |
|---|---|---|
| `_fresh_rate_limits` | função, `autouse` | Chama `reset_rate_limits()` antes de cada teste; sem isso os limites de login/upload vazariam entre testes |
| `db` | função | `drop_all` + `create_all`, roda o `seed` e entrega uma `Session`. Os tipos de registro padrão e o admin existem |
| `client` | função | `drop_all`, sobe o app (`with TestClient(app)`, que executa o `lifespan` e recria as tabelas), e entrega um `Client` **já logado como admin** |
| `png` | função | Bytes de um PNG 1x1 válido (magic bytes corretos) para uploads |

`Client` (classe do `conftest.py`) embrulha o `TestClient`: `refresh()`
lê o `csrf_token` da página `/login`, `login()` autentica como admin, e
`get`/`post` enviam o token CSRF automaticamente e **não seguem
redirecionamentos** (`follow_redirects=False`), então os testes
verificam `303` e o cabeçalho `location`.

### Convenção: `client` ou `(client, db)`

- Teste que só exercita HTTP: `def test_x(client)`.
- Teste que precisa inspecionar ou preparar linhas no banco: `def
  test_x(client, db)`. É a forma mais usada (88 testes
  declaram `client, db` nesta ordem). Mantenha **`client` antes de
  `db`**, como nos testes existentes.
- Teste de serviço puro, sem HTTP: `def test_x(db)` ou nenhuma fixture
  (ex.: `test_parsing.py`, `test_calculation.py`).
- Para testar outro perfil, crie o usuário via o admin e logue em um
  segundo cliente: `_user(client, "func7", "operator")` (em
  `test_director.py`). A senha provisória vem da tela de criação.
- O banco é **recriado a cada teste**, então não há dependência de
  ordem entre testes.

---

## Convenções

- Comentários e mensagens em português; nomes de teste em inglês
  descrevendo a regra (`test_lockout_expires`).
- Reaproveite helpers de outros arquivos em vez de duplicar:
  `from tests.test_app_flow import _make_store, _upload,
  _form_from_review`; `from tests.test_security import _create_user,
  _login, _new_client`; `from tests.test_director import _user`.
- Tempo é injetado quando possível (ex.: `TODAY = date(2026, 10, 10)`
  em `test_alerts.py`; `now` em `totp_service.check_code`). Evite
  `sleep`.
- Gemini **nunca** é chamado: use `MockExtractor`, `parse_response_text`
  sobre os JSONs de `tests/fixtures/` ou `monkeypatch` para simular
  erros de rede (ver `test_v2_features.py`).
- Mudou um modelo em `app/models/`? Crie a migração; o
  `test_migrations.py` falha se houver divergência (`drift()`).
- Mexeu na folha da loja, no resumo ou no agrupamento por
  vencimento/referência? Rode `tests/test_report_sheet.py` antes de
  commitar: ele confere os totais da planilha original.

## Como adicionar um teste novo

1. Escolha o arquivo pela área (tabela acima) ou crie
   `tests/test_<area>.py`.
2. Escreva a função. Exemplo mínimo, de fluxo HTTP com dados:

   ```python
   from app.models import AuditLog
   from tests.test_app_flow import _make_store

   def test_minha_regra(client, db):
       """Descrição curta da regra."""
       store_id = _make_store(client)
       r = client.get(f"/stores/{store_id}")
       assert r.status_code == 200
       assert db.query(AuditLog).filter_by(action="create").count() >= 1
   ```
3. Rode só o arquivo: `python -m pytest tests/test_<area>.py -q`.
4. Rode a suíte inteira e o lint do CI:
   ```bash
   pip install ruff
   ruff check --select F,E9 .
   python -m pytest -q
   ```
5. Fixture compartilhada nova vai em `conftest.py`; helper específico
   de uma área fica no arquivo de teste dessa área.

---

## Integração contínua

`.github/workflows/ci.yml`, em todo `push` e `pull_request`, no
`ubuntu-latest` com Python 3.12 e cache de pip:

1. `pip install -r requirements-dev.txt ruff pip-audit`
2. `ruff check --select F,E9 .` — só erros do pyflakes (`F`, como
   import não usado) e erros de sintaxe (`E9`). **Não** é um lint de
   estilo.
3. `pytest -q`
4. `pip-audit -r requirements.txt` — vulnerabilidades conhecidas nas
   dependências. Está com `continue-on-error: true`: **avisa, não
   bloqueia**.

Não há etapa de deploy no CI; o deploy é do Railway
([operations.md](operations.md)).

## Postgres local (opcional)

`conftest.py` aceita `TEST_DATABASE_URL`. O `README.md` descreve o uso:
`TEST_DATABASE_URL=postgresql://usuario@localhost:5432/banco_de_teste
pytest`, com banco UTF-8 que será recriado a cada teste. **Não foi
executado ao escrever este documento** e o CI não faz isso.

---

## O que NÃO é coberto

- **Gemini real**: nenhum teste chama a API. O prompt, o JSON schema e
  o comportamento do modelo com contas reais só são validados por
  fixtures de respostas já obtidas e por testes de retentativa/erro
  com falhas simuladas.
- **PostgreSQL**: o CI roda só SQLite. Diferenças de dialeto (tipos,
  `ALTER` em tabelas grandes, `batch_alter_table` que só o SQLite
  exige) aparecem apenas em produção ou em execução manual com
  `TEST_DATABASE_URL`. As migrações são testadas em SQLite.
- **Restauração de backup**: nem `pg_dump`/`pg_restore` nem o
  procedimento de [operations.md](operations.md) têm teste. O que
  existe é `db_migrate.drift()` para conferir o banco restaurado, e
  ele precisa ser rodado à mão.
- **Subida real no Railway**: o incidente da revisão `0003`
  (`Can't locate revision identified by '0003'`) é prevenido por um
  teste de cadeia (`test_revisions_already_applied_in_production_stay_in_the_chain`),
  mas o teste não vê o banco de produção: ele só garante que os
  arquivos `0001`–`0003` existem. Revisões futuras aplicadas em
  produção precisam ser acrescentadas a esse teste à mão.
- **Navegador**: JavaScript do front-end, gráficos Chart.js e a
  acessibilidade (a auditoria axe-core citada no README foi feita fora
  da suíte).
- **Várias instâncias**: limite de requisições e disjuntor são em
  memória por processo; não há teste de concorrência entre processos.
- **Os scripts** `scripts/reset_2fa.py`, `scripts/purge_documents.py`
  e os `seed_demo*`: não há teste direto de linha de comando. A lógica
  que usam (`totp_service.disable`, `purge_expired_documents`) é
  testada nos arquivos de serviço.
