# Roadmap pós-apresentação

Origem: pesquisa de 2026-10-10 sobre gestão de contas de energia, cruzada com o que o sistema já tem. Nada aqui entra antes
da decisão da diretoria. A ordem considera benefício, esforço e risco. Itens marcados com ✅ já foram feitos.

## Já adotado

| Ideia | Situação |
|---|---|
| Renomear R$/kWh para "custo efetivo por kWh" e explicar a fórmula | ✅ |
| Nota metodológica no painel e na planilha | ✅ |
| Tolerância de 5% na demanda (sem afirmar cobrança) | ✅ |
| Alertas com motivo e histórico usado; marcar como conferido | ✅ (Central de Alertas) |
| Aviso de duplicidade por unidade, referência e nota fiscal | ✅ |
| Itens da fatura que não fecham com o total | ✅ |
| XLSX executivo formatado | ✅ |

## Revisão externa de 11/10/2026 (outra IA, sobre o commit `ad41b32`)

**Aplicado na hora:** textos da apresentação mais precisos ("com o mínimo de digitação", "visão executiva da empresa", 2FA "disponível" e não "usado"); modo **Resumo** (8 slides, tecla `R`); zoom devolve e prende o foco; papéis ARIA de aba removidos; busca, *Top 5*, *Todas*, *Limpar* e contador na seleção de lojas do gráfico de evolução. **Não procede:** "o deck inteiro está com `aria-hidden`", pois só os elementos decorativos têm (há um teste que garante isso).

**Medido com 100 lojas e 2 unidades cada (2.297 contas, SQLite local):** painel da diretoria carrega em ~0,5-0,7 s, XLSX em ~1,1 s, CSV em ~0,2 s. Em produção (Postgres) a rede soma algumas dezenas de ms; confirmar no Railway.

**Fica para depois da decisão (precisa de desenho e de dados reais, não é para a apresentação de terça):** fila de pendências com responsável, prazo e status; ciclo de vida de alertas (atribuir, comentar, adiar, resolver, reabrir); investigação de alerta ponta a ponta; importação e conferência em lote; painel de *qualidade dos dados* (lojas completas, contas aguardando conferência); separar a diretoria em abas (resumo, desempenho, custos, qualidade, detalhe); grupos/regiões e escopo de acesso por loja; passkeys/WebAuthn; `REQUIRE_ADMIN_2FA=true` em produção (depois que cada administrador ativar o seu 2FA, para ninguém ficar de fora); pentest externo e teste de impressão A3 com diretores.

## Próximos passos de baixo risco

1. kWh/dia e R$/dia ao lado da variação mensal (consumo, valor e dias já existem).
2. Mostrar o período comparado e os dias em cada alerta.
3. Cobertura do fechamento: contas esperadas, recebidas e pendentes por mês.
4. Estados da conta: provisória, validada, manual.
5. Alerta "justificado", com comentário e usuário.
6. Exibir ultrapassagem e reativo efetivamente cobrados, quando a extração já os trouxer.
7. Aba "Dicionário de dados" e "Detalhamento" sem células mescladas no XLSX.

## Médio prazo (precisam de dados ou de decisão da empresa)

| Ideia | Dado necessário |
|---|---|
| Fila mensal com responsável, prazo e motivo | responsáveis e prazos |
| Revisão lado a lado com destaque do campo lido | coordenadas e confiança da leitura |
| Medir acurácia da leitura (precisão, revocação, acerto por campo e layout) | conjunto de contas reais anotado |
| Conciliação de mercado livre (distribuidora + LL + CCEE) por competência | faturas dos três |
| Normalizar por área, faturamento e horário | dados do ERP |
| Exportação TXT/CSV para importar no Oracle | versão e leiaute do ERP |
| Conciliação ERP × sistema por documento e valor | retorno do ERP |

## Longo prazo (alto esforço ou risco)

- Simulador de demanda contratada (12+ ciclos) e de modalidade verde × azul.
- Estrutura genérica para energia, água, esgoto e combustível (ver `DECISIONS.md` §10).
- Dados intervalares por comercializadora ou CCEE.
- Provisão de contas não recebidas; aprovação automática de documentos "seguros".
- Alertas de vazamento de água (precisam de dados horários).

## Não fazer agora

Impostos recuperáveis, modelo de previsão por IA, telemetria e submedição própria, aplicativo móvel, portal para fornecedores e
gestão de pagamento. Aumentam manutenção e responsabilidade sem resolver o que a apresentação precisa mostrar: controle
confiável das contas já existentes.

## Pontos a confirmar

- Texto oficial do artigo da REN ANEEL 1.000/2021 sobre ultrapassagem (tolerância de 5% confirmada em fontes secundárias;
  multiplicador da cobrança divergente entre fontes).
- Quais lojas são Grupo A ou B, quais estão no mercado livre e as demandas contratadas.
