# Segurança — como a proteção funciona

Este documento descreve os mecanismos de segurança que existem no código hoje, o motivo de cada decisão e os
limites conhecidos. Cada afirmação foi conferida no código em `app/`; o que não pôde ser verificado está marcado
como tal. O resumo para quem opera o sistema está em [`../SECURITY.md`](../SECURITY.md) e em
[`operations.md`](operations.md); este arquivo é a versão técnica.

O sistema guarda dados da empresa: valores de contas de energia, consumo, unidades consumidoras e as fotos/PDFs
das contas. Os usuários são poucos e internos, em quatro perfis (`admin`, `operator`, `director`, `viewer`).
Não há cadastro público, recuperação de senha por e-mail nem API para terceiros.

## Visão geral das camadas

```
Navegador ── HTTPS ──> proxy do Railway (1 salto) ──> uvicorn ──> FastAPI

Ordem dos middlewares (de fora para dentro, app/main.py):
  SecurityHeadersMiddleware   nonce do CSP, cabeçalhos, Cache-Control
  RateLimitMiddleware         janela deslizante por IP, em memória
  BodySizeLimitMiddleware     corta corpo gigante antes do parse
  CSRFOriginMiddleware        recusa mutação de outra origem
  SessionMiddleware           cookie assinado "energia_session"
  → rota: current_user / writer_required / admin_required / ... + verify_csrf
```

O último `add_middleware` é o mais externo; por isso os cabeçalhos envolvem tudo e a sessão fica por dentro.

---

## Senhas

**Hash**: `scrypt` da biblioteca padrão (`hashlib.scrypt`), `N = 2^15` (`SCRYPT_LOGN = 15`), `r = 8`, `p = 1`, sal de
16 bytes aleatórios (`os.urandom`), `maxmem` de 128 MB. Formato armazenado: `scrypt$15$<sal-hex>$<hash-hex>`. A
comparação usa `hmac.compare_digest`.

Hashes antigos continuam válidos: o formato legado de três partes (`scrypt$sal$hash`, `N = 2^14`) é lido, e
`needs_rehash` faz o login regravar o hash no parâmetro atual. A escolha do scrypt foi por não depender de
biblioteca externa nem de extensão compilada.

**Política** (`validate_password`), aplicada à senha pessoal na troca:

- mínimo de 8 caracteres (`MIN_PASSWORD_LENGTH`); o administrador inicial exige 12 (ver
  [Validação de configuração](#validação-de-configuração-no-start));
- máximo de 200 caracteres;
- recusa a lista de senhas comuns embutida em `security.py` (22 entradas, como `123456`, `qwerty`, `economart`,
  `trocar123`), comparada também com a senha reduzida às letras;
- recusa senha que contém o nome de usuário;
- recusa senha com menos de 5 caracteres distintos;
- exige ao menos 2 classes entre minúscula, maiúscula, dígito e símbolo.

A lista de comuns é curta de propósito: a política barra o óbvio e não substitui verificação contra bases de
vazamento (não existe aqui).

**Tempo constante na enumeração**: quando o usuário não existe, ou a conta está bloqueada, o login ainda executa
uma verificação scrypt contra um hash-isca (`verify_dummy`), para que o tempo de resposta não revele se o nome
existe.

### Senha provisória

Usuário novo e senha redefinida pelo administrador recebem uma **senha de 4 dígitos** (`generate_temp_password`):

- sorteio uniforme com `secrets.randbelow(10_000)`, descartando padrões previsíveis: todos iguais (`0000`),
  sequência crescente ou decrescente (`1234`, `4321`), par repetido (`1212`) e `2026`, `2025`, `2024`, `1010`;
- exibida **uma única vez**, na própria resposta HTTP `200` do administrador (nunca em cookie nem em *flash*);
- vale `TEMP_PASSWORD_HOURS` (48 h); depois disso, mesmo com a senha certa, o login falha com a mensagem genérica e
  registra `login_temp_expired`;
- enquanto `must_change_password` está ativo, `current_user` só deixa abrir `/account/password` e `/logout`;
  qualquer outra rota redireciona para a troca;
- a conta bloqueia na **3ª** tentativa errada (`TEMP_MAX_LOGIN_ATTEMPTS`), em vez da 5ª.

É fraca de propósito (uso interno, só para o primeiro acesso, entregue pelo administrador). As salvaguardas
acima compensam, mas ver [Limites e riscos conhecidos](#limites-e-riscos-conhecidos).

### Bloqueio por tentativas

- 5 falhas (`MAX_LOGIN_ATTEMPTS`) bloqueiam a conta por 15 minutos (`LOGIN_BLOCK_MINUTES`); ao bloquear, o contador
  volta a zero e registra-se `account_locked`.
- Credencial errada, usuário inexistente e conta inativa mostram **a mesma mensagem** ("Usuário ou senha
  incorretos."). O bloqueio mostra outra ("Acesso bloqueado por excesso de tentativas… N minuto(s)").
- Para o bloqueio não revelar quem existe, usuário **inexistente** também é bloqueado: a tabela `login_throttle`
  guarda as falhas por uma chave `HMAC` do nome digitado (o nome bruto não é gravado); depois de 1 dia, linhas
  antigas são limpas.
- O administrador libera na hora em *Usuários → Desbloquear* (`account_unlocked`). Redefinir a senha também
  desbloqueia.
- Além do bloqueio por conta, há o limite de 10 `POST /login` por minuto por IP (`429`).

---

## Sessão e cookies

A sessão é o `SessionMiddleware` do Starlette com cookie **assinado** (não cifrado) chamado `energia_session`:

| Atributo | Valor |
|---|---|
| `HttpOnly` | sempre |
| `SameSite` | `strict` |
| `Secure` | `https_only = not DEBUG` |
| `Max-Age` | `SESSION_MAX_HOURS × 3600` (12 h) |

Conteúdo da sessão: `uid`, `epoch`, `iat` (início), `seen` (último uso), `csrf`, mensagens *flash* e, durante o 2FA,
`pre2fa`. Não há JWT, nem refresh token, nem `localStorage` com credencial.

Uma sessão é válida (`current_user`) só se **todas** as condições valem:

1. o usuário existe e está ativo;
2. `sessão.epoch == usuário.session_epoch`;
3. `agora − iat ≤ SESSION_MAX_HOURS` (duração máxima absoluta, 12 h);
4. `agora − seen ≤ SESSION_IDLE_MINUTES` (inatividade, 60 min). `seen` é atualizado a cada requisição autenticada.

Se qualquer uma falha, a sessão é limpa e o usuário vai para `/login`.

**Revogação por época.** `User.session_epoch` é incrementado em: logout, troca de senha, redefinição pelo
administrador, mudança de perfil, desativação, ativação do 2FA e remoção do 2FA. Como a sessão carrega a época de
quando nasceu, todas as sessões antigas do usuário, **inclusive cookies copiados**, deixam de valer na hora. Isso
substitui a lista de sessões no servidor.

**Fixação de sessão.** `start_session` chama `request.session.clear()` antes de gravar a nova sessão; o login
completo, a troca de senha e a ativação/desativação do 2FA sempre recriam a sessão (e, com ela, o token CSRF).

**Redirecionamento aberto.** O parâmetro `next` do login e de `/points` só é aceito se começar com `/` e não com
`//` nem contiver `\`.

---

## CSRF

Duas camadas independentes, porque `SameSite=Strict` sozinho não cobre navegadores antigos nem subdomínios.

1. **Origem** (`CSRFOriginMiddleware`), em toda mutação (`POST`, `PUT`, `PATCH`, `DELETE`):
   - `Sec-Fetch-Site: cross-site` é recusado;
   - `Origin: null` é recusado;
   - `Origin` presente precisa ter o mesmo `netloc` do cabeçalho `Host`, ou estar na lista `CSRF_ALLOWED_ORIGINS`
     (normalmente vazia);
   - recusa: `403` JSON "Origem não permitida para esta operação.".
2. **Token** (`verify_csrf`), declarado como dependência em **todas** as rotas `POST` (conferido: nenhum `POST`
   em `app/routes/` fica sem). Token por sessão, `secrets.token_urlsafe(32)`, criado sob demanda e guardado em
   `session["csrf"]`. O cliente envia:
   - o campo de formulário `csrf_token` (macro `csrf()` em `macros.html`, ou campo oculto direto), **ou**
   - o cabeçalho `X-CSRF-Token` (usado por `app.js` no logout e na baixa de vencimento, lendo
     `<meta name="csrf-token">` de `base.html`).

   A comparação usa `hmac.compare_digest`. Ausente ou diferente: `403` "Sessão expirada ou requisição inválida.
   Recarregue a página.".

O token não muda a cada requisição; muda quando a sessão é recriada (login, troca de senha, 2FA). `GET` não altera
dados de negócio, então não leva token.

---

## Cabeçalhos de segurança e CSP

`SecurityHeadersMiddleware` gera um **nonce** novo por resposta (`secrets.token_urlsafe(16)`), guarda em
`request.state.csp_nonce` e `render()` o entrega aos templates como `csp_nonce`. Cabeçalhos enviados:

| Cabeçalho | Valor |
|---|---|
| `Content-Security-Policy` | ver abaixo (omitido em `/documents/*`) |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), payment=()` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cross-Origin-Resource-Policy` | `same-origin` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains`, só com `DEBUG=false` |
| `Cache-Control` | `no-store` em tudo que não começa com `/static/` e não define o próprio |

CSP:

```
default-src 'self'; script-src 'self' 'nonce-<nonce>'; style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src 'self';
object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'
```

Consequências para quem mexe no frontend:

- **Nenhum JavaScript inline sem nonce e nenhum manipulador inline** (`onclick=`, `onchange=`). Comportamentos
  vêm de atributos `data-*` tratados em `app.js` (`data-confirm`, `data-print`, `data-autosubmit`,
  `data-filter`, `data-toggle-password`…). Dados para scripts vão em `<script type="application/json">` ou em
  `data-*` com `|tojson`. O teste `test_pages_have_no_inline_event_handlers_and_every_inline_script_has_nonce`
  protege isso.
- O Chart.js é servido de `/static/js/vendor/chart.umd.min.js` (v4.4.7): sem CDN, sem origem externa no CSP.
- `style-src` mantém `'unsafe-inline'`: os templates usam atributos `style=` (cerca de 100 ocorrências). É a
  principal concessão do CSP (ver limites).
- `frame-src 'self'` e `X-Frame-Options: SAMEORIGIN` permitem o PDF original em `<iframe>` na conferência, e
  nada de fora.
- `form-action 'self'` impede que um formulário injetado envie dados para outro domínio.

Respostas de `/documents/*`: o middleware não define CSP nelas; a rota define
`default-src 'none'; img-src 'self' data:; sandbox` para **imagem**. Para **PDF** não há CSP (ver limites).

Autoescape do Jinja2 está ativo (padrão do `Jinja2Templates`); a conferência de campos usa `value="{{ … }}"` sempre
escapado.

---

## IP real, proxy e rate limit

**IP do cliente** (`client_ip`): com `TRUSTED_PROXY_COUNT = N` (padrão 1, o do Railway), vale a N-ésima entrada
**a partir do fim** de `X-Forwarded-For`. As entradas à esquerda podem ser forjadas pelo cliente; a última foi
escrita pelo proxy de confiança. Com `N = 0`, ou com menos entradas que `N`, usa o IP da conexão. Valor truncado em
64 caracteres. Se o app for exposto sem proxy confiável na frente, o cabeçalho passa a ser controlado pelo
cliente e o IP, assim como o rate limit por IP, deixa de ser confiável.

**Rate limit** (`RateLimitMiddleware`): janela deslizante em memória, por `política:IP`. Tabela completa em
[`api-reference.md`](api-reference.md#limites-de-requisições-por-ip-janela-deslizante-em-memória). Pontos que
importam aqui:

- login e 2FA: 10 por minuto por IP; troca de senha: 10 por 10 minutos; upload: 20 por minuto; documentos: 60 por
  minuto; `GET /api/*`: 240 por minuto; demais mutações: 120 por minuto.
- resposta `429` JSON com `Retry-After` igual à janela;
- o dicionário de contadores é podado quando passa de 5 000 chaves;
- vale **por processo**: com mais de uma instância, cada uma conta separado (Redis seria o próximo passo);
- `RATE_LIMIT_ENABLED=false` desliga (usado em testes).

**Tamanho do corpo** (`BodySizeLimitMiddleware`, ASGI puro): em mutações, acima de 1 MB é recusado com `413`; em
`POST /import` o teto é `MAX_UPLOAD_MB + 1 MB`. Um `Content-Length` declarado acima do teto é recusado na hora; sem
esse cabeçalho (ou com um valor falso), os bytes são contados conforme chegam e a leitura é interrompida ao passar do
teto (a resposta é descartada e o middleware devolve o `413`, porque o FastAPI converteria a interrupção em `400`). A
checagem ocorre antes do parse multipart e antes de qualquer verificação de sessão.

---

## 2FA do administrador (TOTP)

Só o perfil `admin` tem 2FA. Implementação própria em `app/services/totp_service.py`, RFC 6238:

| Parâmetro | Valor |
|---|---|
| Algoritmo | HMAC-SHA1 |
| Dígitos | 6 |
| Período | 30 s |
| Tolerância | ±1 janela (`WINDOW = 1`), para relógio de celular um pouco fora |
| Segredo | 20 bytes aleatórios (`secrets.token_bytes(20)`), em base32 |
| Emissor no app | "Economart Energia" |

Compatível com Google Authenticator, Microsoft Authenticator e Authy (URI `otpauth://totp/…`).

**Ativação** (`/account/2fa`): a primeira visita gera um segredo ainda inativo e mostra o QR code (SVG gerado no
servidor com `segno`) e o segredo em texto. O 2FA só passa a valer depois que o administrador digita um código
correto. Nesse momento:

1. `totp_enabled = true`;
2. são gerados **8 códigos de recuperação** no formato `xxxx-xxxx` (hex), mostrados **uma única vez** na tela (com
   botão de imprimir) e guardados só como `SHA-256`;
3. as outras sessões do administrador são revogadas.

**Login com 2FA.** Senha correta de um administrador com 2FA **não cria sessão**: `POST /login` grava
`session["pre2fa"]` (usuário, instante, destino) e redireciona para `/login/2fa`. Essa etapa expira em 300 s. O
código aceito é o TOTP ou um código de recuperação (que é consumido).

**Anti-replay.** `check_code` só aceita um passo de 30 s maior que `totp_last_step`; cada código TOTP vale uma
vez, mesmo dentro da janela de tolerância.

**Anti-força-bruta.** Erro de código conta como tentativa errada de login (`failed_attempts`): 5 seguidas bloqueiam
a conta por 15 min. A senha certa **não zera** o contador (só o sucesso do código zera), senão seria possível
chutar o código sem limite alternando com a senha. Além disso, `POST /login/2fa` tem limite de 10 por minuto por
IP.

**Segredo em repouso.** `seal()` cifra o segredo com Fernet usando `DOCUMENT_ENCRYPTION_KEY` (prefixo `enc:`). Sem
chave (somente `DEBUG`), grava com prefixo `raw:`.

**`REQUIRE_ADMIN_2FA=true`.** Administrador sem 2FA é redirecionado (`MustSetup2FA`) para `/account/2fa` em toda
rota autenticada, exceto `/account/2fa*`, `/account/password` e `/logout`. Com `false` (padrão), o administrador
sem 2FA vê um aviso em `/` e `/admin/users`.

**Desativar**: exige senha **e** código (TOTP ou recuperação).

**Perda do celular**, em ordem de preferência:

1. entrar com um código de recuperação (cada um serve uma vez);
2. outro administrador usa *Usuários → Redefinir 2FA* (`POST /admin/users/{id}/reset-2fa`), que remove o 2FA do
   alvo e encerra as sessões dele (`2fa_reset`);
3. se for o único administrador: no servidor, `python -m scripts.reset_2fa <usuario>`. O script usa o mesmo
   `DATABASE_URL` do app, chama `totp_service.disable`, grava `2fa_reset` na auditoria (`{"by": "script"}`) e
   encerra as sessões. Exige acesso ao servidor ou ao banco, por isso não é uma brecha remota.

O usuário refaz o cadastro em `/account/2fa` no próximo acesso.

---

## Auditoria à prova de adulteração

Tabela `audit_log` (`AuditLog`): `at`, `user_id`, `action`, `entity`, `entity_id`, `details` (JSON), `prev_hash`,
`row_hash`. Eventos são criados por `audit_service.log(...)` e por `auth_service.security_event(...)`.

### Cadeia HMAC

Um *listener* `before_flush` da `Session` calcula, para cada evento novo:

```
row_hash = HMAC-SHA256(chave, prev_hash + "|" + JSON canônico(at, user_id, action, entity, entity_id, details))
```

- `prev_hash` é o `row_hash` do evento anterior (vazio no primeiro).
- O JSON canônico tem chaves ordenadas, `at` em UTC com microssegundos, sem espaços, `ensure_ascii=False`.
- Chave: `PSEUDONYM_KEY`, ou `SECRET_KEY` se vazia, mais o sufixo `:audit-chain` (separada da chave de
  pseudonimização, que usa o sufixo `:pseudonym`).
- No PostgreSQL, a escrita da cadeia é serializada com `pg_advisory_xact_lock(7461001)`, para duas transações não
  criarem dois eventos com o mesmo `prev_hash` (bifurcação). No SQLite (desenvolvimento) não há esse lock.
- Qualquer evento gravado por `Session` entra na cadeia, inclusive o `purge` da retenção, o script `reset_2fa` e os
  eventos de login.

### Verificação de integridade

*Auditoria → Verificar integridade* (`POST /admin/audit/verify`, `audit_service.verify_chain`) percorre todos os
eventos em ordem de `id`, em lotes de 2 000, e para no **primeiro** problema, informando o `id`:

- evento **sem selo** depois que a cadeia começou ("inserido ou editado fora do sistema");
- `prev_hash` diferente do selo do evento anterior ("evento removido ou inserido antes deste");
- selo que não bate com o conteúdo recalculado ("conteúdo alterado depois de gravado").

Resultado bom: "Auditoria íntegra", quantos eventos estão protegidos, quantos são anteriores à proteção
(`row_hash` nulo, "não verificáveis") e o **selo final** (hash do último evento). A própria verificação grava
`audit_verified`.

### O que a cadeia não cobre

- **Apagar só os últimos eventos** não quebra elo nenhum. Contra isso, anote o selo final de tempos em tempos;
  se ele deixar de aparecer na cadeia, houve truncamento. O CSV traz os 16 primeiros caracteres do selo de cada
  evento (coluna *Selo*).
- Quem tem o banco **e** o `SECRET_KEY`/`PSEUDONYM_KEY` consegue recalcular a cadeia inteira. A proteção é contra
  edição direta no banco por quem não tem a chave do ambiente.
- **Trocar `SECRET_KEY` (sem `PSEUDONYM_KEY` definida) invalida a verificação dos eventos antigos**, porque a chave
  nova não reproduz os selos. Antes de trocar: exporte o CSV e rode a verificação. Definir `PSEUDONYM_KEY` fixa
  desacopla a cadeia da chave de sessão.

### IP real e nome digitado pseudonimizado

Decisão registrada em `AGENTS.md`: **o IP não é anonimizado**. Os eventos gravados por
`security_event` (login e suas falhas, bloqueios, `login_blocked`, logout, troca da própria senha, ativação e
falhas do 2FA próprio) levam `{"ip": <IP real>}` em `details`, porque o uso é em máquinas corporativas e o IP é o
dado útil numa investigação. Eventos de alteração de dados e ações do administrador sobre outras contas
(`create`, `update`, `delete`, `password_reset`, `account_unlocked`, `role_change`, `2fa_reset`…) são gravados por
`audit_service.log` e **não** levam IP.

O que continua pseudonimizado é o **nome de usuário digitado** em tentativa de login com usuário inexistente:
`pseudonymize()` grava `"h:" + 16 primeiros hex do HMAC-SHA256` (chave `PSEUDONYM_KEY`/`SECRET_KEY` + `:pseudonym`).
Isso permite correlacionar tentativas sem guardar um possível erro de digitação de senha no campo de usuário. A tela
de auditoria mostra "usuário digitado oculto" para esses valores e "IP anonimizado (registro antigo)" para IPs
gravados como `h:…` em versões anteriores. A senha digitada nunca é gravada.

Detalhes de alteração de dados incluem `before`/`after` (por exemplo, na substituição de conta); a tela de
auditoria não os exibe, mas o JSON fica no banco.

### Eventos registrados

| Grupo | Ações (`action`) |
|---|---|
| Acesso | `login`, `login_password_ok`, `login_2fa`, `login_failed`, `login_2fa_failed`, `login_blocked`, `account_locked`, `account_unlocked`, `login_temp_expired`, `logout` |
| Senha | `password_changed`, `password_change_failed`, `password_reset` |
| 2FA | `2fa_enabled`, `2fa_setup_failed`, `2fa_disabled`, `2fa_disable_failed`, `2fa_reset` |
| Usuários | `create`, `role_change`, `activate`, `deactivate` |
| Dados | `create`, `update`, `delete`, `replace` em loja, unidade, conta, lançamento e tipo |
| Importação | `extract`, `import`, `import_rejected`, `cancel` |
| Rotinas | `purge`, `export`, `audit_verified`, `due_ack`, `alert_ack` |

A tela mostra os últimos 300 eventos; o CSV, até 20 mil.

---

## Criptografia dos documentos

Fotos e PDFs das contas ficam **no banco** (`documents.data`, `LargeBinary`), porque o disco do Railway é
efêmero. Antes de gravar, `create_import` cifra os bytes com `crypto_service.encrypt`:

- **Fernet** (AES-128-CBC com HMAC-SHA256, da biblioteca `cryptography`), via `MultiFernet`;
- `DOCUMENT_ENCRYPTION_KEY` aceita **várias chaves separadas por vírgula**: a primeira cifra, todas decifram. É a
  rotação: coloque `nova,antiga` e as leituras antigas continuam funcionando;
- cada `Document` tem o flag `encrypted`; arquivo gravado sem chave (só em `DEBUG`) continua legível sem ela;
- a leitura (`Document.plain()`) decifra sob demanda; chave ausente ou diferente levanta `CryptoError`, que as
  rotas traduzem para uma mensagem sem detalhe ("erro de chave de criptografia"), sem vazar nada.

Gerar a chave:

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Perder a chave torna os arquivos já gravados ilegíveis; os dados lidos das contas (valores, consumo) não dependem
dela. O segredo TOTP dos administradores também é cifrado com essa chave. **Guarde a chave em um cofre, separada
do backup do banco.** Rotacionar não recifra os arquivos antigos: eles seguem cifrados com a chave antiga, que
precisa permanecer na lista. Não existe script de recifragem.

A cifra protege contra vazamento de um *dump* do banco. Não protege contra quem comprometer o próprio processo da
aplicação, que tem a chave.

---

## Validação de upload e rejeição de arquivos que não são conta de energia

### Validação do arquivo (`app/utils/uploads.py`, `validate_upload`)

Em ordem:

1. arquivo não vazio;
2. tamanho máximo `MAX_UPLOAD_MB` (12 MB). A rota lê no máximo `limite + 1` byte, e o middleware corta antes por
   `Content-Length`;
3. extensão na lista `jpg`, `jpeg`, `png`, `webp`, `pdf`;
4. **conteúdo real** (magic bytes) compatível com a extensão: JPEG `FF D8 FF`, PNG, WEBP (`RIFF…WEBP`), PDF
   (`%PDF-`). Um `.pdf` com conteúdo de imagem é recusado;
5. PDF com no máximo 10 páginas, contadas por expressão regular de `/Type /Page`;
6. nome sanitizado: só letras, dígitos e `._- `, sem caminho, até 120 caracteres.

Falha vira `UploadError` e `400` com a mensagem na tela de envio. O SHA-256 do arquivo é gravado em
`documents.sha256` e usado para impedir o reenvio do mesmo arquivo (já importado, ou já rejeitado) antes de chamar
o Gemini.

Antes de enviar ao modelo, imagens passam por `prepare_for_model`: rotação conforme EXIF e redução para lado maior
de 3000 px (reencodadas em JPEG) quando necessário; PDF vai intacto. O original guardado não é alterado. Erro no
pré-processamento é engolido e o original é enviado.

### Rejeição de arquivo que não é conta

A decisão tem duas pontas, a IA e o servidor:

- o prompt pede que o modelo preencha `is_energy_bill` (verdadeiro **somente** para fatura de distribuidora de
  energia) e, se falso, `not_bill_reason` e todos os demais campos nulos;
- o servidor (`rejection_reason`) rejeita quando `is_energy_bill is False`, **ou** quando nenhum campo que
  identifique uma conta foi lido (unidade consumidora, valor, mês, nota, vencimento) e não há itens faturados.

Rejeitado: nada é lançado, os **bytes são apagados na hora** (`doc.data = None`), a importação vira `rejected` e
resta na auditoria `import_rejected` com nome do arquivo, motivo (até 120 caracteres), provedor e
`bytes_deleted: true`. O hash permanece, então reenviar o mesmo arquivo dá `409` sem nova chamada ao Gemini.

Outras regras desse fluxo: a IA nunca grava sozinha (toda conta passa pela tela de conferência); a resposta do
modelo é validada contra o esquema Pydantic `BillExtraction` (JSON inválido vira erro de extração); o prompt manda
devolver `null` quando o campo não está legível ("zero chute").

### Circuit breaker do Gemini

`app/services/circuit_breaker.py`, instância `gemini_breaker`. Sem ele, uma queda do Google faria cada envio
esperar o timeout (120 s) e as retentativas antes de falhar.

- **Fechado**: as chamadas passam. Cada falha *do Google* soma ao contador (reinicia com qualquer sucesso).
- **Aberto**: depois de 5 falhas seguidas (`failure_threshold`), rejeita na hora por 30 s (`reset_seconds`) com a
  mensagem "O Gemini está instável no momento. Aguarde cerca de 30 segundos e tente de novo."
- **Meio-aberto**: passados os 30 s, deixa passar **uma** chamada de teste por vez; sucesso fecha, falha reabre.
- Só conta como falha o `UpstreamError`: `429`, `5xx`, rede, timeout. Erro do arquivo ou da configuração
  (`400`, `401`, `403`, `404`, JSON inválido) **não** abre o disjuntor.
- Dentro de cada chamada há até 3 tentativas (`MAX_ATTEMPTS`) com espera de 2 s e 4 s para `429/500/502/503/504` e
  falhas de rede transitórias. Uma extração que esgota as tentativas soma **uma** falha ao disjuntor.
- Estado por processo (basta para 1 instância).
- Concorrência: no máximo `GEMINI_MAX_CONCURRENCY` (2) leituras simultâneas (semáforo em `import_service`).

Mensagens ao usuário nunca incluem chave, URL ou *stack*. `install_log_redaction` filtra dos logs padrões
`AIza…`, `x-goog-api-key` e `?key=`, além do valor literal de `GEMINI_API_KEY`.

---

## Validação de configuração no start

`create_app()` chama `security_problems(settings)` (`app/startup_checks.py`) e, se a lista não estiver vazia,
levanta `RuntimeError("Configuração insegura — o servidor não inicia em produção sem corrigir:\n - …")`. Como
`app = create_app()` roda na importação do módulo, o `uvicorn` não sobe. Com `DEBUG=false` (o padrão do código), é
recusado:

| Problema | Regra |
|---|---|
| `SECRET_KEY` | menos de 32 caracteres, ausente, ou um dos valores fracos (`changeme`, `secret`, `trocar`, `troque-em-producao`, `test-secret`) |
| `DOCUMENT_ENCRYPTION_KEY` | ausente, ou alguma das chaves da lista não é uma chave Fernet válida |
| `DATABASE_URL` | começa com `sqlite` |

Em `DEBUG=true` nada disso é exigido: sem `SECRET_KEY` gera-se uma chave temporária (as sessões caem a cada
reinício), o cookie não é `Secure`, não há HSTS e, se não houver `ADMIN_PASSWORD`, o administrador inicial é
`admin`/`admin`. `DEBUG=true` **nunca** deve ir para produção; o `.env.example` traz `DEBUG=true` só para
desenvolvimento local.

Há uma segunda verificação, fora de `security_problems`: no `lifespan`, `seed()` cria o administrador inicial
**apenas se não existe nenhum usuário**. Fora do `DEBUG`, a `ADMIN_PASSWORD` precisa passar em
`validate_password` com mínimo de 12 caracteres, senão `RuntimeError("ADMIN_PASSWORD recusada: …")` interrompe a
subida. Num banco que já tem usuários, a variável é ignorada e nenhuma validação ocorre.

Outros cuidados: erros `500` nunca mostram detalhe da exceção (`error.html`, mensagem fixa); o *traceback* vai só
para o log, com chaves redigidas; documentação interativa do FastAPI desativada.

---

## Retenção e expurgo de documentos (LGPD)

- Foto/PDF originais são **removidos do banco** `DOCUMENT_RETENTION_DAYS` (183 dias, cerca de 6 meses) depois da
  data de envio (`documents.created_at`).
- `retention_loop` é uma tarefa assíncrona iniciada no `lifespan`: roda na subida e depois a cada
  `RETENTION_CHECK_HOURS` (6 h), em *thread*; falha é logada e nunca derruba o app.
- O expurgo faz `data = NULL` e `purged_at = agora`. A linha em `documents` permanece com nome, tipo, tamanho e
  SHA-256, para a tela explicar "Original expirado". Registra `purge` na auditoria (`count`, `retention_days`).
- Depois disso, `GET /documents/{id}` responde `410`.
- Manual: `python -m scripts.purge_documents`.
- Arquivo rejeitado (não é conta) é apagado imediatamente, sem esperar a retenção.
- Valores, consumo, itens da conta e gráficos **permanecem**: são os dados do negócio.

O que a retenção **não** apaga (ver limites): o JSON bruto da leitura em `imports.extracted` (inclui nome e
endereço do cliente impressos na conta), o nome do arquivo, o hash, e os bytes de uma importação apenas
*descartada* (`cancelled`), que saem na retenção normal.

O desenho adota: minimização do que fica após 6 meses; nome digitado em login falho pseudonimizado; senhas nunca
gravadas em claro nem em log; trilha de auditoria de quem acessou e alterou. Não houve avaliação jurídica; este
texto descreve o que o código faz.

---

## Controle de acesso por perfil

Aplicado no servidor, em cada rota, por dependências (`app/security.py`). Esconder botão na tela é só conveniência.

| Perfil | Pode |
|---|---|
| `admin` | tudo do funcionário, mais usuários, auditoria, 2FA, painel da diretoria |
| `operator` | importar, lançar, editar, excluir; lojas, unidades, tipos; vencimentos e alertas. Não vê usuários, auditoria nem painel da diretoria |
| `director` | consulta, painel da diretoria, imprime; confere alertas. Não escreve |
| `viewer` | consulta e imprime |

Regras que protegem a administração: não é possível rebaixar nem desativar o último administrador ativo; o
administrador não desativa a si mesmo; mudança de perfil revoga as sessões do usuário. Os avisos de vencimento
(`/api/due`) são só do `operator`.

Há um ponto de atenção: toda a leitura (`/stores`, `/notas`, `/bills/{id}/print`, etc.) está liberada a **qualquer
perfil logado**, sem escopo por loja. O modelo de dados não tem restrição por loja ou região. Exceção, desde
2026-10-10: `/documents/{id}` só entrega o arquivo a qualquer perfil quando ele pertence a uma conta confirmada;
enquanto a importação ainda está em conferência, só quem lança contas (`operator`, `admin`) abre o arquivo.

---

## Dependências e CI

`.github/workflows/ci.yml` roda a cada `push` e `pull_request`: `ruff check --select F,E9`, `pytest -q` e
`pip-audit -r requirements.txt` com `continue-on-error: true`, ou seja, **a auditoria de vulnerabilidades alerta
mas não bloqueia o merge**. As dependências em `requirements.txt` usam `>=` (sem versões fixadas nem arquivo de
lock), então a instalação de produção pega a versão mais recente compatível no momento do build.

---

## Limites e riscos conhecidos

Itens abaixo são verificáveis no código, a menos que marcados como "não verificado".

**Autenticação e sessão**

- 2FA **só para administradores**. Funcionário, diretoria e consulta entram só com senha.
- Sem recuperação de senha por e-mail (de propósito: não há canal de e-mail a proteger). Quem esquece a senha
  depende do administrador, e esse é o principal alvo de engenharia social.
- **Bloqueio de conta permite negação de serviço**: quem sabe um nome de usuário pode bloqueá-lo por 15 minutos
  com 5 tentativas erradas, repetidamente. O limite por IP (10/min) não impede isso contra uma conta de cada vez.
- **Senha provisória de 4 dígitos**: são cerca de 10 mil combinações menos os padrões descartados. Com o bloqueio
  em 3 tentativas por 15 minutos, um atacante que saiba o usuário e a janela de 48 h consegue na ordem de 576
  tentativas (estimativa: 3 tentativas × 4 janelas de 15 min por hora × 48 h), isto é, perto de 6% de chance de
  acertar antes de expirar. Só serve para trocar a senha, mas quem acerta assume a conta. Reduzir
  `TEMP_PASSWORD_HOURS` e entregar a senha logo diminui a exposição.
- **Códigos de recuperação do 2FA** têm 32 bits de entropia cada e são guardados como `SHA-256` sem sal. Num
  vazamento do banco, são recuperáveis por força bruta offline. O 2FA protege contra a senha vazada, não contra
  quem já tem o banco.
- A sessão é um cookie **assinado, não cifrado**: o conteúdo (ids, instantes, token CSRF, *flash*) é legível por
  quem tem o cookie. Segredos (como a senha provisória) nunca vão para a sessão.
- Senha de administrador pode ser um valor que só passa na política (12 caracteres, 2 classes); não há verificação
  contra senhas vazadas.
- Perda da `DOCUMENT_ENCRYPTION_KEY` também cifra o segredo TOTP: o login por 2FA dos administradores deixaria de
  funcionar (não verificado por execução; a leitura do segredo falha em `decrypt`). A saída seria
  `python -m scripts.reset_2fa`, que não precisa decifrar nada.

**Rede e cabeçalhos**

- Rate limit e contagem de falhas por IP dependem de `TRUSTED_PROXY_COUNT` correto. Fora do Railway, ou com outro
  proxy/CDN na frente, o valor precisa ser ajustado; errado, o IP de auditoria e o limite ficam sem sentido.
- Rate limit **em memória por processo**: some no reinício e não é compartilhado entre instâncias.
- `style-src 'unsafe-inline'` continua no CSP. Um HTML injetado com `style` não executa script, mas permite
  alterar aparência e, em tese, exfiltrar por seletores CSS de atributo; o risco é reduzido pelo
  autoescape e por `connect-src`, `img-src` e `form-action` restritos.
- **PDF sem CSP**: `/documents/{id}` entrega PDF sem `Content-Security-Policy` (só imagem leva `sandbox`). Há
  `nosniff`, `Content-Type: application/pdf`, `X-Frame-Options: SAMEORIGIN` e `Cross-Origin-Resource-Policy`; o
  navegador abre o PDF no visualizador próprio. Um PDF malicioso depende de falhas desse visualizador.
- Corrigido em 2026-10-10: o limite de corpo antes só olhava o `Content-Length` declarado; hoje conta os bytes
  recebidos (ver "Tamanho do corpo"). Testado de ponta a ponta com corpo em pedaços (`tests/test_security_hardening.py`).
- Respostas `500` geradas pelo `@app.exception_handler(Exception)` provavelmente saem por fora do
  `SecurityHeadersMiddleware` (no Starlette esse tratador fica na camada mais externa), logo sem os cabeçalhos
  de segurança. Não verificado por execução. A página é fixa e sem dado sensível.
- Não há `Strict-Transport-Security` com `preload`.

**Upload e IA**

- Corrigido em 2026-10-10: a contagem de páginas do PDF era uma expressão regular sobre `/Type /Page`, que PDFs com
  objetos comprimidos burlavam. Hoje usa o `pypdfium2`, o mesmo leitor que abre o arquivo depois; PDF que não abre é
  recusado com mensagem própria. O Gemini e a impressão (no máximo 6 páginas) têm seus próprios limites.
- A classificação "é conta de energia?" depende do modelo. O servidor só rejeita quando o modelo diz que não é, ou
  quando nada identificável foi lido. Um documento adulterado ou uma foto de outra conta de energia (de outro
  cliente) passa; quem barra o erro é a **conferência humana**, obrigatória antes de salvar.
- O conteúdo do arquivo é interpretado por um modelo: um documento pode conter texto que tente instruir a IA
  (injeção de prompt). A saída é restringida por esquema e conferida por uma pessoa; não há outra defesa.
- **A imagem da conta sai para a API do Google.** Confirme que o plano e os termos usados atendem à política da
  empresa: planos pagos e Vertex AI têm termos de retenção diferentes da cota gratuita. Nada neste repositório
  controla isso.
- Corrigido em 2026-10-10: imagem com dimensões acima de 40 milhões de pixels é recusada no upload, lendo só o
  cabeçalho (sem decodificar), antes de o Pillow decodificar em `prepare_for_model`.

**Dados**

- O que a retenção apaga é só o arquivo original. `imports.extracted` guarda a resposta bruta da IA (inclui
  `customer_name` e `customer_address`) por tempo indeterminado, e o nome do arquivo e o hash ficam em
  `documents`.
- A auditoria é mantida sem prazo de expurgo; contém IPs reais e nomes de usuário.
- O banco guarda valores, consumo e dados de unidades **sem cifra de coluna**. Só o arquivo original e o segredo
  TOTP são cifrados.
- Sem escopo por loja (todos os perfis logados veem todas as lojas e documentos).
- **Backups**: configure e teste a restauração do PostgreSQL; o Railway não faz isso por você. O *dump* contém os
  arquivos cifrados; a chave não deve ficar junto.

**Auditoria**

- Truncamento do final da cadeia não é detectável sem o selo final guardado fora do sistema.
- Quem tem acesso ao ambiente (variáveis) e ao banco consegue refazer a cadeia.
- A tela mostra 300 eventos e o CSV 20 mil; eventos mais antigos só existem no banco.
- Em SQLite (desenvolvimento) a escrita da cadeia não é serializada.

**Processo**

- `pip-audit` não bloqueia o CI; a revisão das dependências é manual.
- O código nunca foi submetido a teste de invasão independente. Os testes automatizados de segurança estão em
  `tests/test_security.py`, `tests/test_2fa_audit.py`, `tests/test_temp_password.py`,
  `tests/test_reject_non_bill.py` e `tests/test_roles.py`.

---

## Onde isso vive no código

| Assunto | Arquivo |
|---|---|
| Hash e política de senha, senha provisória, sessão, dependências de perfil, CSRF, IP real, pseudonimização | `app/security.py` |
| Login, bloqueio, 2FA no login, troca de senha, revogação | `app/services/auth_service.py`, `app/routes/auth.py`, `app/routes/account.py` |
| TOTP, códigos de recuperação | `app/services/totp_service.py`; reset por script em `scripts/reset_2fa.py` |
| Cabeçalhos, CSP, CSRF de origem, rate limit, limite de corpo | `app/middleware.py` |
| Validação de configuração | `app/startup_checks.py`, `app/main.py` (`create_app`), `app/seed.py` (admin inicial) |
| Configuração e variáveis | `app/config/__init__.py`, `railway.env.example`, `.env.example` |
| Auditoria e cadeia | `app/services/audit_service.py`, `app/models/audit.py`, `app/routes/admin.py` |
| Criptografia de documentos | `app/services/crypto_service.py`, `app/models/document.py` |
| Upload | `app/utils/uploads.py`, `app/utils/images.py`, `app/services/import_service.py` |
| Gemini e disjuntor | `app/services/gemini_service.py`, `app/services/circuit_breaker.py`, `app/utils/log_safety.py` |
| Retenção | `app/services/retention_service.py`, `scripts/purge_documents.py` |
| Entrega de documentos | `app/routes/documents.py` |

## Variáveis de ambiente de segurança

| Variável | Padrão | Efeito |
|---|---|---|
| `DEBUG` | `false` | `true` desliga as exigências de produção (nunca em produção) |
| `SECRET_KEY` | vazio | assina a sessão; base da chave da auditoria e da pseudonimização se `PSEUDONYM_KEY` vazia; mín. 32 caracteres |
| `PSEUDONYM_KEY` | vazio | chave da cadeia de auditoria e do HMAC do nome digitado; cai em `SECRET_KEY` |
| `DOCUMENT_ENCRYPTION_KEY` | vazio | chaves Fernet separadas por vírgula; obrigatória em produção |
| `DATABASE_URL` | `sqlite:///app.db` | em produção precisa ser PostgreSQL |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / vazio | criam o primeiro administrador se o banco não tem usuários |
| `REQUIRE_ADMIN_2FA` | `false` | obriga 2FA aos administradores |
| `TRUSTED_PROXY_COUNT` | `1` | proxies à frente do app |
| `MAX_LOGIN_ATTEMPTS` / `LOGIN_BLOCK_MINUTES` | `5` / `15` | bloqueio por tentativas |
| `TEMP_PASSWORD_HOURS` / `TEMP_MAX_LOGIN_ATTEMPTS` | `48` / `3` | senha provisória |
| `SESSION_IDLE_MINUTES` / `SESSION_MAX_HOURS` | `60` / `12` | expiração da sessão |
| `MIN_PASSWORD_LENGTH` | `8` | tamanho mínimo da senha pessoal |
| `RATE_LIMIT_ENABLED` | `true` | liga o limite de requisições |
| `CSRF_ALLOWED_ORIGINS` | vazio | origens extras aceitas em mutações |
| `MAX_UPLOAD_MB` | `12` | limite do upload |
| `GEMINI_API_KEY` / `GEMINI_MODEL` / `GEMINI_MAX_CONCURRENCY` | vazio / `gemini-3.5-flash-lite` / `2` | leitura por IA |
| `DOCUMENT_RETENTION_DAYS` / `RETENTION_CHECK_HOURS` | `183` / `6` | retenção dos originais |
