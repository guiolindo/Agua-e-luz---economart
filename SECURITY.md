# Segurança

> Versão resumida. O detalhamento de cada mecanismo, os endpoints e os limites conhecidos estão em [`docs/security.md`](docs/security.md).

O sistema guarda dados da empresa (valores de contas, consumo, unidades, fotos de documentos). Este arquivo descreve o
que está implementado, como configurar em produção e o que ainda é risco residual. Referência de práticas: o repositório
`Notas-despesas` (auditoria set/2026).

## Controles implementados

| Área | Controle |
|---|---|
| **Acesso** | Todas as páginas e APIs exigem login (única exceção: `/login`, `/health`, `/static`). |
| **Senhas** | scrypt (N=2^15) com sal; hashes antigos são atualizados no login. Política: ≥8 caracteres (≥12 para o admin inicial), mistura de classes, sem senhas comuns nem o nome de usuário. Tempo de verificação igualado quando o usuário não existe. |
| **Força bruta** | 5 falhas → conta bloqueada 15 min (aumento do contador é atômico no banco, não corre risco de "perder" tentativas concorrentes); 10 tentativas de login/min por IP (429). Credencial errada, usuário inexistente e conta inativa mostram a mesma mensagem, o mesmo tempo de resposta e o mesmo bloqueio após N tentativas (tabela `login_throttle` para inexistentes), então nada denuncia se a conta existe ou foi desativada. Recuperação se o único admin se bloquear sozinho: `python -m scripts.unlock_user <usuario>`. |
| **Sessão** | Cookie assinado `HttpOnly`, `SameSite=Strict`, `Secure` em produção; expira por **inatividade (60 min)** e por **duração máxima (12 h)**; recriada a cada login (anti *session fixation*). **Logout, troca de senha, desativação e mudança de perfil revogam as sessões** (época por usuário), inclusive cookies copiados. |
| **2FA (administrador)** | TOTP (RFC 6238) com **Google Authenticator**/Authy: o admin ativa em *Verificação em 2 etapas* (QR code + 8 códigos de recuperação de uso único). Com 2FA ativo, a senha sozinha não cria sessão; o código vale uma vez (anti-replay), tolera ±30 s, o segredo fica cifrado no banco e erros contam para o bloqueio de conta (a senha certa não zera o contador). `REQUIRE_ADMIN_2FA=true` obriga todo admin a configurar. Perdeu o celular: outro admin usa *Redefinir 2FA*; se for o único admin, `python -m scripts.reset_2fa <usuario>` no servidor. |
| **Senha provisória** | Usuário novo ou senha redefinida pelo admin recebe **4 dígitos** (sorteados, sem padrões como 0000/1234), exibidos **uma única vez**. Por ser fraca de propósito (uso interno, só para o 1º acesso), tem salvaguardas: **vale 48 h** (`TEMP_PASSWORD_HOURS`), **só permite trocar a senha** e a conta **bloqueia na 3ª tentativa errada** (`TEMP_MAX_LOGIN_ATTEMPTS`). A senha pessoal que a pessoa cria continua exigente (≥8 caracteres, letras + números). |
| **Perfis** | `admin` (cria/gerencia usuários e perfis, auditoria), `operator` = funcionário (responsável por toda a gestão de energia: lojas, unidades, tipos, contas, lançamentos, exclusões — tudo auditado), `director` (painel executivo, só consulta), `viewer` (só consulta e imprime). O painel da diretoria é restrito a `director` e `admin`. Aplicado no servidor em todas as rotas de escrita (botões escondidos são só conveniência). Não permite remover o último administrador. **Criar outro administrador, promover alguém a administrador ou tirar o 2FA de outro administrador pede a sua própria senha de novo** (confirmação por `prompt()`), para uma sessão de admin sequestrada não conseguir sozinha empoderar outra conta. |
| **CSRF** | Token por sessão + checagem de `Origin`/`Sec-Fetch-Site` em toda mutação + cookie `SameSite=Strict`. |
| **XSS** | CSP com **nonce por resposta** (`script-src 'self' 'nonce-…'`, sem `unsafe-inline` em script, `object-src 'none'`, `frame-ancestors 'self'`), sem handlers inline, Jinja com autoescape, Chart.js servido localmente (sem CDN). |
| **Cabeçalhos** | `nosniff`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP, HSTS em produção, `Cache-Control: no-store` em tudo que não é estático (nada de dados da empresa no cache do navegador). |
| **Uploads** | Extensão **e** conteúdo real (magic bytes); limite de tamanho aplicado nos bytes recebidos (não só no cabeçalho `Content-Length`, que um envio sem ele ou mentiroso contornaria); PDF ≤ 10 páginas contadas pelo mesmo leitor que abre o arquivo depois (não por busca de texto nos bytes crus, que um PDF com páginas comprimidas escaparia); imagem com dimensões absurdas é recusada antes de decodificar os pixels (bomba de descompressão; JPEG até 120 milhões de pixels, que cobre câmeras de 108 MP, e PNG/WEBP até 40 milhões); nome sanitizado; imagens servidas com CSP `sandbox` e `nosniff`. |
| **Dados em repouso** | Fotos/PDFs **criptografados** no banco (Fernet) com `DOCUMENT_ENCRYPTION_KEY` (rotação por várias chaves) e **apagados após 183 dias** (`DOCUMENT_RETENTION_DAYS`). Também apagados na hora se a conta vinculada for excluída e nenhuma outra conta ainda usar o mesmo arquivo. Uma foto/PDF ainda em conferência (antes de a conta ser confirmada) só é visível para quem lança contas; depois de confirmada, qualquer perfil logado pode ver (ex.: imprimir a conta com a foto). |
| **Auditoria / LGPD** | `/admin/audit`: logins, falhas, bloqueios, trocas de senha, alterações de dados. Nos eventos de segurança (login, falha, bloqueio, logout, troca da própria senha, 2FA próprio) o IP de origem é gravado em claro (uso em máquinas corporativas); ações do administrador e eventos de dados não levam IP. O usuário digitado em login falho continua **pseudonimizado** (HMAC). |
| **Auditoria à prova de adulteração** | Cada evento leva um selo HMAC encadeado ao anterior (`prev_hash`/`row_hash`, chave derivada de `SECRET_KEY`/`PSEUDONYM_KEY`). Editar, apagar no meio ou inserir evento direto no banco quebra a cadeia; *Verificar integridade* em `/admin/audit` aponta o primeiro evento adulterado. Eventos anteriores à atualização ficam como "não verificáveis". Não troque `SECRET_KEY` sem exportar a auditoria antes: a chave nova não valida os selos antigos. Limite: apagar só os últimos eventos não quebra elo; anote o *selo final* mostrado na verificação. |
| **Segredos** | Chave do Gemini só em variável de ambiente e redigida de qualquer log. Em produção o servidor **se recusa a iniciar** com `SECRET_KEY` fraca, sem `DOCUMENT_ENCRYPTION_KEY`, ou com SQLite. A senha do primeiro administrador (`ADMIN_PASSWORD`) é validada quando ainda não existe nenhum usuário no banco; depois disso a variável é ignorada. |
| **Rede** | Limite de requisições (login, upload, documentos, API, mutações), limite de corpo contado no fluxo da requisição (não só pelo cabeçalho declarado), IP real lido do **fim** do `X-Forwarded-For` (`TRUSTED_PROXY_COUNT`), docs/OpenAPI desativados, erros 500 sem detalhes. |

## Configuração obrigatória em produção (Railway)

`DEBUG=false`, `SECRET_KEY` (≥32 caracteres), `DOCUMENT_ENCRYPTION_KEY`, `DATABASE_URL` (PostgreSQL), `ADMIN_PASSWORD` (≥12) —
veja `railway.env.example`. **Guarde a `DOCUMENT_ENCRYPTION_KEY` em um cofre de senhas**: sem ela, os arquivos já gravados não
abrem (os dados lidos das contas continuam). Para rotacionar: `DOCUMENT_ENCRYPTION_KEY=<nova>,<antiga>`.

Depois do primeiro acesso: troque a senha do admin, crie os usuários reais (perfil mais restrito possível) e confira
*Auditoria*.

## Revisão de segurança interna (2026-10-10)

Revisão própria (leitura do código + testes de ataque contra uma cópia local, nunca a produção): 1 achado alto, 3 médios,
4 baixos. Corrigidos, com teste (`tests/test_security_hardening.py`), com duas ressalvas: o bloqueio de conta abusado
por terceiros continua possível (mitigado pelo script de desbloqueio) e a confirmação de senha cobre só criar admin,
promover a admin e tirar o 2FA de outro admin (não cobre redefinir a senha de outro admin). Os principais:
- **Bloqueio de conta contornável por condição de corrida:** o contador de tentativas erradas usava "ler, somar 1 em
  Python, gravar", e duas tentativas ao mesmo tempo podiam "perder" uma delas — na senha provisória de 4 dígitos
  (bloqueia na 3ª tentativa) isso reduzia bastante a proteção real. Agora o incremento é uma operação atômica no banco.
- **Limite de tamanho do envio não valia sem o cabeçalho `Content-Length`:** um envio sem autenticação, em pedaços
  (`chunked`), não era cortado. Agora os bytes são contados conforme chegam.
- **Foto/PDF ainda em conferência era visível para qualquer perfil logado por id sequencial**, inclusive de contas
  excluídas (o arquivo não era apagado). Agora só quem lança contas vê antes da confirmação, e o arquivo é apagado ao
  excluir a conta (quando nenhuma outra a usa).
- **Criar ou promover um administrador, e tirar o 2FA de outro administrador, não pedia nada além da sessão já aberta**
  — uma sessão de admin sequestrada virava posse de todos os admins. Agora pede a senha de quem está fazendo a ação.
- Contador de PDF por regex nos bytes crus (um PDF com páginas comprimidas escapava do limite de 10 páginas) e
  decodificação de imagem sem limite de pixels (bomba de descompressão). Corrigidos.
- Conta desativada respondia mais rápido e nunca mostrava "bloqueado", diferente de uma senha errada comum —
  dava para descobrir por fora quais contas foram desativadas. Agora o comportamento é igual.

Ver `DECISIONS.md` §13 para a lista completa e o que ficou como risco aceito (ex.: um bloqueio de conta sempre pode ser
usado para negar acesso a alguém que sabe o nome de usuário; isso é inerente a qualquer política de bloqueio, não um bug
deste sistema — por isso existe `scripts/unlock_user.py` para o único admin se destravar).

## Risco residual (não implementado)

- **2FA só para administradores** (os demais perfis entram com senha). Estenda a outros perfis se o risco justificar.
- **Limite de requisições em memória por processo:** vale para 1 instância (Railway padrão). Com várias instâncias, usar Redis.
- **Sessão em cookie assinado** (não criptografado): não guarda dados sensíveis, apenas ids; a revogação é feita por época no banco.
- **Sem recuperação de senha por e-mail:** o admin redefine (de propósito: sem canal de e-mail a proteger).
- **Backups:** configure e **teste a restauração** do PostgreSQL (Railway não faz isso por você).
- **Dependências:** `pip-audit` roda no CI como alerta (não bloqueia). Revise periodicamente.
- **Fotos enviadas ao Gemini:** a imagem da conta sai para a API do Google. Confirme que o plano/termos usados atendem à política da empresa
  (planos pagos/Vertex AI têm termos de retenção diferentes da cota gratuita).
