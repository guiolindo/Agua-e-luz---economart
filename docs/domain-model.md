# Modelo de domínio

O que o sistema faz do ponto de vista do negócio: quem usa, o que é uma loja, uma unidade consumidora, uma
conta, um lançamento manual, como os meses são agrupados nos relatórios e quais avisos o sistema gera. Para a
estrutura técnica, ver [architecture.md](architecture.md) e [database.md](database.md).

Origem: o sistema substitui a planilha "ENERGIA — GRÁFICO POR LOJA" da Economart. A folha impressa da loja
reproduz essa planilha (ver [Folha da loja](#folha-da-loja)).

## Papéis

O papel fica em `users.role`. Valores aceitos na tela de usuários: `admin`, `operator`, `director`, `viewer`. O
valor `user` é legado e tem o mesmo efeito de `operator`. Quem cria o usuário é o administrador, que recebe uma senha
provisória de 4 dígitos, exibida uma única vez.

| Papel (tela) | Valor | Escrita | Painel da diretoria | Avisos de vencimento | Área administrativa |
|---|---|---|---|---|---|
| Administrador | `admin` | sim | sim | não | sim |
| Funcionário (operador) | `operator` (e `user`) | sim | não | sim | não |
| Diretoria | `director` | não | sim | não | não |
| Consulta | `viewer` | não | não | não | não |

Esses efeitos vêm das propriedades de `User` (`can_write`, `can_see_executive`, `gets_due_alerts`, `is_admin`) e
das dependências de `app/security.py`.

**Administrador.** Tudo o que o funcionário faz, mais: gestão de usuários (criar, redefinir senha, desbloquear,
mudar perfil, ativar/desativar, redefinir o 2FA de outro administrador), consulta e exportação da auditoria,
verificação de integridade da auditoria e configuração do próprio 2FA. Também vê o painel da diretoria. Não recebe
os avisos de vencimento. O sistema não deixa rebaixar ou desativar o último administrador ativo. Com
`REQUIRE_ADMIN_2FA=true`, o administrador sem 2FA é forçado a configurá-lo antes de usar o sistema; sem isso, só
aparece um aviso. O 2FA existe apenas para administradores.

**Funcionário (operador).** É quem cuida das contas: importa foto/PDF, confere e salva, faz lançamento manual e em
lote, cadastra e edita lojas, unidades (pontos de energia) e tipos de registro, exclui contas e lançamentos. É o
único papel que recebe os lembretes de vencimento (sino no menu e `/api/due`) e que pode marcar um vencimento
como tratado.

**Diretoria.** Acompanha. Ao entrar, é redirecionada de `/` para `/diretoria`. Vê o painel comparativo e pode
exportar o CSV dele; consulta lojas, histórico, folha impressa, lista de contas e Central de Alertas. Pode marcar
alertas como conferidos. Não importa, não lança e não edita. Não recebe os lembretes de vencimento.

**Consulta.** Só visualiza e imprime: lojas, histórico, folha, lista de contas, ficha da conta e Central de Alertas
(sem marcar como conferido). Não vê o painel da diretoria.

Observações verificadas no código:

- A criação e a edição de tipos de registro (`/types`) exigem perfil com escrita; portanto o funcionário também
  pode cadastrar tipos, não só o administrador.
- `/documents/{id}` (arquivo original) e a ficha de impressão exigem apenas estar logado; qualquer papel abre o
  original enquanto ele existir.
- Importação (`/import`), lançamento manual e em lote, cadastro de ponto e de loja exigem `writer_required`.

## Lojas, unidades consumidoras e tipos de registro

**Loja** (`stores`). Identificada por um `code` único (por exemplo `CD300`). Tem nome, localização, região
(UF, usada para comparar na diretoria), observações, apelidos (lista de textos, como "CD 300") e flag de ativa.
Os apelidos servem para resolver anotações escritas à mão na conta.

**Unidade consumidora** (`consumer_units`), chamada na interface de **ponto de energia**. É a instalação
que a distribuidora fatura. Pertence a uma loja; uma loja pode ter várias. O número é guardado como impresso
(`number`) e também normalizado, só com dígitos (`number_normalized`, único em todo o sistema): "12.060.073.018-19" e
"1206007301819" são a mesma unidade. É a chave usada para identificar a loja de uma conta importada. Pode ter
descrição, código interno, tipo de registro (a distribuidora), observações, ativa/inativa e o **dia de vencimento**
mensal (`due_day`, 1 a 31).

**Tipo de registro** (`record_types`). Define o que um lançamento é. Dois tipos (`kind`):

- `bill`: conta com leitura estruturada, vinculada a uma unidade consumidora; grava em `energy_bills`.
- `manual`: lançamento mensal com valor e campos numéricos próprios (`fields`), por loja; grava em
  `manual_records`.

Tipos criados na instalação (`app/seed.py`):

| Código | Nome | Tipo |
|---|---|---|
| `cemig` | CEMIG | conta (distribuidora) |
| `coelba` | COELBA | conta (distribuidora) |
| `energisa` | ENERGISA | conta (distribuidora) |
| `cemig-geracao` | CEMIG Geração e Transmissão | conta (compra de energia no mercado livre); campo extra `energia_kwh` |
| `ll-energia` | LL Energia | manual, só em lote; campo `consumo_kwh` |
| `ccee` | Câmara de Comercialização de Energia | manual; campo `energia_kwh` |
| `combustivel-gerador` | Compra de combustível para gerador | manual; campos `horas`, `litros` |
| `manutencao-gerador` | Manutenção de Gerador | manual; campo `ocorrencias` |

Cada tipo de conta tem nomes alternativos (`aliases`, por exemplo a razão social da distribuidora) que ajudam a
casar a distribuidora lida na conta com o tipo cadastrado (`type_for_utility`). `cemig-geracao` nasceu como
manual e hoje é conta; o `seed` converte bancos antigos, e os lançamentos manuais antigos dele continuam somando
nas tabelas e nos gráficos. Novos tipos são criados em `/types`. Um tipo `bill` novo não tem campos extras; um
tipo `manual` recebe os campos informados.

Um tipo manual pode ser "só em lote" (`is_batch_only`). Hoje isso é um conjunto fixo no código
(`BATCH_ONLY_TYPE_CODES = {"ll-energia"}`), não uma coluna do banco.

## Fatura de energia

`energy_bills` guarda uma conta de uma unidade em um mês de referência. Campos principais:

- **Identificação:** unidade, tipo de registro, `reference` (sempre dia 1 do mês), emissão, vencimento (`due_date`),
  número e série da nota fiscal, valor total (`total_value`, não pode ser negativo), `source` (`import` ou `manual`).
- **Leitura:** número de dias, datas de leitura anterior, atual e próxima.
- **Consumo:** ponta (`consumption_hp`), fora de ponta (`consumption_hfp`), horário reservado (`consumption_hr`) ou
  consumo único (`consumption_kwh`, baixa tensão). `consumption_total` soma ponta, fora de ponta e reservado quando
  existem; caso contrário usa o consumo único.
- **Demanda:** ponta, fora de ponta e contratada (kW).
- **Impostos e classificação:** PIS/COFINS e ICMS (R$), classe, subclasse, modalidade tarifária.
- **Itens faturados** (`line_items`, lista com descrição, quantidade, valor) e observações.
- **Origem:** documento original (se veio de importação) e usuário que criou/alterou.

Uma unidade deveria ter no máximo uma conta por mês e uma nota por número; o banco não impõe isso. A regra é do
aplicativo (`duplicate_service`): ao salvar, o sistema detecta mesma unidade e mesmo mês, ou mesma unidade e mesmo
número de nota, e pede a decisão ao usuário (substituir ou criar mais uma). Substituir regrava a conta mantendo o
antes/depois na auditoria.

Na importação, o Gemini lê os campos acima mais um nível de confiança (0 a 1) para unidade, mês, valor e datas.
Campos com confiança abaixo de 0,85 ficam destacados na tela de conferência. A IA não tem permissão de inventar:
campo ilegível volta vazio.

## Lançamento manual

`manual_records` guarda uma despesa mensal sem fatura estruturada (gerador, manutenção, LL Energia, CCEE) ou o
histórico antigo de um tipo que virou conta. Campos: loja, unidade (opcional), tipo, mês de referência, valor,
vencimento (opcional), campos numéricos do tipo (`data`, em JSON) e observações.

**Regra: o lançamento manual vale sempre pelo mês de referência.** Nos relatórios e no painel, qualquer
`ManualRecord` é posicionado pelo mês de `reference`, mesmo quando o relatório está agrupado por vencimento
(`month_of(r.reference, None, by)` em `chart_service`). O campo `due_date` do lançamento manual é apenas
informativo: aparece na lista de contas e no CSV, mas não desloca o valor de mês.

Ponto de atenção: isso vale para `ManualRecord`. A conta de distribuidora digitada à mão no formulário
(`/manual` com tipo de conta) é uma `EnergyBill` com `source = manual`, e o vencimento dela é um dado real:
no agrupamento por vencimento ela segue a regra das contas.

Duas formas de lançar:

- **Loja a loja** (`/manual`). Tipo de conta exige unidade; tipo manual exige loja, mês e valor.
- **Em lote** (`/manual/lote`). Um valor, um mês e uma lista de lojas ativas; grava um lançamento por loja, sem
  unidade. Se já existe lançamento daquele tipo, loja e mês, o sistema pergunta se pula ou substitui.

Qualquer lançamento pode ser editado ou excluído por quem tem escrita; as exclusões entram na auditoria.

## Pontos e pendências

"Ponto" é o ponto de energia, isto é, a unidade consumidora. Há três mecanismos que olham para eles.

**Cadastro rápido** (`/points/new`, `POST /points`). Pede loja, número da unidade, data de vencimento e
descrição. Se o número já existe, só atualiza o dia de vencimento (reabrindo o lembrete). O dia de vencimento
também é preenchido sozinho na primeira conta salva de uma unidade que ainda não tinha `due_day`.

**Lembretes de vencimento** (`due_service`, só funcionário). Cada ponto ativo de loja ativa com `due_day`
tem uma ocorrência por mês; em mês mais curto vale o último dia (dia 31 em fevereiro vira 28 ou 29). A ocorrência
mais recente aparece como "vence hoje" no dia, ou "venceu há N dias" por até 15 dias, até alguém marcar como
tratada (`consumer_units.due_ack`, ação "marcada como paga" na auditoria). A próxima ocorrência aparece como "vence
amanhã" ou "vence em N dias" nos 3 dias que a antecedem. Se existe uma conta lançada com aquele vencimento exato,
o valor é mostrado. Esses cálculos usam o fuso America/Sao_Paulo.

**Pendências do mês** (`dashboard_service.pending_items`, página inicial e painel da diretoria). Duas regras:

1. Unidade ativa, de loja ativa, cujo tipo é conta (ou sem tipo, tratando como o tipo de conta padrão) e que
   não tem conta com `reference` no mês: "Conta do mês não lançada".
2. Lançamento manual do mês anterior sem repetição neste mês (mesma loja, unidade e tipo), com o tipo ainda
   ativo: "Lançado no mês anterior; falta este mês". Não conta quando o tipo hoje é conta e a loja já tem conta
   daquele tipo no mês.

O mês mostrado na página inicial é o mais recente com algum dado, ou o escolhido no seletor. A página inicial
também lista até 8 unidades ativas sem dia de vencimento cadastrado.

## Agrupamento do relatório

Uma conta tem duas datas: o mês de referência (competência do consumo) e o vencimento, que costuma cair no mês
seguinte. Os relatórios podem agrupar por qualquer uma. A regra está em `chart_service.month_of`: por vencimento,
o registro entra no mês de `due_date`; se não tem `due_date`, cai no mês de referência.

A folha da loja (`/stores/{id}/report`) tem o parâmetro `by`, com três modos. O padrão é `sheet`; valores
desconhecidos viram `sheet`.

| Modo | Resumo mensal (todos os fornecedores) | Gráfico e tabela do imóvel (um fornecedor) |
|---|---|---|
| `sheet` | mês de vencimento | mês de referência |
| `due` | mês de vencimento | mês de vencimento |
| `reference` | mês de referência | mês de referência |

`sheet` reproduz a planilha impressa da Economart: o resumo soma pelo mês de vencimento e a tabela do imóvel
mostra o mês de referência da conta. Detalhes que valem para a folha:

- Lançamentos manuais sempre entram pelo mês de referência, em qualquer modo.
- Quando o resumo é por vencimento e o período final não foi informado, o fim avança um mês, porque o vencimento
  da última conta cai no mês seguinte. Meses vazios nas pontas são cortados.
- Na busca de registros por vencimento, o intervalo é ampliado em um mês para cada lado, para incluir contas cuja
  referência está fora do período mas vencem dentro dele.
- O período padrão são os 12 meses até o mês mais recente com dados, começando no primeiro mês com dados da loja
  se ele for posterior.
- Valores do mesmo mês e fornecedor são somados; a variação é percentual contra o mês anterior da série
  (arredondada a 2 casas, "—" quando não há base).

Os outros relatórios usam apenas uma das regras:

- **Painel da diretoria** (`/diretoria`): parâmetro `by` aceita `reference` (padrão) ou `due`. O modo `sheet` não
  existe nele.
- **Gráfico e histórico da loja** (`/api/stores/{id}/chart`, `/stores/{id}`): mês de referência.
- **Lista de contas** (`/notas`): filtro de período por mês de referência.
- **Alertas e pendências**: mês de referência.

## Folha da loja

É a página impressa que substitui a planilha. Traz: resumo mensal por fornecedor (com total, média por mês e
percentual de cada fornecedor), e para um fornecedor por vez (ou todos, com `all=1`) gráfico, variação mensal, tabela
por unidade, consumo, demanda fora de ponta, R$/kWh, dias de consumo, indicadores resumidos (total, média, maior e
menor mês, última variação) e dados da última conta.

**Equivalência com a planilha original.** `tests/test_report_sheet.py` carrega a loja CD300 de demonstração
(`scripts/seed_demo.py`) e confere, ao centavo, contra os valores da planilha:

- "Total geral" por mês de vencimento, janeiro a outubro de 2026: 47.458,41; 52.912,20; 44.564,10; 85.703,20;
  51.675,39; 46.157,01; 50.521,75; 50.304,35; 46.785,96; 20.505,00, com total final 496.587,37.
- "Valor da fatura" da CEMIG Distribuição por mês de referência, janeiro a setembro de 2026: 22.543,10; 19.560,38;
  24.144,83; 23.153,69; 16.959,69; 18.020,14; 18.835,58; 19.536,31; 20.505,00.
- "Dias de consumo": 31, 28, 31, 30, 31, 30, 31, 31, 30.
- Nos modos `reference` e `due` explícitos, o primeiro mês do "Total geral" é 47.172,26 e 47.458,41,
  respectivamente.

Regra do repositório: não alterar o resumo da folha sem rodar esse teste. A folha também acrescenta colunas
que a planilha não tinha (média e percentual por fornecedor, indicadores).

## Painel da diretoria

`executive_service.build` calcula, a partir de uma leitura de contas e outra de lançamentos manuais:

- total da empresa e por mês, por loja (com participação, média mensal, comparação com o período anterior de
  mesmo tamanho e variação contra o mês anterior);
- mix por tipo de registro e por loja;
- R$/kWh por loja (soma de valores e kWh das contas com consumo; `cemig-geracao` não entra nos kWh, porque a
  energia já aparece na conta da distribuição);
- uso da demanda contratada (demanda medida, a maior entre ponta e fora de ponta, dividida pela contratada) e
  quantidade de contas acima de 100%;
- comparação com o mesmo mês do ano anterior, só com as lojas que têm dado nos dois;
- frases de destaque (`insights`), que só afirmam o que os números sustentam.

Regras de proteção contra falso alarme: um mês é tratado como **parcial** se tem dado de menos de 60% das lojas em
relação ao mês mais completo do período, e o "mês em foco" é o último mês completo. Uma loja só é comparada com o
período anterior se teve pelo menos 3 meses de dado lá (ou o tamanho do período, se menor). Filtros: período, região
(UF da loja), tipos de registro e agrupamento por referência ou vencimento. Exporta o comparativo em CSV
(`/diretoria/export.csv`).

## Central de Alertas

`alert_service.compute` lê as contas dos últimos 10 meses, compara a conta mais recente de cada unidade com as
até 6 anteriores **da própria unidade** (mínimo 3 para comparar) e gera avisos. Só considera unidades e lojas
ativas, e só gera alerta se a conta mais recente tem referência dentro dos últimos 3 meses. Alerta é aviso para
conferir, não veredito: pode ser erro de leitura da IA ou fato real.

| Tipo (`kind`) | Regra | Gravidade |
|---|---|---|
| `valor` | Total da conta 30% ou mais acima da média das contas anteriores da unidade | média; alta se 50% ou mais |
| `valor` | Total 40% ou mais abaixo da média | média |
| `tarifa` | R$/kWh da conta 20% ou mais acima da mediana do R$/kWh anterior da unidade (exige consumo e 3 valores anteriores) | média |
| `demanda` | Demanda medida (maior entre ponta e fora de ponta) acima da contratada | média; alta se 110% ou mais |
| `itens` | Conta importada por IA cujos itens lidos somam mais de 3% de diferença do total (precisa de 2 itens ou mais) | baixa |
| `periodo` | Período de leitura com menos de 20 ou mais de 40 dias | baixa |
| `nota` | Mesmo número de nota fiscal (sem zeros à esquerda) em duas ou mais contas | alta |

Os alertas de `valor` e `tarifa` só são avaliados com pelo menos 3 contas anteriores e total positivo. A lista é
ordenada por gravidade, referência mais recente e código da loja.

**Conferido.** Quem tem escrita ou acesso ao painel executivo (administrador, funcionário e diretoria) marca o
alerta como conferido. Isso grava uma linha em `alert_acks` com a chave `tipo:id-da-conta`, estável entre
execuções, e o alerta some da lista; a ação vai para a auditoria (`alert_ack`). A rota só aceita chaves de alertas
que existem no momento. Não há desfazer pela interface. O contador do menu (`/api/alertas/contagem`) é calculado
com cache de 90 segundos por processo e limpo ao marcar um alerta.

## Rejeição de documentos que não são conta de energia

Qualquer arquivo com extensão e conteúdo válidos (imagem ou PDF) chega ao Gemini; é a IA quem diz se é conta de
energia (`is_energy_bill`). `rejection_reason` rejeita nestes casos:

1. A IA devolveu `is_energy_bill = false` (motivo vem em `not_bill_reason`, limitado a 120 caracteres).
2. Nenhum identificador de conta foi lido (nem número da unidade, valor total, mês de referência, número de nota e
   vencimento) e não há itens.

Efeito da rejeição (`_reject`): a importação fica com `status = rejected`, nada é lançado, **os bytes do arquivo são
apagados na hora** (`documents.data = NULL`) e a auditoria registra `import_rejected` com nome do arquivo, motivo e
`bytes_deleted`. Fica o registro do `Document` (nome, tipo, tamanho, hash). Reenviar o mesmo arquivo (mesmo SHA-256)
resulta em erro 409 na tela de upload, sem nova chamada ao Gemini. Um arquivo idêntico a um já importado com
sucesso também é barrado no upload. O prompt manda a IA devolver todos os campos vazios nesses casos.

Outros estados de uma importação: `processing` → `ready` → `confirmed` ou `cancelled`; `processing` → `failed`
(erro, ou parada por mais de 10 minutos), que permite "Tentar novamente".

## Retenção de documentos

O arquivo original (foto ou PDF) fica cifrado no banco por `DOCUMENT_RETENTION_DAYS` dias (padrão 183, cerca de 6
meses), contados de `documents.created_at`. Passado o prazo, a rotina de retenção apaga só os bytes: o registro
do documento permanece com `purged_at`, e os dados lidos da conta (valores, datas, JSON da IA, itens) continuam. A
tela do original responde 410 ("o arquivo original expirou"), a ficha da conta não consegue incluí-lo e
uma importação cujo arquivo já expirou falha, com mensagem própria, se for reprocessada. A auditoria registra a
execução (`purge`, com a quantidade e o prazo). Ver [architecture.md](architecture.md#tarefas-de-retenção).

## Auditoria

Toda criação, alteração, exclusão, importação, extração, rejeição, exportação, login e evento de segurança gera
uma linha em `audit_log`. Os eventos de autenticação gravam o IP real do cliente (`client_ip`); só o nome de
usuário digitado em tentativas falhas é pseudonimizado (HMAC), por decisão do projeto. A cadeia de hash que protege essa tabela está em
[database.md](database.md#cadeia-de-hash-da-auditoria).
