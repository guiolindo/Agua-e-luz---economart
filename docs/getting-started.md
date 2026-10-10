# Guia rápido — como rodar o sistema localmente

Este guia instala o Economart (controle de contas de energia) na sua
máquina, configura o mínimo necessário e faz o primeiro login. Para
deploy em produção, ver [operations.md](operations.md).

## Pré-requisitos

- **Python 3.12** (arquivo `.python-version` e CI usam 3.12). Conferir
  com `python --version`.
- **Git**, para clonar o repositório.
- Windows, Linux ou macOS.

Banco de dados: **não precisa instalar Postgres**. Sem `DATABASE_URL`,
o sistema usa SQLite no arquivo `app.db`, criado **na pasta onde o
processo é iniciado** (a URL padrão é `sqlite:///app.db`, relativa ao
diretório atual). Arquivos `*.db` e `.env` estão no `.gitignore`.

---

## Passo a passo

### 1. Clonar e criar o ambiente virtual

```bash
git clone <url-do-repositório> agua-e-luz---economart
cd agua-e-luz---economart
```

**Linux / macOS**:
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

(`.venv/` e `venv/` estão no `.gitignore`.)

### 2. Instalar dependências

Dois arquivos:

- `requirements.txt` — o que roda em produção (FastAPI, uvicorn,
  SQLAlchemy 2, Jinja2, Alembic, pydantic-settings, google-genai,
  psycopg, Pillow, pypdfium2, cryptography, segno, etc.).
- `requirements-dev.txt` — inclui o anterior (`-r requirements.txt`) e
  acrescenta `pytest` e `httpx`. Use este para desenvolver e testar.

```bash
pip install -r requirements-dev.txt
```

Para só rodar o sistema, `pip install -r requirements.txt` basta.

### 3. Configurar o `.env`

Copie o exemplo:

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

O `.env` é lido por `pydantic-settings` (`env_file=".env"`, a partir
do diretório atual). Para rodar localmente o mínimo é:

```ini
DEBUG=true
EXTRACTION_PROVIDER=mock
ADMIN_USERNAME=admin
ADMIN_PASSWORD=uma-senha-local
```

O que cada coisa faz:

- `DEBUG=true` — dispensa `SECRET_KEY` e `DOCUMENT_ENCRYPTION_KEY`.
  Sem `SECRET_KEY` o app gera uma chave temporária a cada subida (as
  sessões caem a cada reinício, e há um aviso no log). Sem
  `DOCUMENT_ENCRYPTION_KEY` os arquivos enviados ficam **sem cifra** no
  banco. O cookie de sessão deixa de exigir HTTPS e o HSTS não é
  enviado.
- `EXTRACTION_PROVIDER=mock` — a "leitura" da conta devolve sempre o
  JSON de `tests/fixtures/cemig_set_2026.json`, sem chamar o Gemini e
  sem gastar cota. Para ler contas de verdade, use `gemini` (o padrão)
  e preencha `GEMINI_API_KEY`.
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` — ver "Primeiro login".

Em `.env.example` o `DEBUG` já vem `true`. Se `DEBUG=false` (ou a
variável for removida: o padrão no código é `false`), o servidor
**recusa subir** sem `SECRET_KEY` de pelo menos 32 caracteres, sem
`DOCUMENT_ENCRYPTION_KEY` válida e com `DATABASE_URL` apontando para
SQLite. Ver "Erros comuns".

Para gerar chaves (úteis se você quiser testar com `DEBUG=false`):

```bash
# SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
# DOCUMENT_ENCRYPTION_KEY (chave Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

A lista completa de variáveis está em
[operations.md](operations.md#variáveis-de-ambiente).

### 4. Subir o servidor

Duas formas equivalentes, ambas a partir da raiz do projeto:

```bash
python run.py
# ou
uvicorn app.main:app --reload
```

`run.py` chama `uvicorn.run("app.main:app", host="127.0.0.1",
port=8000, reload=True)`. Abra `http://127.0.0.1:8000`.

Na subida (função `lifespan` em `app/main.py`) o sistema:

1. aplica as migrações do Alembic (`RUN_MIGRATIONS=true`, o padrão),
   criando todas as tabelas num banco novo;
2. executa o `seed`: cadastra os tipos de registro padrão (CEMIG,
   COELBA, ENERGISA, CEMIG Geração e Transmissão, LL Energia, CCEE,
   combustível e manutenção de gerador) e cria o administrador se não
   houver nenhum usuário;
3. inicia a rotina de retenção de documentos.

### 5. Primeiro login

O administrador é criado **somente se a tabela de usuários estiver
vazia**, com `ADMIN_USERNAME` (padrão `admin`) e `ADMIN_PASSWORD`:

| Situação | Resultado |
|---|---|
| `ADMIN_PASSWORD` definido, `DEBUG=true` | Usa a senha informada, sem validação de força |
| `ADMIN_PASSWORD` definido, `DEBUG=false` | Exige mínimo de 12 caracteres e passa em `validate_password`; senão o app não sobe (`ADMIN_PASSWORD recusada: ...`) |
| `ADMIN_PASSWORD` vazio, `DEBUG=true` | Cria o admin com a senha `admin` e avisa no log |
| `ADMIN_PASSWORD` vazio, `DEBUG=false` | Nenhum usuário é criado; o log avisa para definir a variável |

Entre em `/login` com esse usuário e senha. Alterar `ADMIN_PASSWORD`
depois **não** muda a senha de um admin já criado: a variável só vale
quando o banco não tem usuários. Para trocar a senha depois, use
*Conta → senha* (`/account/password`) ou, a partir de outro
administrador, *Usuários → Redefinir senha* (gera senha provisória de
4 dígitos).

O administrador pode então criar os demais usuários em *Usuários*
(perfis: administrador, funcionário, diretoria, consulta — descritos
no [README](../README.md)).

---

## Dados de demonstração

Dois scripts, executados **da raiz do projeto**, com o venv ativo e o
mesmo `.env` do app (eles usam o `DATABASE_URL` configurado):

```bash
python -m scripts.seed_demo
python -m scripts.seed_demo_company     # depois do anterior
```

### `scripts/seed_demo.py`

- Cria as tabelas (`create_all`), roda o `seed` e, se ainda não existe
  loja com código `CD300`, cria a loja **CD300** (Ribeirão das Neves/MG)
  com a unidade `12.060.073.018-19`.
- Lê `scripts/demo_cd300.json` (tabela dinâmica da planilha impressa,
  jan–out/2026, valores por mês de **vencimento**) e cria as contas da
  CEMIG Distribuição como `EnergyBill` (a referência é o mês anterior
  ao da coluna) e os demais fornecedores como `ManualRecord`.
- As datas de vencimento "dia 9" são **assumidas** (comentário no
  próprio script): só a de set/2026 (09/10/2026) vem de conta real.
- Idempotente: se `CD300` já existe, imprime "CD300 já existe; nada a
  fazer."
- Os valores são os da planilha real; o teste
  `tests/test_report_sheet.py` usa esses números como critério de
  aceite.

### `scripts/seed_demo_company.py`

- Rode **depois** de `seed_demo`. Cria as lojas `DEMO-01` a `DEMO-08`
  com 12 meses (set/2025 a ago/2026) de contas e lançamentos gerados
  por fórmula (`random.Random(300)`, determinístico), e marca o CD300
  com região `MG`.
- Serve para visualizar o **painel da diretoria** (`/diretoria`) com
  várias lojas. Todo dado é **fictício** — o próprio script avisa para
  não usar em produção.
- Idempotente: se já existe loja `DEMO-*`, imprime "Lojas DEMO já
  existem."

Para recomeçar do zero em desenvolvimento, apague o `app.db` (com o
servidor parado) e suba de novo.

---

## Erros comuns na instalação

### `RuntimeError: Configuração insegura — o servidor não inicia em produção sem corrigir`
`app/startup_checks.py` roda quando `DEBUG=false`. Lista os problemas:
`SECRET_KEY` ausente/curta (< 32 caracteres) ou fraca,
`DOCUMENT_ENCRYPTION_KEY` ausente ou que não é chave Fernet, e
`DATABASE_URL` apontando para SQLite. Localmente, ponha `DEBUG=true` no
`.env`.

### `RuntimeError: ADMIN_PASSWORD recusada: ...`
Só acontece com `DEBUG=false` e banco sem usuários. A senha precisa ter
no mínimo 12 caracteres e não ser fraca.

### `ModuleNotFoundError: No module named 'app'`
O comando foi executado fora da raiz do projeto. Faça `cd` para a pasta
que contém `app/`, `run.py` e `alembic.ini`. Para os scripts use sempre
`python -m scripts.<nome>` (e não `python scripts/<nome>.py`), por causa
do import `from app import ...`.

### `ModuleNotFoundError` de `alembic`, `google`, `segno`, `psycopg`...
O venv não está ativo ou o `pip install` foi feito em outro Python.
Confira o prompt `(.venv)` e rode `pip install -r requirements-dev.txt`
de novo.

### "A chave do Gemini (GEMINI_API_KEY) não está configurada no servidor."
Aparece ao importar uma conta com `EXTRACTION_PROVIDER=gemini` e
`GEMINI_API_KEY` vazio. Use `EXTRACTION_PROVIDER=mock` para testar sem
chave, ou preencha a chave.

### O login funciona mas a sessão cai sempre que reinicio
Com `DEBUG=true` e `SECRET_KEY` vazio a chave é regenerada a cada
subida. Defina um `SECRET_KEY` fixo no `.env`.

### `OperationalError: unable to open database file`
Pasta sem permissão de escrita. O `app.db` é criado no diretório de
trabalho; rode a partir de uma pasta sua ou aponte `DATABASE_URL` para
outro caminho (`sqlite:///C:/caminho/app.db`).

### Quero usar PostgreSQL localmente
Defina `DATABASE_URL=postgresql://usuario:senha@localhost:5432/banco`.
O sistema converte `postgres://` e `postgresql://` para
`postgresql+psycopg://` (driver psycopg 3, já em `requirements.txt`).
Com `DEBUG=false` as validações de segredo acima continuam valendo.
**Não verificado**: este guia não foi testado contra um Postgres real.

---

## Rodando os testes

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Detalhes em [testing.md](testing.md).

---

## Próximos passos

- Deploy, variáveis, backup e incidentes: [operations.md](operations.md)
- Testes: [testing.md](testing.md)
- Perguntas frequentes: [faq.md](faq.md)
- Segurança: [SECURITY.md](../SECURITY.md)
