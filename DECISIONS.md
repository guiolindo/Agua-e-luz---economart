# Decisões — registro histórico

Decisões que exigiram discussão: contexto, o que foi escolhido e por quê. Serve para ninguém precisar
redescobrir o motivo meses depois. Do mais antigo para o mais novo.

---

## 1. A folha da loja segue a planilha original ✅

**Contexto.** O projeto nasceu para substituir a planilha "ENERGIA — GRÁFICO POR LOJA": uma tabela-resumo da loja
por fornecedor e, abaixo, um gráfico por conta (unidade consumidora) com Valor da Fatura, Dias de Consumo e Variação %.
Quem fazia a planilha concatenava à mão, com fórmulas, os dados lançados no sistema da empresa.

**Decisão.** A folha impressa mantém toda a informação da planilha e acrescenta melhorias por cima (média por mês,
percentual do total, composição, custo por kWh), sem remover nada. No modo padrão (`by=sheet`, "Como na planilha"):
o **resumo** agrupa pelo **mês de vencimento** e o **gráfico por conta** pelo **mês de referência**. Os outros modos
(`due`, `reference`) existem para análise.

**Garantia.** `tests/test_report_sheet.py` confere os totais da planilha ao centavo, incluindo o total final 496.587,37.
Qualquer mudança no agrupamento precisa manter esse teste verde.

## 2. Lançamento manual vale sempre pelo mês de referência ✅

**Contexto.** Despesas sem conta de distribuidora (manutenção e combustível do gerador, LL Energia, meses antigos de
antes do sistema) são lançadas à mão: o usuário escolhe a loja, o tipo, o mês de referência e o valor.
Surgiu a dúvida: na tabela por vencimento, o gerador entra pelo vencimento ou pela data de contabilização?

**O que foi tentado (2026-10-10).** (a) vencimento, senão contabilização; (b) contabilização, senão vencimento,
com um campo novo "Data de contabilização" e a migração 0003.

**Decisão final.** Voltar ao comportamento original: o lançamento manual vale **só** pelo mês de referência escolhido,
em todas as tabelas e painéis. O campo "Vencimento" continua existindo, apenas para consulta. Quem fazia a planilha
escolhia o mês de referência e o valor já aparecia no gráfico; não havia outra data.

**Consequência.** A regra está em `chart_service` e `executive_service` (`month_of(r.reference, None, by)` nos lançamentos
manuais). Se a empresa decidir um dia usar outra data, é uma troca localizada nesses dois pontos.

## 3. A revisão 0003 do Alembic permanece, vazia ✅

**Contexto.** A migração 0003 (coluna `manual_records.accounting_date`) chegou a ser aplicada no banco de produção.
Depois a funcionalidade foi abandonada (decisão 2) e o arquivo da migração foi apagado.

**Incidente (2026-10-10).** A produção parou de subir com `Can't locate revision identified by '0003'`:
o banco guardava a revisão 0003 e o Alembic não a encontrava mais no repositório.

**Decisão.** Manter `migrations/versions/0003_manual_accounting_date.py` como migração **sem alterações de esquema**.
A coluna que ficou em bancos que já a tinham é nula e não é usada. Há um teste
(`test_revisions_already_applied_in_production_stay_in_the_chain`) que impede remover revisões aplicadas.

**Regra.** Nunca apagar uma revisão que já passou por produção. Para desfazer uma funcionalidade, criar uma migração nova
ou manter a antiga vazia.

## 4. Alembic, com adoção segura de bancos existentes ✅

**Contexto.** O sistema começou com `create_all` e `ensure_columns`. Era preciso migrações versionadas sem perder dados
do banco de produção já em uso.

**Decisão.** Baseline `0001` representa o esquema anterior. Na primeira subida de um banco sem `alembic_version`,
`app/db_migrate.py` cria o que faltar, completa colunas e carimba a revisão certa sem alterar dados. As migrações são
idempotentes (conferem se a coluna ou tabela já existe). Os testes usam `create_all`; `RUN_MIGRATIONS=true` é o padrão em produção.

**Limite conhecido.** A adoção foi testada nos testes automáticos com SQLite. Em produção (Postgres), o sistema subiu com
Alembic e voltou ao normal após a correção da decisão 3. O roteiro de restauração de backup nunca foi ensaiado.

## 5. 2FA só para administrador, e auditoria à prova de adulteração ✅

**Contexto.** Paridade de segurança com o sistema Notas-despesas, usado como referência.

**Decisão.** TOTP (Google Authenticator) para administradores, com `REQUIRE_ADMIN_2FA` para tornar obrigatório e
`scripts/reset_2fa.py` para quem perdeu o celular. A auditoria grava cada evento em cadeia (HMAC com `prev_hash`/`row_hash`,
trava de consulta no Postgres) e a tela de Auditoria tem "Verificar integridade", que mostra o selo final.
O IP real é gravado sem anonimizar; o nome digitado em login falho é pseudonimizado.

## 6. Arquivo que não é conta de energia é barrado e apagado ✅

**Contexto.** Qualquer pessoa pode enviar um PDF ou foto aleatória.

**Decisão.** O Gemini devolve um campo `is_energy_bill`. Se for falso, o servidor também confere os campos extraídos,
rejeita a importação e apaga os bytes do arquivo. Um arquivo já barrado não volta ao Gemini. Se o Google estiver fora do ar,
um disjuntor (circuit breaker) faz o sistema falhar rápido em vez de esperar timeouts.

**Limite conhecido.** A rejeição foi testada com respostas simuladas; ainda não com o Gemini real e arquivos não relacionados.

## 7. "Maior alta" e "maior queda" só quando existem ✅

**Contexto.** No painel da diretoria, com uma loja só, ou quando todas subiram, o cartão "Maior queda" mostrava uma
alta (↑ 3,12% em vermelho).

**Decisão.** Alta considera apenas variações positivas e queda apenas negativas; sem nenhuma, o cartão mostra "—".
O mesmo vale para as frases de destaque do painel.

## 8. Telas profissionais, sem tom de assistente ✅

**Decisão.** Textos curtos e específicos, uma paleta única definida em `:root` (azul da marca, laranja de destaque,
verde/âmbar/vermelho só para estado). Animações discretas: abertura do login com a logo nascendo do gráfico, splash curto
após o login, despedida no logout; tudo desligado na impressão. Nada de frases genéricas como "resumo em poucas palavras".

## 9. Fora do escopo por enquanto (itens 10 e 11 abaixo são ideias futuras)

- Importar o relatório TXT do ERP e conciliar com as faturas.
- Integração direta com o banco Oracle do ERP.
- Alertas por e-mail.

Foram discutidos e deixados para depois de a diretoria decidir se o projeto continua. O foco é o fluxo principal:
foto → conferência → salvar → folha impressa.

## 10. Módulo de água (futuro, só se a diretoria aprovar) 📝 REGISTRADO

**Contexto.** O repositório se chama `Agua-e-luz---economart` porque a expectativa é que, se o projeto for aprovado,
o sistema passe a atender também as contas de água. Hoje ele é só de energia. A Economart tem cerca de 20 lojas em MG e BA
(mais 3 a 4 em implantação), 3 centros de distribuição e escritórios em Ribeirão das Neves, Belo Horizonte e Salvador.

**O que já serve para água sem mudança:** lojas, unidades, lançamento manual, documentos e importação, auditoria, 2FA,
usuários e perfis, relatórios por mês, CSV, impressão, ranking, variação e composição.

**O que é específico de energia e precisaria evoluir:**
- Fornecedores (CEMIG, COELBA, Energisa etc.): entrariam as concessionárias de água.
- Campos técnicos da conta: consumo e demanda em ponta e fora de ponta, demanda contratada, R$/kWh. Em água importam m³,
  hidrômetro e faixa tarifária.
- A leitura por IA e a rejeição de arquivos (`is_energy_bill`) precisam de uma versão para conta de água.
- Alertas: no lugar de "demanda acima da contratada" e "R$/kWh fora do padrão", viriam consumo acima do padrão e
  suspeita de vazamento.
- Textos de ajuda, títulos, folha impressa e nomes internos (`energy_bills`, `consumption_hfp`, `demand_hfp`).

**Caminho sugerido.**
1. Módulo de água simples: valor, vencimento e consumo em m³ por hidrômetro, usando o lançamento manual e a
   importação atuais. Cabe em dias.
2. Se houver demanda, extração completa da conta de água, alertas próprios e painel adaptado. É um projeto maior,
   e aí vale generalizar `energy_bills` para uma tabela de contas de serviço com tipo (luz, água).

## 11. Escolha de módulo (Luz ou Água) depois do login 📝 IDEIA

**Ideia.** Depois do login, uma tela pergunta qual módulo a pessoa quer abrir: **Luz** ou **Água**. Ao escolher, todo o
sistema passa a mostrar só aquele módulo (painel, contas, lojas, alertas, ajuda). Há uma opção para voltar à escolha de módulos.

**Identidade visual (login).** Manter o gráfico subindo como elemento principal e, ao fundo, de forma bem discreta,
chuva escorrendo de um lado e faíscas de raio do outro, para representar água e luz juntas. Sem chamar mais atenção do que o
gráfico e a logo; desligado em `prefers-reduced-motion` e na impressão.

**Condição.** Só faz sentido quando o módulo de água existir (decisão 10). Antes disso, mostrar uma escolha com um módulo só
seria um passo a mais para o usuário.

## 12. Pesquisa de evolução (2026-10-10) e o que foi adotado ✅

**Contexto.** Uma IA de pesquisa avaliou o sistema contra boas práticas de gestão de contas de energia (ISO 50006, ANEEL,
IBM Envizi, EnergyCAP e outros). Conclusão: o núcleo já é de um produto profissional; o maior ganho está em explicar os
números e controlar o fechamento, não em acrescentar gráficos.

**Adotado antes da apresentação (baixo risco):**
- "R$/kWh" passou a se chamar **custo efetivo por kWh** (total da conta ÷ kWh, com demanda, impostos e multas).
- **Nota metodológica** no painel e na planilha: competência, mês incompleto, mercado livre, demanda e limite dos destaques.
- **Tolerância de 5% na demanda** (REN ANEEL 1.000/2021, Grupo A). Entre 100% e 105% o alerta é de baixa gravidade e
  não afirma cobrança; acima de 105% diz que costuma haver cobrança e manda conferir a fatura. O texto antigo ("há cobrança de
  ultrapassagem" a partir de 100%) podia afirmar uma cobrança que não existe. O valor da multa (2× ou 3× a tarifa) não foi
  confirmado no texto oficial e não aparece no sistema.

**Roadmap depois da aprovação:** ver [`docs/ROADMAP.md`](docs/ROADMAP.md).


## 13. Pentest interno (2026-10-10): achados e correções ✅

**Contexto.** Pedido explícito do usuário: "Faça tudo pra melhorar segurança. E tente fazer um pentest no sistema."
Revisão em duas frentes: um agente leu o código de ponta a ponta (autorização, CSRF, injeção, upload, configuração) e,
em paralelo, foram feitos testes reais contra uma cópia local do sistema (banco separado, dados fictícios) — nunca a
produção. **O que rodou ao vivo:** matriz de autorização por perfil (admin, funcionário, diretoria, consulta) em todas as
rotas GET e POST, e POST sem token CSRF em todas as rotas de escrita. **O que foi confirmado só por leitura de código, não
por ataque real:** tentativa de contornar o limite de login com `X-Forwarded-For` forjado e com variação de maiúsculas
(o script de força bruta que eu escreveria foi interrompido antes de rodar e não foi refeito), enumeração de usuários,
injeção (SQL/XSS/fórmula), upload e configuração. Esses itens vêm da leitura do agente revisor e da minha, mais os testes
automatizados; não houve teste de invasão com ferramenta externa.

**Achados corrigidos** (com teste em `tests/test_security_hardening.py`; ressalva: o incremento atômico do contador de
tentativas **não tem teste de concorrência real** — só confirma que o bloqueio continua funcionando como antes. A correção
é a forma padrão de fechar essa classe de falha, mas não foi reproduzida em duas conexões simultâneas ao Postgres):

1. **[Alta] Bloqueio de conta por condição de corrida.** `user.failed_attempts = (user.failed_attempts or 0) + 1` lia,
   somava em Python e gravava — duas tentativas de login ao mesmo tempo podiam partir do mesmo valor e uma delas "sumir".
   Na senha provisória de 4 dígitos (bloqueia na 3ª tentativa errada), isso permitia muito mais que 3 palpites reais antes
   do bloqueio valer. Corrigido com `UPDATE ... SET failed_attempts = failed_attempts + 1` (atômico no banco; em
   produção/Postgres o próprio UPDATE serializa tentativas concorrentes pela trava de linha). Mesma correção na tabela de
   usuários inexistentes (`LoginThrottle`) e no contador de erros do código do 2FA.
2. **[Média] Bloqueio de conta sem recuperação — mitigado, não eliminado.** Qualquer um bloqueia uma conta alheia só de errar a senha 5 vezes; se
   for o único administrador, ninguém mais consegue desbloquear pela interface. Isso é inerente a qualquer política de
   bloqueio por tentativas (a alternativa, não bloquear, é pior). Mitigação: `python -m scripts.unlock_user <usuario>`,
   para quem tem acesso ao servidor.
3. **[Média] Limite de tamanho do envio não contava sem `Content-Length`.** O corte de requisições grandes só olhava o
   cabeçalho declarado; sem ele (ou em pedaços, "chunked"), o valor ficava em 0 e nada era cortado — um envio sem login
   (ex.: `POST /login`) podia ser usado para derrubar o servidor com um corpo gigante. `BodySizeLimitMiddleware` virou um
   middleware ASGI puro que conta os bytes conforme chegam, não mais só o que o cliente declarou.
4. **[Média] `/documents/{id}` mostrava qualquer documento para qualquer perfil logado por id sequencial**, inclusive
   fotos ainda em conferência (antes de confirmar a conta) e de contas já excluídas, cujo arquivo também não era
   apagado. Agora: documento de conta confirmada continua visível a todos (necessário para imprimir a conta com a foto);
   documento ainda em revisão só é visível a quem lança contas; excluir a conta apaga o arquivo quando nenhuma outra
   conta ainda o referencia.
5. **[Baixa] Bomba de descompressão de imagem e contagem de páginas de PDF por regex.** Uma imagem pequena em bytes mas
   com dimensões absurdas (ex.: 20000×20000) decodificava centenas de MB de memória antes de qualquer checagem; um PDF
   com páginas em formato comprimido escapava da busca por `/Type /Page` nos bytes crus. Corrigido: dimensões lidas do
   cabeçalho (sem decodificar) e rejeitadas acima de 40 milhões de pixels; páginas contadas pelo mesmo leitor (pypdfium2)
   que abre o arquivo depois.
6. **[Baixa] HTML injection armazenada no painel da diretoria** via `innerHTML` com o código da loja (ex.: criar uma loja
   com código contendo uma tag `<a>`). A CSP já impedia executar script, mas um link ou conteúdo forjado aparecia na
   tela. Corrigido com escape antes de montar o HTML.
7. **[Baixa] Conta desativada era distinguível por tempo e comportamento.** Pulava a verificação de senha (mais rápida)
   e nunca mostrava "bloqueado" mesmo após várias tentativas — diferente de uma senha errada comum, o que permitia
   inventariar quais contas foram desativadas. Agora gasta o mesmo tempo (`verify_dummy`) e conta como falha igual.
8. **[Baixa] Ações de privilégio de administrador sem segunda confirmação (parcial).** Quem tinha uma sessão de admin (mesmo com
   2FA) conseguia sozinho criar outro admin, promover alguém a admin ou tirar o 2FA de outro admin — uma sessão
   sequestrada virava posse de todos os admins. Agora essas três ações pedem a senha de quem está fazendo a ação
   (confirmação simples por `prompt()`, sem redesenho de tela). **Ficou de fora:** redefinir a senha de outro
   administrador, que ainda não pede confirmação.
9. **[Informativa] `Admin` e `admin` podiam coexistir** (comparação de usuário sensível a maiúsculas). A checagem de
   usuário duplicado na criação passou a ser por `lower(username)`.
10. **[Informativa] Nome de arquivo com acento quebrava o download** (`Content-Disposition` só aceita Latin-1). Corrigido
    com `filename*=UTF-8''...` (RFC 6266), mantendo um nome em ASCII como alternativa.

**Verificado e já estava correto** (não mudou): autorização por perfil em todas as rotas, CSRF em toda mutação, só ORM
nas consultas (sem injeção de SQL), autoescape do Jinja, injeção de fórmula em CSV/XLSX já neutralizada, sessão com
revogação por época, senha com scrypt e tempo constante, 2FA sem bypass no fluxo `pre2fa`, IP real resistente a
`X-Forwarded-For` forjado, variação de maiúsculas não contorna o bloqueio de conta real.

**Risco aceito, não corrigido agora:**
- `SECRET_KEY` assina a sessão e também deriva a chave da cadeia de auditoria; `DOCUMENT_ENCRYPTION_KEY` cifra
  documentos e segredos TOTP. Chaves separadas reduziriam o raio de um vazamento, mas é uma mudança de configuração em
  produção (rotação de chave), não só de código — fica para depois da apresentação.
  CI com `pip-audit` sem bloquear o build (continua como alerta, decisão 2026-10-08) e sem pin de versão das
  dependências — mudar isso agora arrisca travar o CI por algo sem relação com o trabalho desta sessão, perto da
  apresentação.
- `.github/workflows/ci.yml` ganhou um bloco `permissions: contents: read` (reduz o escopo padrão do token do CI);
  o resto (pins de ação por SHA, pip-audit bloqueante) fica para depois.
