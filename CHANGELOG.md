# Changelog

Histórico do sistema, do mais novo para o mais antigo, agrupado por dia. Cada item corresponde a commits em
`ccr-9b4b2f9b-4bk1nd`. O motivo das decisões maiores está em [`DECISIONS.md`](DECISIONS.md).

## 2026-10-13

- **Lojas numa tela só (UX).** O item de menu separado "Lojas da empresa" deixava duas telas de lojas. Agora tudo fica em **Lojas**: o administrador vê o botão **Importar lista de lojas** (que vira *Atualizar lista de lojas* depois da primeira carga) e, no topo da mesma tela, o cartão laranja para vincular as lojas criadas antes da lista, com a sugestão já marcada. Importar e vincular voltam para Lojas. O aviso no Painel leva para lá.

- **Lojas da empresa: colunas com os nomes certos e Drogamart sem número de filial.** As colunas são empresa, filial (número da loja), código C5, nome, CNPJ, inscrição estadual, inscrição municipal, CEP e endereço; o código C5 fica guardado como `c5`. A Drogamart não tem número de filial: com a coluna vazia ou repetindo o C5, a loja recebe o nome da empresa como código (`DROGAMART — Matriz`). Carregar a lista de novo acha a loja oficial pelo CNPJ quando o código mudou (a Drogamart carregada antes como 246774 vira DROGAMART, com 246774 como apelido), sem criar loja duplicada.

- **Lojas da empresa (lista oficial).** Novo menu do administrador, **Lojas da empresa**: cola-se a planilha de lojas (empresa, número, código interno, nome, CNPJ, inscrição estadual e municipal, CEP, endereço, com os títulos dos blocos), o sistema mostra a conferência e carrega. A UF sai do CEP (reserva: endereço e título do bloco); o leitor aceita colunas vazias, "-" como vazio, nome e CNPJ sem TAB entre eles e texto colado sem TAB. Carregar de novo atualiza pelo número, sem duplicar nem apagar. Lojas criadas antes da lista aparecem num aviso para o administrador (Painel e Lojas) e são **vinculadas** à loja oficial com confirmação: pontos de energia (com as contas), lançamentos manuais e importações passam para ela, o código e o nome antigos viram apelidos, registrado na auditoria. Com a lista carregada, o funcionário escolhe a loja e não cria loja nova (o administrador inclui); listas de lojas em ordem numérica (6, 7, 10, 24...). Loja sem conta continua fora do Painel executivo. Migração 0004 (colunas novas em `stores`, anuláveis). Testado com a lista real: 34 lojas (18 MG, 15 BA, 1 PE), sem erro.

- **Botão "Apresentação do sistema" brilha até ser aberto.** Quem ainda não abriu a apresentação naquele navegador vê o botão com borda laranja e uma luz passando de um lado para o outro. Depois que clica (ou abre a apresentação pelo link), o brilho some naquele navegador (`localStorage`; sem armazenamento, continua brilhando). Quem pediu menos movimento no sistema operacional vê só a borda laranja.

- **Brilho do botão mais chamativo.** Enquanto não foi aberto, o botão fica laranja sólido, com um halo laranja pulsando e a luz branca passando a cada 2 segundos. Com menos movimento pedido, fica só laranja, parado.

## 2026-10-12

- **Imprimir para assinatura: dois botões e um trabalho só, sem esticar.** A tela tinha cinco botões para a mesma coisa (*Imprimir tudo*, *Só a folha*, *Só a conta original*, *Tudo no mesmo trabalho*, a caixa *Incluir a conta original*), tudo por causa do problema da conta esticada. Agora são dois: **Imprimir relatório + conta** e **Só o relatório**. A causa: a impressora aplica UMA orientação a todo o trabalho, então uma conta em pé num trabalho com a folha deitada saía deitada e espremida. A solução: o trabalho inteiro sai em **A4 deitado** (a orientação do relatório) e cada página da conta que é em pé vai **girada 90°** pelo servidor (`/documents/{id}/pages/{n}.png?rot=1`, foto ou PDF), ocupando a folha inteira na proporção original. No papel, é só virar a folha: a conta fica em pé, do jeito que ela é; conta deitada sai deitada. É o mesmo que um leitor de PDF faz com páginas mistas. Na tela, a conta continua aparecendo em pé. Verificado no navegador gerando o PDF da impressão: foto em pé, foto deitada, PDF misto e o PDF real da CEMIG GT; todas as páginas A4 deitadas, nenhuma esticada.

## 2026-10-11

- **"Painel da diretoria" agora se chama "Painel executivo".** O nome antigo soava estranho e se repetia demais. Trocado no menu, nas telas, na Ajuda, no TUTORIAL, nos documentos, na planilha, na apresentação do sistema e no PowerPoint (capa "Visão executiva"; o nome não se repete nos slides). A rota continua `/diretoria` e o perfil continua "Diretoria". Entradas antigas deste histórico mantêm o nome da época.

- **Apresentação do sistema atualizada (27 slides).** Dois slides novos: *Folha e conta num só clique* (imprimir para assinatura, com a tela real) e *O painel vira PowerPoint* (slide gerado pelo próprio sistema). Slide da planilha reescrito em tópicos curtos e o contador "5 abas" virou "3 jeitos de levar o painel: papel, planilha e PowerPoint". Imagens da diretoria refeitas com o nome novo. O modo Resumo continua com 8 slides.

- **Lista de Contas no celular em cartões.** Era o defeito visível que restava da revisão de UX: no celular (até 800 px) a tabela era larga e os botões ficavam fora da tela. Agora cada conta é um cartão: loja e valor no alto, unidade e fornecedor, vencimento e origem, e os botões (*Imprimir para assinatura*, *Relatório da conta*, *Editar*) embaixo. No computador nada muda. Verificado em 390, 700 e 1356 px: sem rolagem lateral, sem erro de JavaScript.

## 2026-10-10

- **Apresentação em PowerPoint (.pptx) do painel da diretoria.** Botão **Baixar apresentação** no Painel da diretoria (`/diretoria/export.pptx`, mesmos filtros da tela, só diretoria e administrador, registrado na auditoria). Gera um deck 16:9 no visual do modo apresentação do sistema (azul-marinho, laranja, barras de energia na capa e no fim): capa, destaques em frases com 4 indicadores, gasto por mês e fornecedor, ranking de lojas, maiores altas e quedas, custo por kWh, pendências, e **um slide por loja** (até 60) com indicadores e a evolução mensal. Gráficos **nativos e editáveis** do PowerPoint, **transição suave** e **entrada em cascata** em todos os slides, notas do apresentador nos destaques. Só usa números que o painel já calcula. Validado contra o esquema OOXML e renderizado: 9 lojas = 18 slides (159 KB); 100 lojas = 69 slides (622 KB) em 1,4 s. Nova dependência: `python-pptx`. **Ajuda** completada: imprimir A4/A3, baixar planilha e apresentação, limites do envio (12 MB, 10 páginas, um arquivo por vez), uso no celular e botão da apresentação do sistema.

- **"Imprimir tudo" num clique, em dois trabalhos seguidos.** O botão laranja da tela *Folha para assinatura* imprime a folha da loja (paisagem) e, assim que a impressão fecha, abre sozinho a conta original (`/impressao/original/{id}`, foto ou PDF em ~190 dpi, na orientação da 1ª página, sem esticar) já com a impressão aberta. Cada trabalho tem UMA orientação, que é o que impressoras e drivers aceitam; o "tudo no mesmo trabalho" antigo continua como botão pequeno. *Só a folha* e *Só a conta original* também existem. Verificado no navegador com a impressão simulada: clique, 1º trabalho só com a folha, navegação automática, 2º trabalho em 1 página retrato (foto em pé) e 2 páginas retrato (PDF de 2 páginas).

- **Imprimir para assinatura em dois trabalhos de impressão (conta original do jeito que ela é).** O usuário reportou que, na impressão, as páginas da conta saíam deitadas e esticadas. O PDF salvo por ele estava correto (retrato, proporção preservada), então o problema está na impressão física/prévia, onde impressoras e drivers costumam aplicar UMA orientação a todo o trabalho (folha deitada + conta em pé no mesmo trabalho não é confiável). Solução que não depende disso: a tela da folha agora tem **1 · Imprimir a folha da loja** (só a folha, paisagem) e **2 · Imprimir a conta original** (abre o PDF original no leitor do navegador, ou a foto numa página própria, `/impressao/original/{id}`, na orientação dela). O modo antigo continua como *Tudo junto*. Verificado em PDF: folha = 1 página paisagem; foto em pé = 1 página retrato; foto deitada = 1 página paisagem.

- **Imprimir para assinatura: páginas de PDF mais nítidas.** Conferido num PDF real impresso pelo usuário (CEMIG Geração e Transmissão, 2 páginas): a folha saiu em paisagem e as contas em retrato, com a imagem na proporção exata (950x1348 px na caixa 544x770 pt, razão 0,706 = 0,707; nada esticado). Como a página do PDF virava imagem de ~115 dpi e era ampliada até A4, o texto saía macio; a impressão agora pede a página em ~190 dpi (`?hq=1`), a conferência na tela continua leve.

- **Imprimir para assinatura: a conta original sai na proporção e na orientação dela.** A folha da loja continua na primeira página, em paisagem. Cada página da conta original agora usa a **própria orientação** (foto ou PDF em pé = página em pé; foto deitada = página deitada; PDF com páginas mistas também) e a imagem tem largura e altura automáticas com limite em mm, **sem esticar nem espremer** (antes, o limite de altura podia deformar uma conta em pé numa página deitada). A orientação vem do tamanho real da página do PDF e do tamanho exibido da foto (a rotação EXIF de foto de celular é considerada). Verificado em PDF: foto em pé = folha paisagem + página retrato (proporção 0,75); foto deitada = duas páginas paisagem (proporção 1,6, igual à da foto); PDF misto = paisagem, retrato, paisagem. Se a impressora forçar uma única orientação, a conta ainda sai na proporção certa, só menor.

- **Menos rolagem lateral nas tabelas (notebook).** A tabela *Contas* da ficha da unidade passava da tela em 1366x768 (com os botões *Documento original*, *Imprimir para assinatura*, *Relatório da conta*, *Editar* e *Excluir*): os botões agora quebram em duas linhas e as colunas secundárias (Dias, Origem, Demanda) somem em telas estreitas. O *Resumo mensal* da loja, o *Comparativo* e o mapa de calor da diretoria ficaram mais justos (colunas e letras menores) e, abaixo de 1300 px, o menu lateral encolhe um pouco. Verificado em 1356 e 1280 px em 13 telas de administrador: nenhuma tabela rola para o lado.

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
