# Segurança

O sistema guarda dados da empresa (valores de contas, consumo, unidades, fotos de documentos). Este arquivo descreve o
que está implementado, como configurar em produção e o que ainda é risco residual. Referência de práticas: o repositório
`Notas-despesas` (auditoria set/2026).

## Controles implementados

| Área | Controle |
|---|---|
| **Acesso** | Todas as páginas e APIs exigem login (única exceção: `/login`, `/health`, `/static`). |
| **Senhas** | scrypt (N=2^15) com sal; hashes antigos são atualizados no login. Política: ≥8 caracteres (≥12 para o admin inicial), mistura de classes, sem senhas comuns nem o nome de usuário. Tempo de verificação igualado quando o usuário não existe. |
| **Força bruta** | 5 falhas → conta bloqueada 15 min; 10 tentativas de login/min por IP (429). Credencial errada, usuário inexistente e conta inativa mostram a mesma mensagem; o bloqueio mostra "bloqueado por excesso de tentativas" e vale igual para usuário inexistente (tabela `login_throttle`), então não revela se a conta existe). |
| **Sessão** | Cookie assinado `HttpOnly`, `SameSite=Strict`, `Secure` em produção; expira por **inatividade (60 min)** e por **duração máxima (12 h)**; recriada a cada login (anti *session fixation*). **Logout, troca de senha, desativação e mudança de perfil revogam as sessões** (época por usuário), inclusive cookies copiados. |
| **2FA (administrador)** | TOTP (RFC 6238) com **Google Authenticator**/Authy: o admin ativa em *Verificação em 2 etapas* (QR code + 8 códigos de recuperação de uso único). Com 2FA ativo, a senha sozinha não cria sessão; o código vale uma vez (anti-replay), tolera ±30 s, o segredo fica cifrado no banco e erros contam para o bloqueio de conta (a senha certa não zera o contador). `REQUIRE_ADMIN_2FA=true` obriga todo admin a configurar. Perdeu o celular: outro admin usa *Redefinir 2FA*; se for o único admin, `python -m scripts.reset_2fa <usuario>` no servidor. |
| **Senha provisória** | Usuário novo ou senha redefinida pelo admin recebe **4 dígitos** (sorteados, sem padrões como 0000/1234), exibidos **uma única vez**. Por ser fraca de propósito (uso interno, só para o 1º acesso), tem salvaguardas: **vale 48 h** (`TEMP_PASSWORD_HOURS`), **só permite trocar a senha** e a conta **bloqueia na 3ª tentativa errada** (`TEMP_MAX_LOGIN_ATTEMPTS`). A senha pessoal que a pessoa cria continua exigente (≥8 caracteres, letras + números). |
| **Perfis** | `admin` (cria/gerencia usuários e perfis, auditoria), `operator` = funcionário (responsável por toda a gestão de energia: lojas, unidades, tipos, contas, lançamentos, exclusões — tudo auditado), `director` (painel executivo, só consulta), `viewer` (só consulta e imprime). O painel da diretoria é restrito a `director` e `admin`. Aplicado no servidor em todas as rotas de escrita (botões escondidos são só conveniência). Não permite remover o último administrador. |
| **CSRF** | Token por sessão + checagem de `Origin`/`Sec-Fetch-Site` em toda mutação + cookie `SameSite=Strict`. |
| **XSS** | CSP com **nonce por resposta** (`script-src 'self' 'nonce-…'`, sem `unsafe-inline` em script, `object-src 'none'`, `frame-ancestors 'self'`), sem handlers inline, Jinja com autoescape, Chart.js servido localmente (sem CDN). |
| **Cabeçalhos** | `nosniff`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP, HSTS em produção, `Cache-Control: no-store` em tudo que não é estático (nada de dados da empresa no cache do navegador). |
| **Uploads** | Extensão **e** conteúdo real (magic bytes), limite de tamanho (corte antes do parse multipart), PDF ≤ 10 páginas, nome sanitizado; imagens servidas com CSP `sandbox` e `nosniff`. |
| **Dados em repouso** | Fotos/PDFs **criptografados** no banco (Fernet) com `DOCUMENT_ENCRYPTION_KEY` (rotação por várias chaves) e **apagados após 6 meses**. |
| **Auditoria / LGPD** | `/admin/audit`: logins, falhas, bloqueios, trocas de senha, alterações de dados. O IP de origem é gravado em claro (uso em máquinas corporativas); o usuário digitado em login falho continua **pseudonimizado** (HMAC). |
| **Auditoria à prova de adulteração** | Cada evento leva um selo HMAC encadeado ao anterior (`prev_hash`/`row_hash`, chave derivada de `SECRET_KEY`/`PSEUDONYM_KEY`). Editar, apagar no meio ou inserir evento direto no banco quebra a cadeia; *Verificar integridade* em `/admin/audit` aponta o primeiro evento adulterado. Eventos anteriores à atualização ficam como "não verificáveis". Não troque `SECRET_KEY` sem exportar a auditoria antes: a chave nova não valida os selos antigos. Limite: apagar só os últimos eventos não quebra elo; anote o *selo final* mostrado na verificação. |
| **Segredos** | Chave do Gemini só em variável de ambiente e redigida de qualquer log. Em produção o servidor **se recusa a iniciar** com `SECRET_KEY` fraca, sem `DOCUMENT_ENCRYPTION_KEY`, com SQLite ou com `ADMIN_PASSWORD` fraca. |
| **Rede** | Limite de requisições (login, upload, documentos, API, mutações), limite de corpo, IP real lido do **fim** do `X-Forwarded-For` (`TRUSTED_PROXY_COUNT`), docs/OpenAPI desativados, erros 500 sem detalhes. |

## Configuração obrigatória em produção (Railway)

`DEBUG=false`, `SECRET_KEY` (≥32 caracteres), `DOCUMENT_ENCRYPTION_KEY`, `DATABASE_URL` (PostgreSQL), `ADMIN_PASSWORD` (≥12) —
veja `railway.env.example`. **Guarde a `DOCUMENT_ENCRYPTION_KEY` em um cofre de senhas**: sem ela, os arquivos já gravados não
abrem (os dados lidos das contas continuam). Para rotacionar: `DOCUMENT_ENCRYPTION_KEY=<nova>,<antiga>`.

Depois do primeiro acesso: troque a senha do admin, crie os usuários reais (perfil mais restrito possível) e confira
*Auditoria*.

## Risco residual (não implementado)

- **2FA só para administradores** (os demais perfis entram com senha). Estenda a outros perfis se o risco justificar.
- **Limite de requisições em memória por processo:** vale para 1 instância (Railway padrão). Com várias instâncias, usar Redis.
- **Sessão em cookie assinado** (não criptografado): não guarda dados sensíveis, apenas ids; a revogação é feita por época no banco.
- **Sem recuperação de senha por e-mail:** o admin redefine (de propósito: sem canal de e-mail a proteger).
- **Backups:** configure e **teste a restauração** do PostgreSQL (Railway não faz isso por você).
- **Dependências:** `pip-audit` roda no CI como alerta (não bloqueia). Revise periodicamente.
- **Fotos enviadas ao Gemini:** a imagem da conta sai para a API do Google. Confirme que o plano/termos usados atendem à política da empresa
  (planos pagos/Vertex AI têm termos de retenção diferentes da cota gratuita).
