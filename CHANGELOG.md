# Changelog

Histórico do sistema, do mais novo para o mais antigo, agrupado por dia. Cada item corresponde a commits em
`ccr-9b4b2f9b-4bk1nd`. O motivo das decisões maiores está em [`DECISIONS.md`](DECISIONS.md).

## 2026-10-10

- **Revisão de UX e ajuste do fluxo de assinatura.** Percurso por tarefa nos três perfis (funcionário, diretoria, consulta), em notebook 1356x640 e celular 390x800, 14 telas do funcionário: nenhuma página com erro, nenhum erro de JavaScript, sem rolagem lateral (exceto a folha da loja na tela, corrigida). Achados e correções: (1) o caminho para imprimir era difícil de achar: o *Painel* ganhou o cartão **Últimas contas lançadas** com o botão *Imprimir p/ assinatura* (na coluna da direita, para a pendência continuar à vista); (2) a folha da loja na tela rolava a página inteira para o lado: agora rola dentro do cartão; (3) o link solto "CSV" da lista de contas virou "Baixar CSV"; (4) a **Ajuda** ganhou a seção "Imprimir para o diretor assinar" (e o atalho na caixa inicial do funcionário) e o **TUTORIAL.md** ganhou o fluxo no capítulo B6 e no checklist. Ainda aberto: a lista de Contas no celular é uma tabela larga (os botões ficam fora da tela, é preciso rolar para o lado) e não mostra qual conta já foi impressa.

- **Imprimir para assinatura: folha da loja + conta original num clique.** No fluxo original, a pessoa imprimia a conta de luz e a folha da loja ("ENERGIA — GRÁFICO POR LOJA") para o diretor conferir e assinar a nota; no sistema o botão *Imprimir* das contas abria outra coisa (dados e gráficos só da conta). Agora o botão principal é **Imprimir para assinatura** (lista de contas, ficha da unidade e, logo depois de salvar uma conta, na ficha da loja): imprime a folha da loja em A4 paisagem e, em seguida, cada página da conta original em A4 retrato (foto ou PDF de até 6 páginas), sem trocar de papel à mão (`@page` nomeada). O antigo virou *Relatório da conta*, com texto explicando o que é. Aceita desmarcar "Incluir a conta original". Conta lançada manualmente (sem arquivo) imprime só a folha. Verificado em PDF: foto = 2 páginas (paisagem + retrato); PDF de 2 páginas = 3 páginas.

- **Bateria com o Gemini real (chave gratuita temporária, só documentos fictícios).** 16 arquivos: 4 contas (CEMIG, Coelba, Energisa, CEMIG G&T), 4 variantes difíceis (foto girada 90°, baixa resolução, PDF de 2 páginas, foto escura e borrada) e 7 que não são conta (cardápio, conta de água, boleto, contrato, página em branco, rosto, paisagem). **Resultado: 14 de 16.** As 4 contas e o PDF saíram com todos os campos certos; os 7 não-conta foram barrados, com o motivo ("Cardápio de pizzaria") e sem inventar valor. Fluxo completo pelo sistema (upload, leitura, conferência, salvar, gráfico) OK em 4-6 s; 6 envios simultâneos ficaram prontos em até 19 s (fila de 2 em 2). Limite do plano gratuito (429): mensagem clara e disjuntor abriu como esperado. **Falhas e correções:** (1) foto muito ruim (escura+borrada+girada) gerou consumo e demanda errados com confiança 0,7-0,9: agora o prompt manda devolver null para número não nítido, e a conferência avisa quando o custo por kWh sai fora de R$ 0,10-3,00 ou a demanda está muito longe da contratada (`plausibility_warnings`); (2) chave inválida aparecia como "arquivo inválido" (o Google responde HTTP 400, não 401): agora diz "A chave da API do Gemini é inválida ou foi revogada"; (3) "5.000 kWh" lido como 5,0 em uma rodada: o prompt ganhou regra explícita do ponto de milhar; (4) número com muitos zeros seguidos perdeu um zero (UC `4000000001` lida `400000001`): o prompt manda contar os dígitos, e a conferência/cadastro de unidade mostra o número lido. Não prova acerto nas contas reais: use pelo menos uma conta real de cada fornecedor. Scripts em `scripts/gemini_battery/`.

- **Ajustes após revisão externa.** Apresentação: textos mais precisos ("com o mínimo de digitação", "a visão executiva da empresa", 2FA "disponível para os administradores"), **modo Resumo** de 8 slides (botão no topo ou tecla `R`; link `#r1`), zoom que devolve e prende o foco, sem papéis ARIA de aba. Painel da diretoria: a seleção de lojas do gráfico de evolução ganhou busca, *Top 5*, *Todas*, *Limpar* e contador (30+ lojas). Medição com 100 lojas e 2.297 contas: painel ~0,5-0,7 s, XLSX ~1,1 s. O restante da revisão (fila de trabalho, ciclo de alertas, lote, qualidade dos dados) está no `docs/ROADMAP.md`.

- **Telas baixas e celular (achados do uso real em notebook 1366x768).** (1) Rodapé do menu lateral (*Apresentação do sistema*, usuário, *Sair*) agora fica fixo embaixo, sem precisar rolar, e o menu fica mais compacto em janelas baixas. (2) O gráfico da tela de entrada não some mais em notebooks: encolhe para caber (só some abaixo de 500 px de altura). (3) Corrigida uma rolagem lateral no celular nas telas de painel, lojas e contas (texto invisível `.sr` escapava do recorte da tabela). (4) A apresentação ganhou ajustes para janelas de ~600 px de altura (menos texto em volta, telas maiores). Verificado em 1356x600, 1280x600, 1366x768, 1920x1080, 2560x1300, 1024x700, 768x1000 e 390x760.

- **Apresentação do sistema (`/apresentacao`), com acabamento de design.** Botão *Apresentação do sistema* no rodapé do menu lateral, para qualquer perfil logado. Abre 25 slides em tela cheia (cerca de 4 min no modo automático): capa animada, **comparador antes × depois** da folha de cada loja (arraste para comparar), os 4 passos, o sistema em números, o **layout responsivo para celular** (3 telas em moldura de aparelho), o fluxo do funcionário (painel, importar, conferir com pontos numerados sobre a tela, salvar, ficha da loja, folha impressa, lançamento manual, contas, alertas), a diretoria (painel, gráficos, evolução, impressão A4/A3, planilha XLSX), a tela de consulta e a segurança. Tipografia própria (Bricolage Grotesque + Inter, locais), fundo animado, títulos que sobem em máscara, cascata de entrada, telas com inclinação 3D, cortina entre capítulos, contadores, **passar sozinho (P)**, tela cheia (F), zoom nas imagens, teclado/toque e layout de celular; respeita *reduzir movimento*. A tela de administrador não aparece. **Tudo é fictício**: lojas L01-L08 e CD01, cliente "Empresa Exemplo"; a "planilha antiga" é uma ilustração gerada com os mesmos números do sistema (nenhuma foto nem dado real). **Some sozinha:** o botão e a página param de existir às 17h de sexta, 16/10/2026 (Brasília), por `PRESENTATION_UNTIL` (ISO 8601; vazio desliga; para estender, troque o valor).

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
