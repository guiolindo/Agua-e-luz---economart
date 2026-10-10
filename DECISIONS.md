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

## 9. Fora do escopo por enquanto

- Importar o relatório TXT do ERP e conciliar com as faturas.
- Integração direta com o banco Oracle do ERP.
- Alertas por e-mail.

Foram discutidos e deixados para depois de a diretoria decidir se o projeto continua. O foco é o fluxo principal:
foto → conferência → salvar → folha impressa.
