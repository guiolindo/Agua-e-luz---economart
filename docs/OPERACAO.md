# Manual de operação

Para quem mantém o sistema no ar (administrador de TI). O uso do dia a dia está na *Ajuda* dentro do sistema; segurança em `SECURITY.md`.

## Variáveis obrigatórias no Railway
`DEBUG=false`, `SECRET_KEY` (≥32 caracteres), `DOCUMENT_ENCRYPTION_KEY`, `DATABASE_URL` (PostgreSQL), `ADMIN_PASSWORD` (≥12), `GEMINI_API_KEY`.
Opcionais: `REQUIRE_ADMIN_2FA=true` (obriga 2FA aos administradores), `TRUSTED_PROXY_COUNT=1`.

## Verificação de saúde
`GET /health` devolve `ok` (200) quando o banco responde e `503` quando não. O Railway usa isso antes de promover um deploy.

## Backup e restauração (PostgreSQL)
1. Ative os backups automáticos do banco no Railway (aba do serviço PostgreSQL).
2. Backup manual: `pg_dump "$DATABASE_URL" -Fc -f economart-AAAA-MM-DD.dump`.
3. Restauração (em um banco de teste primeiro): `pg_restore --clean --no-owner -d "$DATABASE_URL_TESTE" economart-AAAA-MM-DD.dump`.
4. **Teste a restauração a cada trimestre.** Backup que nunca foi restaurado não é backup.
5. Os arquivos das contas (foto/PDF) ficam **cifrados dentro do banco**: o backup do banco os leva junto, mas só abrem com a `DOCUMENT_ENCRYPTION_KEY`. Guarde a chave em cofre de senhas, separada do backup.

## Mudanças no banco (migrações com Alembic)
- Ao subir, o sistema aplica sozinho as migrações pendentes (`RUN_MIGRATIONS=true`, o padrão). O banco já existente é **adotado** na primeira subida: o sistema completa colunas que faltem, carimba a revisão `0001` sem alterar dados e segue dali.
- Para alterar o esquema (nova coluna, tabela, índice): mude o modelo em `app/models/`, rode `alembic revision --autogenerate -m "o que mudou"`, **leia o arquivo gerado em `migrations/versions/`** e faça commit dele junto com a mudança. O teste `tests/test_migrations.py` falha se um modelo mudar sem migração.
- Conferir divergência (por exemplo depois de restaurar um backup): `python -c "from app import db_migrate; print(db_migrate.drift())"` — lista vazia significa banco em dia.
- Antes de uma migração em produção: faça um backup (seção acima).

## Chaves
- `DOCUMENT_ENCRYPTION_KEY`: para rotacionar use `nova,antiga` (a primeira cifra, todas decifram).
- `SECRET_KEY`: também assina o selo da auditoria. Trocá-la invalida a verificação dos eventos antigos. Antes de trocar: *Auditoria → Baixar CSV* e *Verificar integridade*, e guarde os dois resultados.

## Auditoria
- *Verificar integridade* aponta qualquer edição, remoção no meio ou inserção feita direto no banco.
- Anote o **selo final** de vez em quando: apagar só os últimos eventos não quebra a cadeia, e só essa cópia revela.
- *Baixar CSV* exporta até 20 mil eventos recentes.

## Incidentes comuns
| Situação | O que fazer |
|---|---|
| Usuário bloqueado por tentativas erradas | *Usuários → Desbloquear* |
| Esqueceu a senha | *Usuários → Redefinir senha* (senha provisória de 4 dígitos, 48 h) |
| Administrador perdeu o celular do 2FA | Use um código de recuperação; ou outro administrador clica em *Redefinir 2FA*; se for o único: `python -m scripts.reset_2fa <usuario>` no servidor |
| Gemini fora do ar | O sistema falha rápido por 30 s e volta sozinho; enquanto isso, use *Lançamento manual* |
| Suspeita de acesso indevido | *Auditoria*: filtre por "Senha incorreta" e "Conta bloqueada"; redefina as senhas envolvidas e confira *Verificar integridade* |
| Arquivo estranho enviado | É barrado e apagado automaticamente (aparece na auditoria como "Arquivo barrado") |

## Rotina
| Quando | Tarefa |
|---|---|
| Mensal | Conferir a auditoria e os usuários ativos; desativar quem saiu |
| Trimestral | Testar a restauração do backup; revisar `pip-audit` (roda no CI) |
| Anual | Rotacionar `DOCUMENT_ENCRYPTION_KEY` e as senhas de administrador |

## Limites conhecidos
- Limite de requisições em memória por processo: vale para 1 instância (padrão do Railway).
- 2FA só para administradores.
