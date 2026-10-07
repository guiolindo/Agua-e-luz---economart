# Segurança

O sistema guarda dados da empresa (valores de contas, consumo, unidades, fotos de documentos). Este arquivo descreve o
que está implementado, como configurar em produção e o que ainda é risco residual. Referência de práticas: o repositório
`Notas-despesas` (auditoria set/2026).

## Controles implementados

| Área | Controle |
|---|---|
| **Acesso** | Todas as páginas e APIs exigem login (única exceção: `/login`, `/health`, `/static`). |
| **Senhas** | scrypt (N=2^15) com sal; hashes antigos são atualizados no login. Política: ≥10 caracteres (≥12 para o admin inicial), mistura de classes, sem senhas comuns nem o nome de usuário. Tempo de verificação igualado quando o usuário não existe. |
| **Força bruta** | 5 falhas → conta bloqueada 15 min; 10 tentativas de login/min por IP (429). Mensagem única para credencial errada, usuário inexistente, conta bloqueada ou inativa (não revela se a conta existe). |
| **Sessão** | Cookie assinado `HttpOnly`, `SameSite=Strict`, `Secure` em produção; expira por **inatividade (60 min)** e por **duração máxima (12 h)**; recriada a cada login (anti *session fixation*). **Logout, troca de senha, desativação e mudança de perfil revogam as sessões** (época por usuário), inclusive cookies copiados. |
| **Senha provisória** | Usuário novo ou senha redefinida pelo admin recebe **4 dígitos** (sorteados, sem padrões como 0000/1234), exibidos **uma única vez**. Por ser fraca de propósito (uso interno, só para o 1º acesso), tem salvaguardas: **vale 48 h** (`TEMP_PASSWORD_HOURS`), **só permite trocar a senha** e a conta **bloqueia na 3ª tentativa errada** (`TEMP_MAX_LOGIN_ATTEMPTS`). A senha pessoal que a pessoa cria continua exigente (≥10 caracteres, letras + números). |
| **Perfis** | `admin` (cria/gerencia usuários e perfis, auditoria), `operator` = funcionário (responsável por toda a gestão de energia: lojas, unidades, tipos, contas, lançamentos, exclusões — tudo auditado), `director` (painel executivo, só consulta), `viewer` (só consulta e imprime). O painel da diretoria é restrito a `director` e `admin`. Aplicado no servidor em todas as rotas de escrita (botões escondidos são só conveniência). Não permite remover o último administrador. |
| **CSRF** | Token por sessão + checagem de `Origin`/`Sec-Fetch-Site` em toda mutação + cookie `SameSite=Strict`. |
| **XSS** | CSP com **nonce por resposta** (`script-src 'self' 'nonce-…'`, sem `unsafe-inline` em script, `object-src 'none'`, `frame-ancestors 'self'`), sem handlers inline, Jinja com autoescape, Chart.js servido localmente (sem CDN). |
| **Cabeçalhos** | `nosniff`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP, HSTS em produção, `Cache-Control: no-store` em tudo que não é estático (nada de dados da empresa no cache do navegador). |
| **Uploads** | Extensão **e** conteúdo real (magic bytes), limite de tamanho (corte antes do parse multipart), PDF ≤ 10 páginas, nome sanitizado; imagens servidas com CSP `sandbox` e `nosniff`. |
| **Dados em repouso** | Fotos/PDFs **criptografados** no banco (Fernet) com `DOCUMENT_ENCRYPTION_KEY` (rotação por várias chaves) e **apagados após 6 meses**. |
| **Auditoria / LGPD** | `/admin/audit`: logins, falhas, bloqueios, trocas de senha, alterações de dados. IP e usuário digitado são gravados **pseudonimizados** (HMAC), nunca em claro. |
| **Segredos** | Chave do Gemini só em variável de ambiente e redigida de qualquer log. Em produção o servidor **se recusa a iniciar** com `SECRET_KEY` fraca, sem `DOCUMENT_ENCRYPTION_KEY`, com SQLite ou com `ADMIN_PASSWORD` fraca. |
| **Rede** | Limite de requisições (login, upload, documentos, API, mutações), limite de corpo, IP real lido do **fim** do `X-Forwarded-For` (`TRUSTED_PROXY_COUNT`), docs/OpenAPI desativados, erros 500 sem detalhes. |

## Configuração obrigatória em produção (Railway)

`DEBUG=false`, `SECRET_KEY` (≥32 caracteres), `DOCUMENT_ENCRYPTION_KEY`, `DATABASE_URL` (PostgreSQL), `ADMIN_PASSWORD` (≥12) —
veja `railway.env.example`. **Guarde a `DOCUMENT_ENCRYPTION_KEY` em um cofre de senhas**: sem ela, os arquivos já gravados não
abrem (os dados lidos das contas continuam). Para rotacionar: `DOCUMENT_ENCRYPTION_KEY=<nova>,<antiga>`.

Depois do primeiro acesso: troque a senha do admin, crie os usuários reais (perfil mais restrito possível) e confira
*Auditoria*.

## Risco residual (não implementado)

- **Sem 2FA/MFA.** Para dados financeiros, considere habilitar SSO/2FA na frente (ex.: Cloudflare Access) ou implementar TOTP.
- **Limite de requisições em memória por processo:** vale para 1 instância (Railway padrão). Com várias instâncias, usar Redis.
- **Sessão em cookie assinado** (não criptografado): não guarda dados sensíveis, apenas ids; a revogação é feita por época no banco.
- **Sem recuperação de senha por e-mail:** o admin redefine (de propósito: sem canal de e-mail a proteger).
- **Backups:** configure e **teste a restauração** do PostgreSQL (Railway não faz isso por você).
- **Dependências:** `pip-audit` roda no CI como alerta (não bloqueia). Revise periodicamente.
- **Fotos enviadas ao Gemini:** a imagem da conta sai para a API do Google. Confirme que o plano/termos usados atendem à política da empresa
  (planos pagos/Vertex AI têm termos de retenção diferentes da cota gratuita).
