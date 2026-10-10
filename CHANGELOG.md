# Changelog

Histórico do sistema, do mais novo para o mais antigo, agrupado por dia. Cada item corresponde a commits em
`ccr-9b4b2f9b-4bk1nd`. O motivo das decisões maiores está em [`DECISIONS.md`](DECISIONS.md).

## 2026-10-10

- **Painel da diretoria: dá para saber qual loja é qual.** Os gráficos mostravam só o código (ex.: "CD300"); agora os gráficos de barras mostram "CÓDIGO · Nome" (ex.: "CD300 · CD Ribeirão das Neves"), o gráfico de evolução impresso ganhou legenda (antes as linhas ficavam sem nome), o mapa de calor mostra o nome ao passar o mouse e o relatório impresso termina com a *Legenda das lojas* (código, nome e estado). No A3, o gráfico de composição, que é o mais estreito, usa só o código.

- **Impressão do painel da diretoria reorganizada, com escolha de papel:** o botão *Imprimir painel* abre **A4 · várias páginas** (4 páginas A4 paisagem, uma ideia por página: resumo e indicadores · desempenho · custos e demanda · detalhe e pendências) ou **A3 · uma folha só** (grade de 12 colunas: resumo no alto, gráficos lado a lado, tabelas embaixo). Nenhum gráfico é cortado; tabelas longas passam de página repetindo o cabeçalho. Antes eram 6 páginas A4, a última só com a nota. No A3, até ~18 lojas cabem numa folha; acima disso o painel segue numa 2ª folha A3 (folha 1 com o resumo e os gráficos, folha 2 com as tabelas). O bloco "Comparar duas lojas" (interativo) não imprime.

- **Pentest interno:** 1 achado alto, 3 médios, 4 baixos, corrigidos ou mitigados (bloqueio de conta por condição de corrida,
  limite de envio sem Content-Length, documentos visíveis além da conta, confirmação de senha para ações de admin,
  entre outros). Ver `DECISIONS.md` §13.

- **Planilhas em XLSX formatado:** o painel da diretoria baixa um arquivo com 5 abas (Resumo, Lojas, Mês a mês, Fornecedores, Pendências), com a identidade da marca, valores como número/moeda, mapa de calor, totais, filtros, cabeçalho congelado e configuração de impressão. A lista de Contas também ganhou XLSX. O CSV continua disponível (link "CSV" em Contas).
- Revisão de linguagem no painel da diretoria: pluralização correta, "maior participação no gasto", "pode gerar cobrança por ultrapassagem", valor em R$ junto do percentual nos cartões de alta e queda, selo "Top 15" nos rankings; sem a linha "Conexão protegida · acesso monitorado" no login.

- **Corrigido:** a produção não subia (`Can't locate revision identified by '0003'`). A revisão 0003 voltou como migração vazia; teste impede nova remoção.
- Corrigido: excluir uma conta vinda de importação dava erro no Postgres (a importação ainda apontava para ela).
- Despesas manuais valem só pelo mês de referência (a data de contabilização foi tentada e abandonada).
- Painel da diretoria: botão "Alterar filtros" visível; "maior queda" só aparece quando houve queda.
- Auditoria: filtro de evento em barra visível, com "Limpar filtro" e contagem.
- Folha da loja idêntica à planilha original ao centavo, com média por mês, % do total, composição e custo por kWh somados.
- Central de Alertas: cada conta é comparada com o histórico da própria unidade (migração 0002).
- Documentação reorganizada em `docs/`, mais `AGENTS.md`, `DECISIONS.md`, `CHANGELOG.md`, `CREDITS.md`.

## 2026-10-09

- Ficha executiva da loja para a diretoria (ranking, custo por kWh, demanda, destaques).
- Interior com a mesma linguagem do login: faixa de abertura, números que contam, entrada escalonada.
- Painel da diretoria impresso em A4 paisagem, com cabeçalho de relatório.
- Painel da diretoria: ano contra ano, lojas fora do próprio padrão, planilha, copiar resumo.
- Logout com animação de despedida; login com a logo nascendo do gráfico, painel de vidro e splash de abertura.
- Login e 2FA redesenhados: campos com ícones, aviso de Caps Lock, estados de erro.

## 2026-10-08

- Migrações com Alembic: baseline, adoção de bancos existentes, teste anti-divergência.
- `/health` verifica o banco; auditoria exportável em CSV; manual de operação; tabelas viram cartões no celular.
- 2FA (TOTP) para administradores e auditoria com cadeia de integridade; IP real na auditoria.
- Disjuntor (circuit breaker) para quedas do Gemini.
- Importação barra arquivos que não são conta de energia e apaga os bytes.
- Ajuda por perfil (administrador, funcionário, diretoria, consulta), com FAQ e glossário.
- Contas: exportar CSV, busca e filtros recolhidos; auditoria legível.
- Textos mais enxutos e paleta unificada; títulos específicos nos painéis.
- Lançamento manual em lote (LL Energia em várias lojas); botão Desbloquear em Usuários; escolher o tipo antes de abrir o formulário.
- Energisa como distribuidora; CEMIG Geração e Transmissão passa a ser conta lida por foto.
- Imprimir conta com a foto ou PDF original incluído.
- Senha mínima de 8 caracteres; login diferencia "incorretos" de "bloqueado".

## 2026-10-07

- Tela "Contas": lista única para achar e abrir qualquer nota.
- Mobile dedicado: barra superior, gaveta, navegação inferior e botão de importar.
- Identidade visual Economart: cores, logo, favicon, nova tela de login, ícones no menu, animações sutis.
- Horário de Brasília em toda a exibição.

## Antes de 2026-10-07

Primeira versão: importar a foto da conta, leitura pelo Gemini, conferência, histórico e gráficos por loja.
