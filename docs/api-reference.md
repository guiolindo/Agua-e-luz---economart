# Referência da API

Todos os endpoints HTTP do sistema, agrupados pelo arquivo de rota em `app/routes/`. O sistema é uma aplicação
server-side: quase tudo devolve HTML (Jinja2) e as mutações são formulários `POST` com redirecionamento. Os
endpoints JSON são poucos (seção própria no fim de cada grupo) e existem para o JavaScript da interface.

A documentação interativa do FastAPI está **desativada** (`docs_url`, `redoc_url` e `openapi_url` são `None` em
`app/main.py`): `/docs`, `/redoc` e `/openapi.json` não existem. Esta página é a referência.

## Convenções

- **Autenticação**: cookie de sessão `energia_session` (assinado, `HttpOnly`, `SameSite=Strict`, `Secure` fora do
  `DEBUG`). Não há `Authorization: Bearer`, nem API key, nem token de acesso. Detalhes em
  [`security.md`](security.md).
- **Sem sessão válida**: a exceção `LoginRequired` vira `303` para `/login?next=<caminho>` (só o caminho, sem a
  query string). Isso vale também para `/api/*`: um cliente JSON não recebe `401`, recebe o redirecionamento.
- **Troca de senha obrigatória** (`must_change_password`): qualquer rota autenticada, exceto `/account/password`
  e `/logout`, responde `303` para `/account/password`.
- **2FA obrigatório** (`REQUIRE_ADMIN_2FA=true`): administrador sem 2FA recebe `303` para `/account/2fa` em toda
  rota autenticada, exceto `/account/2fa*`, `/account/password` e `/logout`.
- **CSRF**: toda rota `POST` do sistema declara `dependencies=[Depends(verify_csrf)]` (conferido por busca em
  `app/routes/`: nenhum `POST` fica sem). O token vai no campo de formulário `csrf_token` **ou** no cabeçalho
  `X-CSRF-Token`. Falha: `403` "Sessão expirada ou requisição inválida. Recarregue a página." Antes disso, o
  `CSRFOriginMiddleware` recusa mutações com `Sec-Fetch-Site: cross-site` ou `Origin` diferente do `Host`
  (`403` JSON). Os `GET` não alteram dados de negócio. Escrevem apenas: o evento `export` dos CSV (ver
  [Exportações CSV](#exportações-csv)), o segredo TOTP pendente em `GET /account/2fa` e a expiração de importações
  paradas em `GET /import/{id}` e `/status`.
- **Formato das respostas**:
  - página/ação bem-sucedida de formulário: `303 See Other` + mensagem na sessão (*flash*);
  - erro de validação de formulário: a mesma página renderizada de novo, com `400` (ou `409` para conflito);
  - erro de acesso (`HTTPException`): se o cabeçalho `Accept` contém `text/html`, a página `error.html` com o
    código e a mensagem; caso contrário, texto puro com o `detail`;
  - erro `500`: sempre `error.html`, com mensagem fixa ("Ocorreu um erro inesperado…"), sem detalhe da exceção;
  - respostas das camadas de segurança (`CSRFOriginMiddleware`, `BodySizeLimitMiddleware`,
    `RateLimitMiddleware`): JSON `{"detail": "mensagem"}`.
- **Parâmetros de mês** (`month`, `start`, `end`): formato `AAAA-MM`; valor inválido é ignorado e o padrão é usado
  (`parse_reference`).
- **Datas e valores nos formulários**: aceitam o formato brasileiro (`parse_date`, `parse_decimal`).
- Toda resposta recebe os cabeçalhos de segurança descritos em [`security.md`](security.md); `Cache-Control:
  no-store` em tudo que não é `/static/`.

### Perfis e dependências de acesso

Perfis (`User.role`): `admin`, `operator` (funcionário), `director` (diretoria), `viewer` (consulta). O valor
legado `user` é tratado como `operator`.

| Dependência (`app/security.py`) | Quem passa | Falha |
|---|---|---|
| `current_user` | qualquer perfil com sessão válida e conta ativa | `303` login |
| `writer_required` | `admin`, `operator` (e `user`) | `403` "Seu perfil é somente de consulta." |
| `admin_required` | `admin` | `403` "Apenas administradores podem acessar esta área." |
| `director_required` | `director`, `admin` | `403` "O painel da diretoria é restrito à diretoria e ao administrador." |
| `alerts_required` | `operator` (e `user`); **o administrador não passa** | `403` "Os avisos de vencimento são destinados ao funcionário." |

Nas tabelas abaixo, "Logado" significa `current_user` (qualquer perfil), "Escrita" é `writer_required`.

### Limites de requisições por IP (janela deslizante, em memória)

Aplicados por `RateLimitMiddleware` (`app/middleware.py`); a primeira política que casa com método e caminho vale.
Estouro: `429` JSON `{"detail": "Muitas tentativas. Aguarde um pouco e tente novamente."}` com `Retry-After`
igual ao tamanho da janela em segundos (não ao tempo restante).

| Política | Método e caminho | Limite |
|---|---|---|
| `login` | `POST /login` | 10 / 60 s |
| `login2fa` | `POST /login/2fa` | 10 / 60 s |
| `password` | `POST /account/password` | 10 / 600 s |
| `upload` | `POST /import` | 20 / 60 s |
| `documents` | `GET /documents/*` | 60 / 60 s |
| `api` | `GET /api/*` | 240 / 60 s |
| `mutations` | qualquer `POST`/`PUT`/`PATCH`/`DELETE` restante | 120 / 60 s |

O limite só vale por processo e é desligável com `RATE_LIMIT_ENABLED=false`.

---

## `auth.py` — entrada e saída

| Método | Caminho | Acesso | CSRF |
|---|---|---|---|
| GET | `/login` | público | n/a |
| POST | `/login` | público | sim |
| GET | `/login/2fa` | sessão parcial (`pre2fa`) | n/a |
| POST | `/login/2fa` | sessão parcial (`pre2fa`) | sim |
| POST | `/logout` | qualquer (não exige sessão válida) | sim |

### `GET /login`

Query: `next` (padrão `/`), `saiu` (qualquer valor não vazio mostra "Sessão encerrada."). Resposta `200` HTML. A
página cria a sessão e o token CSRF usados no `POST`. Não redireciona quem já está logado.

### `POST /login`

Form: `username` (até 80 caracteres), `password` (até 256), `next`, `csrf_token`.

- Sucesso sem 2FA: `303` para `next`, desde que comece com `/` e não com `//` nem contenha `\` (senão `/`).
  Se `next` é `/` e o perfil é `director`, vai para `/diretoria`. Se a conta tem `must_change_password`, vai para
  `/account/password`.
- Administrador com 2FA ativo: a sessão **não** nasce ainda. A sessão é limpa, grava-se `pre2fa`
  (`uid`, instante, destino) e responde `303` para `/login/2fa`.
- Falha: `401` com a página de login e o texto "Usuário ou senha incorretos." (credencial errada, usuário
  inexistente e conta inativa são indistinguíveis).
- Bloqueio: `401` com "Acesso bloqueado por excesso de tentativas. Tente de novo em N minuto(s) ou peça ao
  administrador para redefinir a senha." Vale também para usuário inexistente.
- `429` pelo limite por IP.

Regras de bloqueio: 5 falhas bloqueiam por 15 minutos (`MAX_LOGIN_ATTEMPTS`, `LOGIN_BLOCK_MINUTES`); conta com
senha provisória bloqueia na 3ª (`TEMP_MAX_LOGIN_ATTEMPTS`).

### `GET /login/2fa` e `POST /login/2fa`

Exigem a sessão parcial criada no `POST /login`, válida por 300 s (`PRE2FA_SECONDS`). Sem ela (ou expirada,
usuário inativo, sem 2FA): `303` para `/login`.

`POST`: form `code` (até 32 caracteres) com o código TOTP de 6 dígitos **ou** um código de recuperação. Sucesso:
`303` para o destino guardado (e `/diretoria` se aplicável). Código errado ou já usado: `401` com "Código
incorreto ou já usado. Confira o app e tente de novo." Bloqueio de conta: `401` na página de login. Limite
10 / 60 s por IP.

### `POST /logout`

Incrementa a época da sessão do usuário (derruba também cookies copiados), registra `logout` na auditoria, limpa a
sessão e responde `303` para `/login`. O JavaScript (`app.js`) chama este endpoint por `fetch` com
`X-CSRF-Token` e `redirect: 'manual'` antes da animação de despedida.

---

## `account.py` — conta do próprio usuário

| Método | Caminho | Acesso | CSRF |
|---|---|---|---|
| GET | `/account/password` | Logado (inclusive com troca obrigatória) | n/a |
| POST | `/account/password` | Logado | sim |
| GET | `/account/2fa` | Admin | n/a |
| POST | `/account/2fa/enable` | Admin | sim |
| POST | `/account/2fa/disable` | Admin | sim |

### `POST /account/password`

Form: `current_password`, `new_password`, `confirm` (cada um até 256). Validações, nesta ordem: senha atual correta
(senão registra `password_change_failed`), confirmação igual, nova diferente da atual, política de senha
(`validate_password`). Erro: `400` com a página e a mensagem. Sucesso: troca o hash, incrementa a época (as outras
sessões caem), reinicia a sessão atual, `303` para `/` com "Senha alterada." Limite 10 / 600 s por IP.

### `GET /account/2fa`

Página de 2FA. Se o 2FA ainda não está ativo, gera (e grava, cifrado) um segredo pendente na primeira visita e
mostra o QR code (SVG inline) e o segredo em grupos de 4 caracteres.

### `POST /account/2fa/enable`

Form: `code`. Código correto: ativa, gera 8 códigos de recuperação **exibidos uma única vez** na resposta
(`200`), revoga as outras sessões do administrador e reinicia a atual. Código errado: `400`, registra
`2fa_setup_failed`.

### `POST /account/2fa/disable`

Form: `password` e `code` (código TOTP ou de recuperação). Sucesso: remove segredo e códigos, reinicia a sessão,
`303` para `/account/2fa`. Falha: `400` "Senha ou código incorretos.", registra `2fa_disable_failed`.

---

## `admin.py` — usuários e auditoria

Todas as rotas exigem **Admin**. Todo `POST` exige CSRF.

| Método | Caminho | Parâmetros | Resposta |
|---|---|---|---|
| GET | `/admin/users` | n/a | `200` lista de usuários, bloqueios e perfis |
| POST | `/admin/users` | form `username` (até 80, mín. 3), `role` | `200` com a senha provisória (uma vez); `303` com *flash* de erro |
| POST | `/admin/users/{user_id}/reset-password` | n/a | `200` com nova senha provisória; `303` se não existe |
| POST | `/admin/users/{user_id}/unlock` | n/a | `303` `/admin/users` |
| POST | `/admin/users/{user_id}/role` | form `role` | `303` `/admin/users` |
| POST | `/admin/users/{user_id}/toggle` | n/a | `303` `/admin/users` |
| POST | `/admin/users/{user_id}/reset-2fa` | n/a | `303` `/admin/users` |
| POST | `/admin/audit/verify` | n/a | `200` página de auditoria com o relatório de integridade |
| GET | `/admin/audit` | query `action` (filtro) | `200`, últimos 300 eventos |
| GET | `/admin/audit/export.csv` | query `action` | `200` CSV, até 20 mil eventos |

Detalhes:

- **Criar usuário**: `role` fora de `admin|operator|director|viewer` vira `operator`. Nome repetido ou com menos
  de 3 caracteres: `303` com mensagem. A senha provisória (4 dígitos) aparece **só na resposta `200`**, nunca em
  cookie ou *flash*. O usuário nasce com `must_change_password` e validade `TEMP_PASSWORD_HOURS` (48 h).
- **Redefinir senha**: nova senha provisória; revoga as sessões e desbloqueia a conta.
- **Desbloquear**: zera tentativas e bloqueio; não mexe na senha nem nas sessões.
- **Perfil**: rebaixar o último administrador ativo é recusado com *flash* "É preciso manter pelo menos um
  administrador ativo." Mudar o perfil revoga as sessões do usuário.
- **Ativar/desativar** (`toggle`): não age sobre o próprio usuário; não desativa o último administrador ativo;
  desativar revoga as sessões.
- **Redefinir 2FA**: só para **outro** administrador que tenha 2FA ativo; remove o 2FA e encerra as sessões dele.
- **Verificar integridade**: percorre a cadeia de selos (ver [`security.md`](security.md)), registra
  `audit_verified` e mostra "Auditoria íntegra" com o selo final, ou o primeiro evento adulterado.
- Rotas de usuário e de auditoria com `user_id` inexistente não devolvem `404`: redirecionam ou ignoram.

---

## `dashboard.py` — painel inicial

| Método | Caminho | Acesso | Parâmetros | Resposta |
|---|---|---|---|---|
| GET | `/` | Logado | query `month` (`AAAA-MM`) | `200` painel; `303` para `/diretoria` se o perfil é `director` |

---

## `director.py` — painel da diretoria

Acesso: **Diretoria** (`director`, `admin`).

| Método | Caminho | Parâmetros | Resposta |
|---|---|---|---|
| GET | `/diretoria` | `start`, `end` (`AAAA-MM`), `by` (`reference` ou `due`; outro valor vira `reference`), `region`, `types` (repetível, ids inteiros) | `200` painel com KPIs, destaques e gráficos |
| GET | `/diretoria/export.xlsx` | os mesmos filtros | `200` planilha XLSX formatada (abas Resumo, Lojas, Mês a mês, Fornecedores, Pendências) |
| GET | `/diretoria/export.csv` | os mesmos filtros | `200` CSV do comparativo entre lojas |

Os dados dos gráficos vão embutidos na página em `<script type="application/json" id="dir-data">`.

---

## `stores.py` — lojas, unidades e folha de impressão

| Método | Caminho | Acesso | CSRF |
|---|---|---|---|
| GET | `/stores` | Logado | n/a |
| GET | `/stores/new` | Escrita | n/a |
| POST | `/stores` | Escrita | sim |
| GET | `/stores/{store_id}` | Logado | n/a |
| GET | `/stores/{store_id}/settings` | Escrita | n/a |
| POST | `/stores/{store_id}/edit` | Escrita | sim |
| POST | `/stores/{store_id}/units` | Escrita | sim |
| GET | `/stores/{store_id}/report` | Logado | n/a |
| GET | `/units/{unit_id}` | Logado | n/a |
| GET | `/units/{unit_id}/edit` | Escrita | n/a |
| POST | `/units/{unit_id}/edit` | Escrita | sim |

- **`POST /stores`**: form `code` (obrigatório, vira maiúsculas), `name`, `location`, `aliases` (separados por `,`
  ou `;`, até 20), `notes`, `region` (até 20, maiúsculas). Código vazio: `303` para `/stores/new` com erro.
  Código já existente: `409` com o formulário. Sucesso: `303` para `/stores/{id}/settings`.
- **`GET /stores/{store_id}`**: histórico da loja. Query: `type_id`, `indicator`, `view` (`units` ou `types`),
  `start`, `end`, `highlight` (id de unidade), `unit_id`, `by` (`reference` ou `due`). `404` se a loja não existe. A
  ficha executiva (`profile`) só é montada para `director` e `admin`.
- **`POST /stores/{store_id}/edit`**: form `name`, `location`, `aliases`, `notes`, `region`, `active` (caixa de
  seleção: qualquer valor não vazio é verdadeiro). `303` para `/stores/{id}/settings`.
- **`POST /stores/{store_id}/units`**: form `number` (obrigatório), `description`, `internal_code`,
  `record_type_id`, `due_day` (1 a 31). Dia inválido ou unidade já cadastrada: `303` de volta com *flash* de erro.
- **`GET /stores/{store_id}/report`**: folha de impressão da loja. Query: `start`, `end`, `by` (`sheet`, `due`
  ou `reference`; padrão `sheet`), `type_id`, `all` (`0`/`1`, "um por folha").
- **`POST /units/{unit_id}/edit`**: form `number`, `description`, `internal_code`, `notes`, `record_type_id`,
  `active`, `store_id`, `due_day`. Campo `due_day` **ausente** não altera o vencimento; **vazio** o remove.
  Número normalizado já usado por outra unidade ou dia inválido: `303` de volta para `/units/{id}/edit`. Sucesso:
  `303` para `/units/{id}`. `404` se a unidade não existe.

---

## `bills.py` — lista única de contas

| Método | Caminho | Acesso | Parâmetros | Resposta |
|---|---|---|---|---|
| GET | `/notas` | Logado | `store_id`, `type_id`, `start`, `end` (`AAAA-MM`), `q`, `origin` (`bill`, `manual` ou vazio) | `200`, até 500 linhas (o total real é informado) |
| GET | `/notas/export.xlsx` (planilha formatada) e `/notas/export.csv` | Logado | os mesmos filtros | `200` CSV |

A busca `q` casa código da loja, número da unidade (com ou sem pontuação), tipo, nota fiscal e referência
(`MM/AAAA` ou `AAAA`). A lista mescla contas lidas (`EnergyBill`) e lançamentos manuais (`ManualRecord`).

---

## `imports.py` — leitura de conta por foto/PDF

Acesso: **Escrita**. Todo `POST` exige CSRF.

| Método | Caminho | Parâmetros | Resposta |
|---|---|---|---|
| GET | `/import` | query `store_id` | `200` tela de envio e as 8 importações recentes |
| POST | `/import` | multipart `file`, form `store_id` | `303` para `/import/{id}`; `400`, `409`, `413`, `429` |
| GET | `/import/{import_id}` | n/a | `200` progresso; `303` para `/review` se `status = ready` |
| GET | `/import/{import_id}/status` | n/a | `200` JSON `{"status", "stage", "error"}` |
| POST | `/import/{import_id}/retry` | n/a | `303` `/import/{id}` |
| POST | `/import/{import_id}/cancel` | n/a | `303` `/import` |
| GET | `/import/{import_id}/review` | n/a | `200` conferência; `303` para o progresso se não está `ready` |
| POST | `/import/{import_id}/confirm` | form dos campos da conta | `303` para a loja; `400`/`409` re-renderizam |

### `POST /import`

Lê no máximo `MAX_UPLOAD_MB` + 1 byte. Respostas:

- `303` para `/import/{id}` e a leitura roda em segundo plano (`BackgroundTasks`).
- `400`: `UploadError` (arquivo vazio, acima do limite, extensão fora de JPG/PNG/WEBP/PDF, conteúdo que não
  corresponde à extensão, PDF com mais de 10 páginas).
- `409` "Este arquivo já foi analisado e não é uma conta de energia." (mesmo SHA-256 de uma importação `rejected`).
- `409` "Este mesmo arquivo já foi importado e a conta está salva. Nada foi enviado ao Gemini." (mesmo SHA-256 de
  uma importação `confirmed` cuja conta ainda existe).
- `413` JSON, do `BodySizeLimitMiddleware`, quando o `Content-Length` passa de `MAX_UPLOAD_MB` + 1 MB.
- `429` acima de 20 envios por minuto por IP.

### Estados da importação

`processing` → `ready` → `confirmed` ou `cancelled`; `processing` → `failed` (com *retry*) ou `rejected` (não é
conta de energia; os bytes são apagados). Uma importação `processing` parada há mais de `STALE_IMPORT_MINUTES`
(10) vira `failed` ao ser consultada (`expire_if_stale`). Estágios: `received`, `extracting`, `matching`, `done`.

### `POST /import/{import_id}/retry`

Só age se `status = failed`; volta para `processing` e dispara a leitura de novo. Em qualquer outro estado apenas
redireciona.

### `POST /import/{import_id}/cancel`

Marca como `cancelled` (se não estiver `confirmed`) e registra `cancel`. Não apaga os bytes do documento; eles
saem pela retenção.

### `POST /import/{import_id}/confirm`

Form: os campos de `macros.bill_fields` (`reference`, `total_value`, `due_date`, `consumption_*`, `demand_*` etc.),
`unit_mode` (`matched`, `existing` ou `new`), `unit_id`, `new_store_id`, `new_number`, `new_description`,
`duplicate_action` (`replace` ou `new`).

- `409` com `HTTPException` se a importação não está `ready`.
- `400` com a tela de conferência e os erros por campo.
- `409` com a tela de conferência e a lista de duplicidades (mesma unidade e mês, ou mesma nota) quando
  `duplicate_action` não é `replace` nem `new`.
- Sucesso: cria a conta (ou substitui a existente, guardando antes/depois na auditoria), marca `confirmed`,
  registra `import`, `303` para `/stores/{id}?highlight={unit}&type_id={tipo}`.

---

## `manual.py` — lançamento manual, exclusões e ficha da conta

| Método | Caminho | Acesso | CSRF |
|---|---|---|---|
| GET | `/manual` | Escrita | n/a |
| POST | `/manual` | Escrita | sim |
| POST | `/manual/bills/{bill_id}/delete` | Escrita | sim |
| POST | `/manual/records/{record_id}/delete` | Escrita | sim |
| GET | `/bills/{bill_id}/print` | Logado | n/a |

- **`GET /manual`**: query `bill` (editar conta), `record` (editar lançamento), `modo` (`loja`), `store_id`. Sem
  nenhuma pista de destino mostra só a escolha do tipo de lançamento. `404` se `bill`/`record` não existem.
- **`POST /manual`**: form `type_id`, `store_id`, `unit_id`, `edit_bill`, `edit_record`, `duplicate_action`
  (`replace` ou `new`) e os campos do tipo. Dois caminhos: tipo "conta" (usa `parse_bill_form`, exige unidade) ou
  tipo manual (`reference`, `value`, `due_date`, `notes` e `f_<campo>` numéricos). `400` com erros por campo;
  `409` com a lista de duplicidades; tipos exclusivos de lote são recusados aqui. Sucesso: `303` para
  `/stores/{id}`.
- **Exclusões**: `303` para `/units/{id}` (conta) ou `/stores/{id}` (lançamento), com registro `delete` na
  auditoria. `404` se não existe.
- **`GET /bills/{bill_id}/print`**: ficha A4 retrato. Query `doc` (`1` inclui o PDF/foto original, se ainda não
  expirou). `404` se a conta não existe.

---

## `manual_batch.py` — lançamento em lote

Acesso: **Escrita**.

| Método | Caminho | Parâmetros | Resposta |
|---|---|---|---|
| GET | `/manual/lote` | query `type` (código do tipo; padrão `ll-energia`) | `200` |
| POST | `/manual/lote` | form `type_id`, `reference`, `value`, `due_date`, `notes`, `f_<campo>`, `store_ids` (repetível), `duplicate_action` (`skip` ou `replace`); CSRF | `303` para `/notas?type_id=…&start=…&end=…&origin=manual` |

Um valor para várias lojas. Erros: `400` (tipo, mês, valor acima de `999999999999.99`, data, lojas inválidas ou
inativas, nenhuma loja marcada). `409` com a lista de lojas que já têm lançamento no mês; reenviar com
`duplicate_action=skip` mantém o existente e `replace` o substitui. Cada loja gera um evento de auditoria com o
identificador do lote.

---

## `types.py` — tipos de registro

Acesso: **Escrita**. Todo `POST` exige CSRF.

| Método | Caminho | Parâmetros | Resposta |
|---|---|---|---|
| GET | `/types` | n/a | `200` |
| POST | `/types` | form `name`, `kind` (`bill` ou `manual`), `description`, `fields` | `303` `/types` |
| POST | `/types/{type_id}` | form `name`, `description`, `aliases` (tipo conta), `fields` (tipo manual), `active` | `303` `/types` |

`fields`: um campo por linha no formato `Rótulo (unidade)`, até 12. `aliases`: separados por `,` ou `;`, até 10. O
código do tipo é o *slug* do nome; nome repetido gera *flash* de erro. `404` se o tipo não existe.

---

## `points.py` — ponto de energia rápido e vencimentos

| Método | Caminho | Acesso | CSRF |
|---|---|---|---|
| GET | `/points/new` | Escrita | n/a |
| POST | `/points` | Escrita | sim |
| GET | `/api/due` | Funcionário (`alerts_required`) | n/a |
| POST | `/api/due/{unit_id}/ack` | Funcionário (`alerts_required`) | sim |

- **`GET /points/new`**: query `next`, `fragment` (`1` devolve só o trecho do diálogo, usado por `app.js`),
  `store_id`. `next` só é aceito se começar com `/` (sem `//` nem `\`).
- **`POST /points`**: form `store_id`, `number` (até 40), `due_date` (obrigatório), `description` (até 200),
  `record_type_id`, `next`. Erros: `400` com a página. Se o número já existe, só atualiza o dia de vencimento e
  reabre o lembrete. Sucesso: `303` para `next`.
- **`GET /api/due`** devolve JSON:

  ```json
  {
    "today": "2026-10-10",
    "items": [
      {"unit_id": 12, "store_id": 3, "store": "CD300", "number": "12.060.073.018-19",
       "description": "", "supplier": "CEMIG", "due": "2026-10-10", "status": "today",
       "days": 0, "value": null, "bill_id": null, "label": "Vence hoje"}
    ],
    "can_ack": true
  }
  ```

  `status`: `today`, `overdue` ou `soon`. `value` é `null` quando a conta do vencimento ainda não foi lançada.
- **`POST /api/due/{unit_id}/ack`**: dá baixa no vencimento ("Já paguei"). Resposta `200` JSON
  `{"ok": true, "due": "AAAA-MM-DD"}`; `404` se a unidade não existe. Registra `due_ack`.

---

## `alerts.py` — central de alertas

| Método | Caminho | Acesso | Parâmetros | Resposta |
|---|---|---|---|---|
| GET | `/alertas` | Logado | query `sev` (`alta`, `media`, `baixa`) | `200` |
| POST | `/alertas/conferido` | `admin`, `operator`, `director` | form `key` (até 80); CSRF | `303` `/alertas` |
| GET | `/api/alertas/contagem` | Logado | n/a | `200` JSON `{"count": n, "high": n}` |

`POST /alertas/conferido`: `viewer` recebe `403`. Uma `key` que não corresponde a um alerta existente é ignorada
em silêncio (o redirecionamento acontece do mesmo jeito). A contagem fica em cache por 90 s por processo e é
zerada ao conferir um alerta.

---

## `charts.py` — dados do gráfico

| Método | Caminho | Acesso | Parâmetros | Resposta |
|---|---|---|---|---|
| GET | `/api/stores/{store_id}/chart` | Logado | `type_id`, `indicator`, `view` (`units` ou `types`), `start`, `end`, `highlight`, `unit_id` | `200` JSON; `404` se a loja não existe |

JSON (visão `units`): `view`, `empty`, `start`, `end`, `months`, `labels`, `indicator` (`key`, `label`, `kind`:
`brl`, `kwh` ou `kw`), `indicators`, `type`, `series[]` (`id`, `label`, `sublabel`, `highlight`, `color`, `data`,
`variations`, `lines`). A visão `types` acrescenta `stacked: true` e usa o indicador `value`. Consumido por
`static/js/chart_panel.js`. Limite `api`: 240 / 60 s.

---

## `documents.py` — arquivos originais

Acesso: **Logado** (qualquer perfil, inclusive `viewer`). Limite `documents`: 60 / 60 s por IP.

| Método | Caminho | Resposta |
|---|---|---|
| GET | `/documents/{doc_id}` | `200` com os bytes decifrados e o `Content-Type` original; `404` se não existe; `410` se o arquivo expirou; `500` se a chave de criptografia não abre o arquivo |
| GET | `/documents/{doc_id}/pages/{number}.png` | `200` PNG da página `number` (1 a 6) de um PDF; `404` se não é PDF ou a página não existe; `410`; `500` |

Cabeçalhos: `Content-Disposition: inline; filename="…"` (nome já sanitizado), `X-Content-Type-Options: nosniff`,
`Cache-Control: no-store`. Para imagem, `Content-Security-Policy: default-src 'none'; img-src 'self' data:; sandbox`.
Para PDF, **nenhum** CSP é enviado (o middleware pula `/documents/` e a rota só define CSP para imagem). O
`410` traz a mensagem "O arquivo original expirou e foi removido (os arquivos são guardados por 6 meses). Os dados
lidos da conta continuam salvos."

---

## `help.py` — ajuda

| Método | Caminho | Acesso | Resposta |
|---|---|---|---|
| GET | `/ajuda` | Logado | `200` página de ajuda por perfil |

---

## Rotas definidas em `app/main.py`

| Método | Caminho | Acesso | Resposta |
|---|---|---|---|
| GET | `/health` | público | `200` texto `ok`; `503` texto `banco indisponível` |
| GET | `/favicon.ico` | público | `301` para `/static/img/favicon.png` |
| GET | `/static/*` | público | arquivos estáticos (CSS, JS, imagens, Chart.js) |

### `GET /health`

Executa `SELECT 1` no banco. Corpo `text/plain`. É o `healthcheckPath` do `railway.json`; o Railway só promove o
deploy se responder `200`. Não verifica o Gemini nem a chave de criptografia. Fica fora da autenticação e não tem
política de rate limit própria (as políticas listadas acima não casam com `GET /health`); recebe os cabeçalhos de
segurança como as demais respostas.

---

## Exportações CSV

Três endpoints, todos `GET`, com o mesmo formato:

| Caminho | Acesso | Arquivo | Conteúdo |
|---|---|---|---|
| `/notas/export.csv` | Logado | `contas-economart.csv` | contas e lançamentos filtrados: mês, loja, unidade, tipo, valor, vencimento, nota, origem ("Foto/IA" ou "Manual") |
| `/diretoria/export.xlsx` | Diretoria | `painel-diretoria-economart.xlsx` | planilha formatada com 5 abas, mesmos filtros do painel |
| `/notas/export.xlsx` | qualquer perfil logado | `contas-economart.xlsx` | contas e lançamentos filtrados, com valores e datas tipados |
| `/diretoria/export.csv` | Diretoria | `comparativo-lojas-economart.csv` | comparativo entre lojas, mesmos filtros do painel |
| `/admin/audit/export.csv` | Admin | `auditoria-economart.csv` | até 20 mil eventos mais recentes, com a coluna *Selo* (16 primeiros caracteres do selo da cadeia) |

Formato: `text/csv; charset=utf-8` com BOM, separador `;`, fim de linha `\r\n`, vírgula decimal,
`Content-Disposition: attachment`. Todo texto digitado por pessoas passa por `_csv_cell`
(`app/routes/bills.py`), que prefixa `'` quando a célula começa com `=`, `+`, `-`, `@`, tab ou CR (injeção de
fórmula no Excel).

Cada exportação grava um evento `export` na auditoria (com filtros e número de linhas, quando aplicável). Por
isso são `GET` que escrevem no banco.

---

## Cabeçalhos de resposta relevantes

- `Content-Security-Policy` com `nonce` por resposta (exceto `/documents/*`); `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`,
  `Cross-Origin-Resource-Policy`; `Strict-Transport-Security` fora do `DEBUG`. Lista completa em
  [`security.md`](security.md).
- `Cache-Control: no-store` em tudo que não começa com `/static/`.
- `Retry-After`: só nas respostas `429`.
- `Set-Cookie: energia_session=…`: reescrito a cada resposta em que a sessão tem conteúdo.
- Não há `X-Request-ID` nem `X-RateLimit-*`.

---

## Códigos HTTP usados

- **200**: página ou JSON; também o resultado de ações que mostram dados uma única vez (senha provisória,
  códigos de recuperação do 2FA, relatório de integridade).
- **301**: `/favicon.ico`.
- **303**: redirecionamento após `POST`, login obrigatório, troca de senha obrigatória, 2FA obrigatório.
- **400**: validação de formulário ou de upload.
- **401**: falha de login (senha, usuário, código 2FA ou bloqueio). É o único uso de `401`.
- **403**: perfil sem permissão; CSRF inválido; origem cruzada recusada.
- **404**: loja, unidade, conta, lançamento, tipo, importação, documento ou página inexistente.
- **409**: conflito: código de loja repetido, duplicidade de conta/lançamento, arquivo já analisado ou já
  importado, importação que não está `ready`.
- **410**: documento original já removido pela retenção.
- **413**: corpo da requisição acima do limite.
- **422**: validação de tipos de parâmetro feita pelo FastAPI (por exemplo `store_id` não numérico). Não há
  *handler* customizado em `main.py`, então vale o formato padrão do FastAPI (`{"detail": [...]}`). Não foi
  verificado por execução neste ambiente.
- **429**: limite de requisições.
- **500**: erro não tratado (`error.html`, sem detalhe) ou falha de chave de criptografia ao abrir um documento.
- **503**: `/health` com banco indisponível.

## O que não foi verificado

- O corpo exato de `404`/`405` para rotas que não existem: `main.py` registra o *handler* para
  `fastapi.HTTPException`, e o roteador do Starlette levanta `starlette.exceptions.HTTPException`; o comportamento
  provável é o JSON padrão `{"detail": "Not Found"}`, mas as dependências não estão instaladas neste ambiente
  para confirmar.
- Os formatos de resposta foram lidos do código; nenhum endpoint foi chamado nesta documentação. A suíte
  `tests/` cobre os fluxos principais (login, bloqueio, CSRF, perfis, importação, CSV).
