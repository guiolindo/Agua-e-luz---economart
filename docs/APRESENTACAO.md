# Apresentação: continuar ou cancelar o projeto

Roteiro para a reunião de terça. Tudo aqui foi conferido no sistema; onde há uma pendência, está escrito.

## 1. A história em uma frase
O projeto nasceu para tirar de uma pessoa o trabalho manual de montar, a cada conta de água e luz, a planilha e os gráficos por loja. Funcionou, e hoje é o controle de energia da empresa.

## 2. Antes × agora

| Na planilha | No sistema |
|---|---|
| Digitar à mão cada conta (valor, datas, consumo, demanda) | Foto ou PDF da conta: o sistema lê, o funcionário só **confere** e salva |
| Montar a tabela e o gráfico de cada loja | Gerados sozinhos; a **folha impressa reproduz a planilha ao centavo** (resumo por vencimento, gráfico por referência, valor/dias/variação) |
| Ver só uma loja de cada vez | Painel da diretoria com **todas as lojas**: ranking, variação, custo por kWh, demanda, comparação entre lojas e mapa de calor |
| Descobrir um problema quando alguém lembra de olhar | **Alertas automáticos**: conta fora do padrão da unidade, demanda acima do contratado, nota repetida |
| Esquecer um vencimento | Aviso no dia do vencimento e lista de pendências do mês |
| Conta duplicada ou digitada errado sem ninguém ver | Detecção de duplicidade, conferência antes de salvar e trilha de auditoria |
| Um arquivo, uma pessoa | Perfis (administrador, funcionário, diretoria, consulta), cada um vê só o que usa |
| Sem histórico de quem mexeu | Auditoria com selo contra adulteração e 2FA para administradores |

Fornecedores já cobertos: CEMIG, CEMIG Geração e Transmissão, COELBA, Energisa, LL Energia (lançamento em lote para várias lojas), Câmara de Comercialização, combustível e manutenção de gerador.

## 3. Roteiro da demonstração (12 minutos)
1. **Entrada (1 min).** Login, abertura do sistema. Mostre o painel do funcionário.
2. **O fluxo principal (4 min).** *Importar conta* com a foto real da CEMIG da CD300 → tela de conferência (dados ao lado da imagem) → salvar → o gráfico da loja já mudou. É o ponto que substitui a digitação.
3. **A folha igual à planilha (2 min).** *Lojas → CD300 → Imprimir relatório*. Coloque a planilha antiga ao lado: os totais são os mesmos. O resumo está por mês de vencimento e o gráfico por mês de referência, como na planilha.
4. **O que a planilha não fazia (4 min).** Painel da diretoria (resumo em frases, ranking, comparar duas lojas), ficha da loja, *Alertas* e *Baixar planilha*.
5. **Segurança e controle (1 min).** Auditoria (quem fez o quê), perfis e 2FA.

Não mostre ao vivo: Energisa e CEMIG Geração e Transmissão com arquivo novo (ver pendências), nem arquivo que não é conta (a barragem foi testada só com simulador).

## 4. Perguntas prováveis e respostas honestas
- **A leitura da foto erra?** Pode. Por isso a conta nunca é salva sem conferência, e os alertas comparam com o histórico para apontar valores estranhos. O funcionário continua responsável pela conferência.
- **Quanto custa operar?** Hospedagem no Railway e o uso da API do Gemini por conta enviada (centavos por conta). Levante o valor atual no painel do Railway e no Google AI Studio antes da reunião e leve o número.
- **E se o Gemini cair?** O sistema falha rápido e o funcionário usa o *Lançamento manual* até voltar.
- **Os dados estão seguros?** Login com bloqueio por tentativas, arquivos das contas cifrados, auditoria com selo, 2FA do administrador, cabeçalhos de segurança, backups do banco (ver pendência).
- **Quanto tempo economiza?** Meça antes: cronometre o fechamento de um mês na planilha e o de um mês no sistema. Um número real vale mais que qualquer estimativa.
- **O que falta?** Metas/orçamento por loja, resumo semanal por e-mail, projeção do ano. Estão no roteiro de evolução, depois da decisão.

## 5. Lista de conferência até terça
**Sexta a domingo**
- [ ] Deploy no Railway com as variáveis do `docs/OPERACAO.md` e `REQUIRE_ADMIN_2FA=false` até você ativar o seu 2FA.
- [ ] Fazer um backup do banco antes do deploy (a primeira subida aplica as migrações).
- [ ] Ativar o 2FA do seu usuário e guardar os códigos de recuperação.
- [ ] Carregar a CD300 com os valores da planilha: `python -m scripts.seed_demo` (usa o `DATABASE_URL` do ambiente; marque como demonstração se for apresentar com dados de exemplo).
- [ ] Enviar a conta CEMIG real da CD300 (SET/2026) pelo Importar e conferir o resultado contra a conta física.
- [ ] Testar **uma** conta Energisa e **uma** CEMIG Geração e Transmissão reais, se houver. Se não houver, não mostrar.
- [ ] Enviar um arquivo que não é conta (cardápio, selfie) e conferir que é barrado.

**Segunda**
- [ ] Ensaio completo do roteiro com a pessoa que usa a planilha. Anote o que ela estranhar.
- [ ] Conferir no celular: login, painel, importar, contas.
- [ ] Congelar mudanças: a partir daqui só correção de erro, nada de novidade.

**Terça**
- [ ] Abrir o sistema 30 min antes, entrar com os três perfis, imprimir uma folha.
- [ ] Ter a planilha original e a folha impressa do sistema lado a lado.

## 6. Pendências que não dependem de código
1. Gemini com contas reais de Energisa e CEMIG Geração e Transmissão.
2. Barragem de arquivos que não são conta, testada com o Gemini real.
3. Restauração de um backup do Railway nunca foi testada.
4. Nenhum alerta por e-mail: o sistema só avisa dentro dele.
