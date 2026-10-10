# Operações — deploy, backup e troubleshooting

Este documento cobre o que acontece **depois** do código pronto: subir
em produção (Railway), configurar variáveis, migrar o banco, fazer
backup, trocar chaves e resolver incidentes. Incorpora o conteúdo
útil de [OPERACAO.md](OPERACAO.md) (manual curto do administrador de
TI).

## Regras de ouro

1. **Nunca apague uma revisão do Alembic que já foi aplicada em
   produção.** Ver o [incidente de 2026-10-10](#incidente-de-2026-10-10--revisão-0003).
2. **Antes de cada deploy: backup do Postgres.**
3. **Depois de cada deploy: ler o log de inicialização.** Ele deve
   terminar com `Application startup complete`. Se não terminar, o
   deploy não está de pé, mesmo que o painel diga "deployed".

---

## Deploy no Railway

O sistema roda no Railway com banco PostgreSQL do próprio projeto. Três
arquivos na raiz configuram o serviço:

### `railway.json`

```json
{
  "build": { "builder": "NIXPACKS" },
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

- Build com Nixpacks (instala `requirements.txt`; a versão do Python
  vem de `.python-version`, 3.12).
- Start: um único processo `uvicorn` (sem gunicorn, sem múltiplos
  workers). Isso importa: o limite de requisições e o disjuntor do
  Gemini são **em memória, por processo**.
- Healthcheck em `/health`; reinício automático em caso de falha.

### `Procfile`

```
web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Equivalente ao `startCommand`, com `PORT` padrão 8000 fora do Railway.
Quando `railway.json` define `startCommand`, ele é o que vale no
Railway (comportamento da plataforma; não testado aqui).

### `railway.env.example`

Lista de variáveis para colar em *serviço web → Variables → Raw
Editor*. Os campos vazios (`GEMINI_API_KEY`, `SECRET_KEY`,
`DOCUMENT_ENCRYPTION_KEY`, `ADMIN_PASSWORD`) precisam ser preenchidos.
`DATABASE_URL=${{Postgres.DATABASE_URL}}` referencia o plugin
PostgreSQL; troque `Postgres` pelo nome do serviço de banco se for
outro. **Nunca** coloque valores reais no arquivo do repositório.

### Roteiro de deploy

1. Backup do Postgres (seção abaixo).
2. Merge/push na branch que o Railway observa.
3. Acompanhar *Deployments → View logs*. Procurar:
   - erros de migração (`alembic`), `RuntimeError: Configuração
     insegura`, `ADMIN_PASSWORD recusada`;
   - a linha final `Application startup complete`.
4. Abrir `/health` (deve responder `ok`) e fazer login.
5. Se algo falhar, ver [Troubleshooting](#troubleshooting).

O healthcheck `/health` faz `SELECT 1` no banco: responde `ok` (200)
ou `banco indisponível` (503). O Railway só promove o deploy se der
200. Não há `/health/live` nem `/health/ready`.

---

## Variáveis de ambiente

Fonte: `app/config/__init__.py` (classe `Settings`, lida de variáveis
de ambiente ou do `.env`; nomes **sem** distinção de maiúsculas). Valores
padrão são os do código.

### Banco e inicialização

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite:///app.db` | URL do banco. `postgres://` e `postgresql://` são convertidas para `postgresql+psycopg://` (psycopg 3). Em produção (`DEBUG=false`) SQLite é **recusado** |
| `RUN_MIGRATIONS` | `true` | Aplica as migrações do Alembic ao subir. Com `false`, usa `create_all` + `ensure_columns` (só para dev/testes rápidos) |
| `DEBUG` | `false` | `true` desliga a validação de segredos, o HSTS e o cookie `Secure`. **Nunca em produção** |
| `ADMIN_USERNAME` | `admin` | Usuário do administrador criado na primeira subida |
| `ADMIN_PASSWORD` | vazio | Senha desse administrador; só vale se não existir nenhum usuário. Com `DEBUG=false`: mínimo 12 caracteres e não-fraca, senão o app não sobe. Vazio e `DEBUG=true`: usa `admin` |

### Segurança

| Variável | Padrão | Descrição |
|---|---|---|
| `SECRET_KEY` | vazio | Assina a sessão e o selo da auditoria. Em produção, mínimo 32 caracteres e fora da lista de valores fracos (`changeme`, `secret`, `trocar`, `troque-em-producao`, `test-secret`) |
| `DOCUMENT_ENCRYPTION_KEY` | vazio | Chave(s) Fernet que cifram foto/PDF e o segredo do 2FA. Várias chaves separadas por vírgula = rotação (a primeira cifra, todas decifram). Obrigatória em produção |
| `PSEUDONYM_KEY` | vazio | Chave do HMAC que pseudonimiza o usuário digitado em login falho e entra no selo da auditoria. Vazio: usa `SECRET_KEY` |
| `TRUSTED_PROXY_COUNT` | `1` | Quantos proxies existem na frente do app (Railway = 1). O IP real é a N-ésima entrada a partir do fim de `X-Forwarded-For` |
| `MAX_LOGIN_ATTEMPTS` | `5` | Falhas seguidas até bloquear a conta |
| `LOGIN_BLOCK_MINUTES` | `15` | Duração do bloqueio |
| `TEMP_MAX_LOGIN_ATTEMPTS` | `3` | Limite de falhas para contas ainda com senha provisória |
| `TEMP_PASSWORD_HOURS` | `48` | Validade da senha provisória (4 dígitos) |
| `SESSION_IDLE_MINUTES` | `60` | Expira a sessão por inatividade |
| `SESSION_MAX_HOURS` | `12` | Duração máxima da sessão (também é o `max_age` do cookie) |
| `MIN_PASSWORD_LENGTH` | `8` | Tamanho mínimo da senha pessoal |
| `REQUIRE_ADMIN_2FA` | `false` | `true` obriga todo administrador a configurar o 2FA antes de usar o sistema |
| `RATE_LIMIT_ENABLED` | `true` | Liga o limite de requisições em memória |
| `CSRF_ALLOWED_ORIGINS` | vazio | Origens extras aceitas em POST (CSV). Normalmente vazio |

### Gemini e importação

| Variável | Padrão | Descrição |
|---|---|---|
| `GEMINI_API_KEY` | vazio | Chave da API. Sem ela, importar conta falha com mensagem clara |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Modelo usado. Nomes da lista de descontinuados (`gemini-2.0-flash-exp`, `gemini-2.5-flash-lite`, `gemini-2.5-flash`, `gemini-1.0-pro`, `gemini-pro`, `gemini-pro-vision`) são trocados pelo padrão, com aviso no log |
| `EXTRACTION_PROVIDER` | `gemini` | `gemini` ou `mock` (o mock devolve sempre `tests/fixtures/cemig_set_2026.json`) |
| `GEMINI_MAX_CONCURRENCY` | `2` | Chamadas simultâneas ao Gemini (a cota gratuita é ~15 pedidos/min) |
| `MAX_UPLOAD_MB` | `12` | Tamanho máximo do arquivo enviado |
| `STALE_IMPORT_MINUTES` | `10` | Importação "processando" parada há mais que isso vira falha com botão "Tentar novamente" |

### Retenção

| Variável | Padrão | Descrição |
|---|---|---|
| `DOCUMENT_RETENTION_DAYS` | `183` | Prazo (~6 meses) para apagar a foto/PDF original do banco |
| `RETENTION_CHECK_HOURS` | `6` | Intervalo da rotina automática de retenção |

Variáveis que **não existem** neste sistema (existem no Notas-despesas):
`ENVIRONMENT`, `MASTER_ENCRYPTION_KEY`, `R2_*`, `SMTP_*`,
`RESEND_API_KEY`. Não há envio de e-mail nem armazenamento externo: os
arquivos ficam cifrados no próprio banco.

Variáveis desconhecidas no ambiente são ignoradas (`extra="ignore"`):
um erro de digitação **não gera aviso**. Confira o nome com a tabela.

### Conjunto mínimo em produção

`DEBUG=false`, `SECRET_KEY`, `DOCUMENT_ENCRYPTION_KEY`, `DATABASE_URL`
(PostgreSQL), `ADMIN_PASSWORD`, `GEMINI_API_KEY`. Recomendados:
`TRUSTED_PROXY_COUNT=1`, `REQUIRE_ADMIN_2FA=true`.

Geração das chaves:

```bash
# SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
# DOCUMENT_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

(O `railway.env.example` sugere para a chave de documentos
`base64.urlsafe_b64encode(os.urandom(32))`, que gera uma chave Fernet
válida do mesmo formato.)

---

## Migrações automáticas na subida

Com `RUN_MIGRATIONS=true`, a função `lifespan` (`app/main.py`) chama
`db_migrate.upgrade()` antes de aceitar requisições:

- **Banco novo/vazio**: `alembic upgrade head` cria tudo.
- **Banco anterior ao Alembic** (tem `users`, não tem
  `alembic_version`): o sistema completa tabelas/colunas que faltem
  (`create_all` + `ensure_columns`), carimba `head` se o esquema já
  bate com os modelos (ou `0001` se não bate) e aplica o resto. Os
  dados não são tocados.
- **Banco já versionado**: aplica só as revisões pendentes.

Revisões atuais em `migrations/versions/`: `0001_baseline`,
`0002_alert_acks`, `0003_manual_accounting_date` (vazia, ver abaixo).

Para alterar o esquema:

1. Mude o modelo em `app/models/`.
2. `alembic revision --autogenerate -m "o que mudou"`
   (a URL vem de `DATABASE_URL`; `alembic.ini` não a guarda).
3. **Leia o arquivo gerado** em `migrations/versions/` e faça commit
   junto com a mudança do modelo.
4. `tests/test_migrations.py` falha se um modelo mudar sem migração
   (`db_migrate.drift()` deve voltar vazio).

Conferir divergência entre modelos e banco real (por exemplo, depois de
restaurar um backup):

```bash
python -c "from app import db_migrate; print(db_migrate.drift())"
```

Lista vazia = banco em dia.

### Incidente de 2026-10-10 — revisão 0003

**O que aconteceu.** Em 2026-10-10 a produção não subiu. O log
terminava em:

```
Can't locate revision identified by '0003'
```

**Causa.** A migração 0003 (coluna `manual_records.accounting_date`)
tinha sido aplicada no banco de produção: a tabela `alembic_version`
guardava `0003`. A funcionalidade foi abandonada e o arquivo da
migração foi removido do repositório. Na subida seguinte, o Alembic
leu `0003` no banco, não achou a revisão nos arquivos e abortou; como a
migração roda no `lifespan`, o app não terminou de iniciar.

**Correção.** Manter `migrations/versions/0003_manual_accounting_date.py`
como migração **vazia** (`upgrade` e `downgrade` fazem `pass`), ainda
na cadeia `0002 -> 0003`. A coluna que ficou nos bancos que a tinham é
nula e o sistema não a usa. Bancos que nunca aplicaram a 0003 passam
por ela sem efeito.

**Regra.** Nunca apague uma revisão já aplicada em produção. Para
desfazer uma funcionalidade, crie uma migração nova que a reverta ou
mantenha a antiga vazia. O teste
`test_revisions_already_applied_in_production_stay_in_the_chain`
garante que `0001`, `0002` e `0003` continuam na cadeia.

**Prevenção.** Antes de cada deploy, backup do banco e leitura do log
de inicialização (esperado: `Application startup complete`).

---

## Backup e restauração (PostgreSQL)

1. Ative os backups automáticos do banco no Railway (serviço
   PostgreSQL). Configurar isso é por conta do administrador; o
   Railway não faz por padrão.
2. Backup manual, antes de cada deploy:
   ```bash
   pg_dump "$DATABASE_URL" -Fc -f economart-AAAA-MM-DD.dump
   ```
   (`$DATABASE_URL` aqui é a URL do Postgres no formato aceito pelo
   `pg_dump`, `postgresql://...`.)
3. Restauração — **num banco de teste primeiro**:
   ```bash
   pg_restore --clean --no-owner -d "$DATABASE_URL_TESTE" economart-AAAA-MM-DD.dump
   ```
4. Depois de restaurar, rode `db_migrate.drift()` (acima) e suba o
   app apontando para esse banco para validar o log.
5. **Teste a restauração a cada trimestre.** Backup que nunca foi
   restaurado não é backup. Esta rotina não é automatizada nem coberta
   por teste.
6. Fotos/PDFs das contas ficam **cifrados dentro do banco**: o dump os
   leva junto, mas só abrem com a `DOCUMENT_ENCRYPTION_KEY`. Guarde a
   chave num cofre de senhas, **separada** do backup. O segredo do 2FA
   também é cifrado com essa chave.

---

## Troca de chaves

### `DOCUMENT_ENCRYPTION_KEY` (rotação sem perder arquivos)

1. Gere uma chave nova (comando acima).
2. Defina a variável como `nova,antiga` (a primeira cifra, todas
   decifram) e reinicie.
3. Documentos gravados antes continuam abrindo. Os arquivos antigos
   **não são recifrados** automaticamente: não há script para isso.
   Só remova a chave antiga quando não houver mais documento cifrado
   com ela (na prática, depois do prazo de retenção de 183 dias).
4. Perder a chave deixa os arquivos ilegíveis; os dados lidos das contas
   (valores, consumo) não dependem dela. Um segredo de 2FA cifrado com
   a chave perdida também deixa de abrir: nesse caso use `reset_2fa`.

### `SECRET_KEY`

Ela assina a sessão **e** o selo (HMAC encadeado) da auditoria. Trocar:

- derruba todas as sessões abertas;
- invalida a verificação dos eventos de auditoria antigos (a chave nova
  não valida os selos antigos). A chave do selo é `PSEUDONYM_KEY` se
  estiver definida, senão `SECRET_KEY` (`audit_service.py`): com
  `PSEUDONYM_KEY` fixa, trocar a `SECRET_KEY` não afeta o selo, mas
  trocar a `PSEUDONYM_KEY` afeta.

Antes de trocar: *Auditoria → Baixar CSV* e *Verificar integridade* e
guarde os dois resultados.

---

## Reset de 2FA

O 2FA vale só para administradores (TOTP, 8 códigos de recuperação de
uso único). Se um administrador perde o celular:

1. Usar um **código de recuperação** no login.
2. Ou outro administrador abre *Usuários* e clica em *Redefinir 2FA*
   (rota `/admin/users/{id}/reset-2fa`; não funciona sobre si mesmo).
3. Se for o **único** administrador, no servidor:
   ```bash
   python -m scripts.reset_2fa <usuario>
   ```
   Roda com o mesmo `DATABASE_URL` do app (no Railway, via
   `railway run` ou shell do serviço; o acesso ao servidor/banco é o que
   impede que isso seja uma brecha remota). O script remove segredo e
   códigos, soma 1 à época de sessão (encerra as sessões do usuário) e
   grava o evento `2fa_reset` (`by: script`) na auditoria. Usuário
   inexistente: imprime "Usuário '...' não encontrado." e sai com
   código 1.

Depois, o administrador configura o 2FA de novo em `/account/2fa`.

---

## Retenção de documentos

A foto/PDF original é removida do banco após `DOCUMENT_RETENTION_DAYS`
(183). Os dados lidos, valores e gráficos permanecem; a tela mostra
"Original expirado" e o registro em `documents` guarda nome, hash e
`purged_at`.

- Automática: roda na subida e a cada `RETENTION_CHECK_HOURS` (6 h)
  numa tarefa em segundo plano. Falhas são logadas e não derrubam o app.
- Manual:
  ```bash
  python -m scripts.purge_documents
  ```
  Imprime `N documento(s) removido(s).` e grava o evento `purge` na
  auditoria (`count`, `retention_days`).
- Arquivo que **não é conta de energia** (rejeitado na importação) não
  espera a retenção: os bytes são apagados na hora e só ficam nome e
  motivo na auditoria (`import_rejected`).

---

## Auditoria

- *Verificar integridade* (`/admin/audit`) aponta edição, remoção no
  meio ou inserção feita direto no banco.
- Anote o **selo final** de vez em quando: apagar só os últimos eventos
  não quebra a cadeia, e só essa cópia revela.
- *Baixar CSV* exporta até 20 mil eventos recentes.

---

## Troubleshooting

| Sintoma | Causa provável / o que fazer |
|---|---|
| Log: `Can't locate revision identified by '0003'` (ou outra revisão) | Uma migração já aplicada foi removida do repositório. Restaure o arquivo (vazio, se a funcionalidade foi abandonada). Ver [incidente](#incidente-de-2026-10-10--revisão-0003) |
| `RuntimeError: Configuração insegura — o servidor não inicia...` | `SECRET_KEY` curta/fraca, `DOCUMENT_ENCRYPTION_KEY` ausente ou inválida, ou `DATABASE_URL` em SQLite. O texto lista cada problema |
| `ADMIN_PASSWORD recusada: ...` | Banco sem usuários e senha com menos de 12 caracteres ou fraca. Defina outra no Railway |
| Log avisa "Nenhum usuário existe e ADMIN_PASSWORD não foi definido" | Defina `ADMIN_PASSWORD` e reinicie |
| Deploy "falha" no healthcheck | `/health` devolveu 503 (banco fora) ou o app nem subiu. Leia o log desde o início |
| Sessões caem a cada reinício | `SECRET_KEY` vazio (só possível com `DEBUG=true`) |
| Importar conta falha: chave inválida/modelo não encontrado | 401/403: revisar `GEMINI_API_KEY`. 404: revisar `GEMINI_MODEL` |
| "Limite de uso do Gemini atingido" | 429 do Google. Aguardar ~1 min; reduzir `GEMINI_MAX_CONCURRENCY` se recorrente |
| Gemini fora do ar | Após 5 falhas seguidas o disjuntor abre e rejeita na hora por 30 s, depois testa uma chamada. Enquanto isso, use *Lançamento manual* |
| Importação presa em "processando" | Passados `STALE_IMPORT_MINUTES` (10) vira falha com "Tentar novamente" |
| "Muitas tentativas" (429) | Limite por IP e por processo (ex.: 10 logins/min). Todos os usuários aparecendo com o mesmo IP indica `TRUSTED_PROXY_COUNT` errado |
| Usuário bloqueado por tentativas erradas | *Usuários → Desbloquear* (ou esperar `LOGIN_BLOCK_MINUTES`) |
| Esqueceu a senha | *Usuários → Redefinir senha* (provisória de 4 dígitos, 48 h) |
| Administrador perdeu o celular do 2FA | Ver [Reset de 2FA](#reset-de-2fa) |
| Suspeita de acesso indevido | *Auditoria*: filtrar "Senha incorreta" e "Conta bloqueada"; redefinir as senhas envolvidas; *Verificar integridade* |
| Arquivo estranho enviado | É barrado e apagado (auditoria: "Arquivo barrado") |
| Documento não abre: "Não foi possível decifrar o documento" | A chave atual não é a que cifrou o arquivo. Restaure a chave antiga como segunda da lista |

---

## Rotina

| Quando | Tarefa |
|---|---|
| A cada deploy | Backup + ler o log de inicialização (`Application startup complete`) |
| Mensal | Conferir a auditoria e os usuários ativos; desativar quem saiu |
| Trimestral | Testar a restauração do backup; revisar `pip-audit` (roda no CI, sem bloquear) |
| Anual | Rotacionar `DOCUMENT_ENCRYPTION_KEY` e as senhas de administrador |

## Limites conhecidos

- Limite de requisições e disjuntor do Gemini em memória, por processo:
  valem para **1 instância** (padrão do Railway com este
  `railway.json`). Com várias instâncias seria preciso Redis.
- 2FA só para administradores.
- O disco do Railway é efêmero: por isso o SQLite é recusado em
  produção.
- Não há envio de e-mail: recuperação de senha é feita pelo
  administrador.
