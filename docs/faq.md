# Perguntas técnicas frequentes

Respostas curtas, baseadas no código. Para o passo a passo, ver
[getting-started.md](getting-started.md) (instalação),
[operations.md](operations.md) (deploy e incidentes) e
[testing.md](testing.md) (testes).

---

## Setup

### Qual versão do Python?

3.12 (`.python-version` e CI). Em uma execução local com 3.13 a suíte
passou, mas o alvo oficial é 3.12.

### Preciso instalar Postgres para desenvolver?

Não. Sem `DATABASE_URL`, o sistema usa SQLite em `app.db`, no diretório
onde o processo é iniciado.

### O servidor não sobe: "Configuração insegura — o servidor não inicia em produção sem corrigir"

Com `DEBUG=false`, `app/startup_checks.py` exige `SECRET_KEY` com 32+
caracteres (e fora de `changeme`, `secret`, `trocar`,
`troque-em-producao`, `test-secret`), `DOCUMENT_ENCRYPTION_KEY` com
chave(s) Fernet válida(s) e `DATABASE_URL` que não seja SQLite. A
mensagem lista o que falta. Localmente, `DEBUG=true` no `.env`.

### Como gerar `SECRET_KEY` e `DOCUMENT_ENCRYPTION_KEY`?

```bash
python -c "import secrets; print(secrets.token_hex(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

A primeira gera 64 caracteres hexadecimais (o mínimo aceito é 32). A
segunda gera uma chave Fernet (44 caracteres, base64). Guarde a de
documentos num cofre: sem ela, os arquivos já gravados não abrem.

### Qual é a senha do admin?

A de `ADMIN_PASSWORD`, no primeiro boot com a tabela de usuários vazia.
Com `DEBUG=true` e variável vazia, é `admin`. Mudar a variável depois
não altera um admin já criado. Ver
[getting-started.md](getting-started.md#5-primeiro-login).

### Como testar a importação sem gastar cota do Gemini?

`EXTRACTION_PROVIDER=mock`. Toda importação "lê" o conteúdo de
`tests/fixtures/cemig_set_2026.json`, qualquer que seja o arquivo
enviado.

### Como carrego dados de demonstração?

`python -m scripts.seed_demo` (loja CD300, valores reais da planilha) e,
depois, `python -m scripts.seed_demo_company` (lojas `DEMO-01..08`,
fictícias, para o painel da diretoria). Nunca em produção. Ver
[getting-started.md](getting-started.md#dados-de-demonstração).

### Por que `python scripts/seed_demo.py` dá erro de import?

Os scripts importam `app`. Rode como módulo, da raiz:
`python -m scripts.seed_demo`.

---

## Migrações

### O deploy falhou com `Can't locate revision identified by '0003'`

Uma revisão já registrada em `alembic_version` não está mais nos
arquivos. Foi o incidente de 2026-10-10: a 0003 tinha sido aplicada em
produção e depois removida do repositório. A correção é manter o
arquivo como migração vazia
(`migrations/versions/0003_manual_accounting_date.py`). Nunca apague
uma revisão já aplicada em produção. Detalhes em
[operations.md](operations.md#incidente-de-2026-10-10--revisão-0003).

### Como crio uma migração?

Altere o modelo em `app/models/`, rode `alembic revision
--autogenerate -m "descrição"`, **leia** o arquivo gerado e faça commit
com a mudança do modelo. O teste `tests/test_migrations.py` quebra se o
modelo divergir das migrações.

### As migrações rodam sozinhas?

Sim, na subida, se `RUN_MIGRATIONS=true` (padrão). Com `false`, o app
usa `create_all` e `ensure_columns`, o que serve só para dev e testes
rápidos.

### Como confiro se o banco bate com os modelos?

```bash
python -c "from app import db_migrate; print(db_migrate.drift())"
```

Lista vazia = em dia. Útil depois de restaurar um backup.

### Meu banco é antigo (antes do Alembic). Preciso fazer algo?

Não. Sem `alembic_version` e com a tabela `users`, a subida completa
colunas/tabelas faltantes, carimba a revisão e segue. Cobertura em
`test_migrations.py`.

---

## Login, 2FA e bloqueio

### Usuário bloqueado: o que fazer?

Bloqueio vem de `MAX_LOGIN_ATTEMPTS` (5) falhas seguidas, por
`LOGIN_BLOCK_MINUTES` (15). Contas com senha provisória bloqueiam na
3ª falha (`TEMP_MAX_LOGIN_ATTEMPTS`). O administrador libera em
*Usuários → Desbloquear*; ou se espera o prazo. Vale também para
usuário inexistente (a mensagem não revela se a conta existe).

### Recebo 429 "Muitas tentativas" ao entrar

Limite por IP, em memória: 10 logins/min, 10 códigos de 2FA/min, 20
uploads/min etc. (`app/middleware.py`). Se **todos** os usuários
aparecem com o mesmo IP, confira `TRUSTED_PROXY_COUNT` (Railway = 1).

### Esqueci a senha. Não há "esqueci minha senha"?

Não há recuperação por e-mail (o sistema não envia e-mail). O
administrador usa *Usuários → Redefinir senha*, que gera uma senha
provisória de 4 dígitos, válida por 48 h (`TEMP_PASSWORD_HOURS`) e que
só permite trocar a senha. Se o esquecido for o único admin, **não há
script de reset de senha**: seria preciso intervenção direta no banco
(não documentada aqui).

### Perdi o celular do 2FA

Em ordem: (1) usar um dos 8 códigos de recuperação; (2) outro
administrador clica em *Redefinir 2FA* no seu usuário; (3) se for o
único administrador, no servidor:
`python -m scripts.reset_2fa <usuario>`. Depois, configure de novo em
`/account/2fa`. Ver [operations.md](operations.md#reset-de-2fa).

### Quem precisa de 2FA?

Só administradores. É opcional, a menos que `REQUIRE_ADMIN_2FA=true`;
nesse caso o admin sem 2FA é redirecionado para `/account/2fa` e não
usa o sistema antes de configurar.

### Por que o código do autenticador é recusado?

O código tem tolerância de ±30 s e **vale uma vez** (anti-replay).
Verifique a hora do celular. Erros repetidos contam para o bloqueio da
conta.

### Por que fui deslogado?

Sessão expira por 60 min de inatividade (`SESSION_IDLE_MINUTES`) ou 12 h
no total (`SESSION_MAX_HOURS`). Também cai quando a senha é trocada, o
perfil muda, o usuário é desativado ou o 2FA é ativado/removido, e em
toda subida sem `SECRET_KEY` fixa (só com `DEBUG=true`).

---

## Importação e documentos

### "O arquivo não foi reconhecido como conta de energia"

O arquivo foi **barrado** (`import_rejected` na auditoria): ou o Gemini
classificou como "não é conta" (`is_energy_bill=false`), ou nenhum campo
identificador foi lido (UC, valor, mês, nota, vencimento) e não há
itens. Nada é lançado e os bytes são apagados na hora; só ficam nome e
motivo. Reenvie uma foto/PDF legível da conta.

### Outros motivos de recusa no upload

- Formato fora de JPG, PNG, WEBP e PDF, ou conteúdo (magic bytes) que
  não bate com a extensão.
- Tamanho acima de `MAX_UPLOAD_MB` (12 MB).
- PDF com mais de 10 páginas.
- O **mesmo arquivo** (mesmo hash) de uma conta já salva é recusado
  antes de chamar o Gemini.

### Mensagens de erro do Gemini

| Mensagem | Causa |
|---|---|
| "A chave do Gemini (GEMINI_API_KEY) não está configurada" | Variável vazia |
| "A chave da API do Gemini é inválida ou foi revogada" | 401/403 |
| "O modelo do Gemini configurado (GEMINI_MODEL) não foi encontrado" | 404: nome do modelo errado |
| "Limite de uso do Gemini atingido" | 429; há 3 tentativas automáticas em 429/5xx antes de falhar |
| "O serviço do Google está indisponível" | 5xx ou rede; após 5 falhas seguidas, disjuntor aberto por 30 s |

### Como troco o modelo do Gemini?

Defina `GEMINI_MODEL` (padrão `gemini-3.5-flash-lite`) e reinicie. Se o
valor estiver em `OBSOLETE_MODELS` (`gemini-2.0-flash-exp`,
`gemini-2.5-flash-lite`, `gemini-2.5-flash`, `gemini-1.0-pro`,
`gemini-pro`, `gemini-pro-vision`), o sistema usa o padrão e avisa no
log. Se o nome não existir, o erro é o 404 acima. **Não verificado**:
quais modelos a API aceita hoje; isso depende do Google. A importação
guarda o modelo usado (`gemini:<modelo>`) no registro.

### A importação ficou em "processando"

Depois de `STALE_IMPORT_MINUTES` (10) vira falha com o botão "Tentar
novamente" (`/import/{id}/retry`). Pode acontecer se o processo
reiniciou no meio.

### O original da conta sumiu ("Original expirado", HTTP 410)

Retenção: foto/PDF são apagados após `DOCUMENT_RETENTION_DAYS` (183).
Os dados lidos e os gráficos permanecem. A rotina roda na subida e a
cada 6 h; manualmente: `python -m scripts.purge_documents`. Não há como
recuperar o arquivo, só de um backup anterior à remoção.

### "Não foi possível decifrar o documento"

A `DOCUMENT_ENCRYPTION_KEY` atual não é a que cifrou o arquivo. Coloque
a chave antiga como segunda da lista (`nova,antiga`). Se a chave foi
perdida, o arquivo está perdido; os dados lidos não.

---

## Lançamentos e relatórios

### Por que o mês do lançamento manual vale pela referência?

Decisão registrada em `DECISIONS.md` §2. Despesas sem conta de
distribuidora (gerador, manutenção, LL Energia) são lançadas com o
mês de referência escolhido pelo usuário, e esse mês vale em todas as
tabelas e painéis, inclusive no modo "por vencimento". O campo
"Vencimento" do lançamento manual é só informativo. Em 2026-10-10 houve
uma tentativa de usar uma "data de contabilização" (migração 0003); foi
abandonada, e a 0003 ficou vazia.

### O relatório da loja não bate com o que eu somei

O relatório tem três agrupamentos (`by`): *Como na planilha* (padrão),
*Mês de referência* e *Mês de vencimento*. No padrão, o **resumo** soma
pelo mês de **vencimento** e a tabela/gráfico **por conta** mostra o mês
de **referência**; por isso a conta da CEMIG que vence em jan/2026 (ref.
dez/2025) aparece em colunas diferentes nas duas áreas. Confira o
agrupamento no cabeçalho da folha ("Agrupado por"). Outros pontos:

- Contas sem `due_date` entram pela referência nos modos por vencimento.
- Lançamento manual sempre vale pela referência (pergunta anterior).
- No painel da diretoria, o mês em que poucas lojas já lançaram é
  marcado com `*` e fica fora das variações.
- Filtros de período, tipo e fornecedor mudam o total.

Os totais da planilha da CD300 são conferidos ao centavo em
`tests/test_report_sheet.py`.

### Duplicata: "substituir" ou "salvar como novo"?

Há duplicata quando a mesma unidade tem conta no mesmo mês de referência
ou com a mesma nota; para lançamento manual, mesma loja/tipo/mês. O
sistema exige a decisão: *substituir* edita o registro existente,
*novo* cria outro.

### O lançamento "LL Energia" não aparece no formulário individual

Tipos marcados como "somente lote" são lançados em
`/manual/lote` (um valor para várias lojas). Registros antigos ainda
podem ser corrigidos um a um.

### Como exporto os dados?

Contas: *Contas → Baixar planilha (CSV)* (`/notas/export.csv`, respeita
os filtros; campos que começam com `=`, `+`, `-`, `@` são
neutralizados). Auditoria: *Baixar CSV* (até 20 mil eventos, só admin).

### Os avisos de vencimento aparecem para quem?

Só para o perfil **funcionário**. Um ponto sem dia de vencimento
cadastrado não gera aviso. "Hoje" é o dia de America/Sao_Paulo, não o
do servidor.

---

## Operação

### Por que o sistema só funciona com uma instância?

Limite de requisições e disjuntor do Gemini são em memória, por
processo. O `railway.json` sobe um único `uvicorn`.

### Posso trocar a `SECRET_KEY`?

Pode, mas derruba as sessões e invalida a verificação dos selos antigos
da auditoria. Exporte o CSV da auditoria e anote o resultado de
*Verificar integridade* antes. Ver
[operations.md](operations.md#troca-de-chaves).

### O que verificar em todo deploy?

Backup do Postgres antes; depois, o log de inicialização precisa
terminar com `Application startup complete`, e `/health` deve responder
`ok`.

### Onde estão as variáveis de ambiente?

Tabela completa em
[operations.md](operations.md#variáveis-de-ambiente). Variáveis
`ENVIRONMENT`, `MASTER_ENCRYPTION_KEY`, `R2_*`, `SMTP_*` e
`RESEND_API_KEY` **não existem** neste sistema.

### Os testes demoram. É normal?

Cerca de 2 minutos, em SQLite, pelo hash de senha real nos testes de
login. Rode um arquivo ou use `-k` durante o desenvolvimento
([testing.md](testing.md#como-rodar)).
