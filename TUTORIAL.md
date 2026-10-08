# Controle de Energia — Tutorial completo

Este guia tem duas partes: **(A) como colocar o sistema no ar** (feito uma vez, por quem administra) e **(B) como usar no dia a dia** (administrador, funcionário e diretoria).

---

## Quem faz o quê

| Perfil | O que faz | Onde cai ao entrar |
|---|---|---|
| **Administrador** | Cria e gerencia os **usuários e perfis** (senha provisória, redefinir senha, desativar) e acompanha a **Auditoria**. Também consegue fazer tudo que o funcionário faz, mas esse não é o seu papel no dia a dia. | Painel |
| **Funcionário** | É o **responsável por toda a gestão de energia da empresa**: cadastra lojas/filiais, unidades consumidoras e fornecedores; envia as contas (foto/PDF); faz os lançamentos manuais; corrige ou exclui o que foi lançado errado; cuida dos vencimentos; imprime. | Painel |
| **Diretoria** | Só consulta: painel executivo com comparação entre lojas, abre as lojas e imprime. Não altera nada. | Painel da diretoria |
| **Consulta** | Só visualiza e imprime. | Painel |

---

# PARTE A — Colocar o sistema no ar (Railway)

Tempo estimado: 30 a 40 minutos. Você vai precisar de: uma conta no **GitHub** (o código já está lá), uma conta no **Railway** (railway.com) e uma **chave do Gemini** (a IA que lê as contas).

> Os nomes dos botões do Railway podem mudar um pouco com o tempo. Se algum nome for diferente, procure pelo equivalente.

## A1. Pegar a chave do Gemini

1. Entre em **aistudio.google.com/apikey** com uma conta Google.
2. Clique em **Create API key** e copie a chave (começa com `AIza…`).
3. Guarde num lugar seguro. **Nunca** cole essa chave em e-mail, WhatsApp ou no código.

## A2. Gerar as duas chaves de segurança

No computador, abra o **Prompt de Comando** (Windows: tecla Windows, digite `cmd`) e rode, **um de cada vez**:

```
python -c "import secrets; print(secrets.token_hex(32))"
```

Copie o resultado: é a **SECRET_KEY**.

```
python -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Copie o resultado: é a **DOCUMENT_ENCRYPTION_KEY** (ela criptografa as fotos e PDFs no banco).

> Se o comando `python` não for reconhecido, tente `py` no lugar de `python`, ou peça ao TI para gerar as duas.
>
> **Guarde as duas chaves num cofre de senhas.** Se perder a DOCUMENT_ENCRYPTION_KEY, as fotos e PDFs já guardados deixam de abrir (os valores lidos das contas continuam).

## A3. Criar o projeto no Railway

1. No Railway: **New Project → Deploy from GitHub repo** e escolha `guiolindo/Agua-e-luz---economart` (autorize o Railway a ver o repositório, se pedir).
2. **Qual versão do código usar:** o trabalho está na branch `ccr-9b4b2f9b-4bk1nd`. Escolha uma opção:
   - **Opção A (recomendada):** no GitHub, abra um *Pull Request* dessa branch para a principal e faça o *merge*. O Railway publica a principal.
   - **Opção B:** no Railway, abra o serviço → **Settings → Source → Branch** e escolha `ccr-9b4b2f9b-4bk1nd`.
3. O Railway reconhece sozinho que é um projeto Python e já sabe como iniciar (o arquivo `railway.json` cuida disso).

## A4. Adicionar o banco de dados

1. No projeto: **+ New → Database → Add PostgreSQL**.
2. Aguarde ele ficar verde. Anote o nome do serviço (normalmente `Postgres`).

## A5. Preencher as variáveis

1. Abra o serviço do sistema (o do GitHub) → **Variables → Raw Editor**.
2. Cole o conteúdo do arquivo **`railway.env.example`** (está na raiz do repositório) e preencha:

| Variável | O que colocar |
|---|---|
| `DATABASE_URL` | Já vem como `${{Postgres.DATABASE_URL}}`. Se o seu banco tem outro nome, troque `Postgres` por esse nome. |
| `GEMINI_API_KEY` | A chave do passo A1. |
| `SECRET_KEY` | O primeiro valor do passo A2. |
| `DOCUMENT_ENCRYPTION_KEY` | O segundo valor do passo A2. |
| `ADMIN_PASSWORD` | A senha do primeiro administrador: **mínimo 12 caracteres, misturando letras e números** (senhas fracas são recusadas). |
| `DEBUG` | Deixe `false`. |
| `GEMINI_MODEL` | Deixe `gemini-3.5-flash-lite`. Se der erro de "modelo não encontrado", troque por outro modelo do Gemini. |

3. Salve. O Railway publica de novo automaticamente.

## A6. Gerar o endereço e conferir

1. **Settings → Networking → Generate Domain**. Esse é o endereço do sistema.
2. Em **Deployments → View logs**, procure `Application startup complete`. O sistema está no ar.
3. Se aparecer `Configuração insegura`, o sistema **se recusa a iniciar** de propósito: a mensagem diz exatamente qual variável está faltando ou fraca. Corrija e salve de novo.
4. Abra o endereço no navegador: deve aparecer a tela de login.

## A7. Primeiro acesso do administrador

1. Entre com usuário **`admin`** e a senha de `ADMIN_PASSWORD`.
2. Clique em **Alterar senha** (no canto inferior esquerdo) e crie a sua senha pessoal.
3. Faça o **backup do banco**: no Railway, ative backups do PostgreSQL e **teste restaurar** uma vez. O Railway não faz isso por você.

---

# PARTE B — Usando o sistema

## B1. Primeiros acessos e cadastros

### Passo 1 — O administrador cria os acessos

O papel do administrador é cuidar de **quem entra e com qual perfil**. Menu **Usuários → Novo usuário**:

1. Digite o nome de usuário e escolha o **perfil** (Funcionário, Diretoria, Consulta ou Administrador).
2. Clique em **Criar usuário**. Aparece uma **senha provisória de 4 dígitos**, mostrada **uma única vez**. Anote e entregue à pessoa.
3. **No primeiro acesso a pessoa é obrigada a criar a própria senha** (mínimo 10 caracteres, letras e números; não pode ser o nome de usuário nem uma senha comum).

Sobre a senha provisória de 4 dígitos:

- Ela **vale 48 horas** e só serve para o primeiro acesso: com ela a pessoa só consegue trocar a senha.
- Depois de 3 tentativas erradas a conta é bloqueada por 15 minutos.
- Se a pessoa não entrou a tempo ou esqueceu a senha: **Usuários → Redefinir senha** gera outra de 4 dígitos.
- Para desligar alguém que saiu da empresa: **Usuários → Desativar** (as sessões abertas caem na hora).

### Passo 2 — O funcionário faz os cadastros

O funcionário é o responsável por manter tudo de energia da empresa, então é ele quem cadastra:

**1. Lojas/filiais.** Menu **Lojas → Nova loja**. Informe:

- **Código** (ex.: `CD300`) e **nome**;
- **Região/UF** (ex.: `MG`, `BA`): é usada para comparar regiões no painel da diretoria;
- **Apelidos** (ex.: `CD 300, CD Rib Neves`): ajudam a ler anotações escritas à mão nas contas.

**2. Unidades consumidoras (pontos de energia).** Dentro da loja, **Cadastro → Adicionar unidade** (com o **dia de vencimento da conta**, opcional), ou, de qualquer tela, **+ Novo ponto de energia** (veja B4). Cada unidade tem o **número da unidade consumidora** exatamente como está na conta (ex.: `12.060.073.018-19`).

**Para editar uma unidade já criada** (número, descrição, distribuidora, dia de vencimento, situação): abra a unidade e clique em **Editar unidade**, ou use **Editar** na lista de unidades da loja. Unidades criadas sem vencimento **continuam funcionando normalmente**; apenas não geram aviso até você definir o dia (o painel do funcionário lista quais ainda estão sem vencimento).

**3. Fornecedores (tipos de registro).** Menu **Tipos de registro**. Já vêm cadastrados: CEMIG, COELBA, ENERGISA, CEMIG Geração e Transmissão (esta também vem em conta com foto, como as distribuidoras), LL Energia, Câmara de Comercialização de Energia, Compra de combustível para gerador e Manutenção de Gerador. Para outra distribuidora (ex.: Light, Copel) crie um tipo **"Conta de distribuidora"**; para outros custos, **"Lançamento manual"**.

Se algo for cadastrado errado, o próprio funcionário corrige. Tudo fica registrado na **Auditoria** (quem fez, o quê e quando), que o administrador acompanha.

## B2. Enviar uma conta (funcionário)

1. Clique em **Importar conta**.
2. Arraste a foto ou o PDF para a caixa (ou clique e escolha; no celular dá para tirar a foto na hora). Formatos: JPG, PNG, WEBP ou PDF, **até 12 MB**; PDF com até 10 páginas. **Um arquivo por conta.**
3. Aguarde alguns segundos. O sistema lê a conta e descobre sozinho a **loja e a unidade**.
4. Na **tela de conferência**, a imagem fica ao lado dos campos. **Confira com atenção**: a leitura é feita por IA e pode errar. Campos marcados com **"conferir"** pedem mais cuidado (valor, mês, vencimento, unidade). Você pode corrigir qualquer campo.
5. Clique em **Confirmar e salvar**. O gráfico da loja já aparece atualizado, com a conta importada em destaque.

O que pode aparecer na conferência:

- **"Unidade encontrada no cadastro"**: tudo certo, a loja foi identificada pelo número.
- **"Unidade consumidora não cadastrada"**: a conta não é descartada. Escolha **Cadastrar esta unidade** (e a loja) ou **Associar a uma unidade existente**. O sistema sugere unidades parecidas se a IA errou um dígito.
- **"Esta conta aparentemente já está cadastrada"**: escolha **Substituir** ou **Salvar como novo**. Para desistir, **Descartar importação**.
- **Aviso de anotação à mão**: se a folha tem algo escrito à mão (ex.: "CD 300") que não bate com a loja da unidade, o sistema avisa.
- Reenviar **exatamente o mesmo arquivo** de uma conta já salva é recusado (evita lançar em duplicidade).

Observações:

- A foto ou o PDF original fica guardado por **6 meses** e depois é apagado automaticamente. Os valores e gráficos permanecem.
- Dica de foto: conta inteira, de frente, com boa luz, sem reflexo.

## B3. Lançamento manual (funcionário)

Para fornecedores sem foto (LL Energia, Câmara, combustível, manutenção) e para meses antigos:

1. Menu **Lançamento manual**.
2. Escolha a **loja**, a **unidade** (opcional para os fornecedores manuais) e o **tipo**.
3. Informe o **mês**, o **valor** e, se quiser, o **vencimento** (usado para agrupar pelo mês de vencimento). Campos extras aparecem conforme o tipo (ex.: litros, horas).
4. **Salvar**. Se já existir lançamento para o mesmo período, o sistema pergunta se é para substituir.

Para corrigir uma conta: **Lojas → (loja) → (unidade) → Contas → Editar**. O funcionário também pode **excluir** uma conta ou lançamento errado (a exclusão fica registrada na Auditoria).

## B4. Novo ponto de energia e aviso de vencimento

De **qualquer tela**, clique em **+ Novo ponto de energia** (canto superior direito):

1. Escolha a **loja**.
2. Digite o **número da unidade consumidora** e, se quiser, uma descrição.
3. Informe a **data de vencimento**.
4. **Cadastrar.** O sistema passa a considerar que a conta vence **todo mês nesse dia**.

**Como funciona o aviso:**

- Quem recebe o aviso é **o funcionário** (administrador, diretoria e consulta não veem o sino nem os avisos). Ao entrar no sistema, aparece **do lado direito** um aviso: **"Vence hoje"** (e **"Venceu há N dias"**, por até 15 dias). Ele **some sozinho em 15 segundos**. Se passar o mouse por cima, o tempo pausa.
- Ele aparece **uma vez por login, por dia**.
- O **sino** (canto superior direito) guarda a lista de vencimentos, inclusive "vence amanhã". Clique em **Já paguei** para dar baixa daquele vencimento; no mês seguinte o aviso volta.
- Contas importadas por foto/PDF ensinam o dia de vencimento ao ponto automaticamente.
- Para mudar o dia depois, ou remover o vencimento: **Editar unidade**.

## B5. Painel da diretoria

Entra direto ao fazer login (perfil Diretoria). O administrador também acessa pelo menu.

- **No topo:** total do período, último mês, média mensal, custo médio por kWh, maior gasto, maior alta e maior queda do mês, pendências.
- **Gráficos:** gasto da empresa por mês e fornecedor, ranking de lojas, variação do último mês por loja, composição do gasto, evolução (marque as lojas que quer ver), custo por kWh, uso da demanda contratada.
- **Comparar duas lojas:** escolha a loja A e a loja B e veja a diferença mês a mês em R$ e em %.
- **Mapa de calor e tabela comparativa:** gasto de cada loja por mês, participação no total, variação, custo por kWh e uso da demanda.
- **Filtros:** período, mês de referência ou de vencimento, região e fornecedores.

Como ler com cuidado:

- Um mês em que **poucas lojas já lançaram** aparece com **\*** e **não entra nas variações**; os indicadores usam o último mês **completo**.
- "vs. período anterior" compara a **média por mês**, só das lojas que têm histórico.
- A **demanda usada acima de 100%** significa conta com demanda medida maior que a contratada (cobrança de ultrapassagem).

## B6. Imprimir

**Folha da loja (1 página A4 paisagem):** **Lojas → (loja) → Imprimir relatório**. Escolha o período, se agrupa por referência ou vencimento e o **imóvel/fornecedor**. A folha traz o resumo mensal de todos os fornecedores com Total Geral, indicadores, gráfico com variação e a tabela de Valor, Consumo, Demanda, Dias e Variação. Marque **"um por folha (todos)"** para imprimir uma folha de cada fornecedor.

**Ficha de uma conta (1 página A4 retrato):** **Unidade → Contas → Imprimir** (ao lado da conta desejada). Dá para trocar de mês na própria tela e marcar **"Incluir foto/PDF original"** (vai numa segunda página, se o arquivo ainda não expirou).

**Painel da diretoria:** botão **Imprimir painel**.

Na janela de impressão do navegador:

- Deixe a **escala em 100%** (ou "padrão").
- As cores já são forçadas na impressão. Se mesmo assim sair sem cor, marque **"Gráficos de segundo plano"** (Chrome; no Edge: "Gráficos de plano de fundo") em *Mais definições*.
- Para guardar em arquivo, escolha **Salvar como PDF**.

## B7. Segurança no dia a dia

- Cada pessoa usa **o seu usuário**; não compartilhe senha.
- O sistema **desloga sozinho** depois de 60 minutos parado.
- Depois de 5 senhas erradas a conta é bloqueada por 15 minutos (3 se ainda estiver com a senha provisória).
- Esqueceu a senha? Peça ao administrador: **Usuários → Redefinir senha**.
- O administrador acompanha tudo em **Auditoria** (quem entrou, tentativas falhas, bloqueios, trocas de senha e o que cada pessoa alterou, inclusive cadastros e exclusões do funcionário). O endereço de IP aparece apenas como um código, nunca em claro.
- Revise **Usuários** todo mês e desative quem saiu.
- Guarde a `SECRET_KEY`, a `DOCUMENT_ENCRYPTION_KEY` e a chave do Gemini num cofre de senhas.

## B8. Rotina sugerida

| Quando | O quê | Quem |
|---|---|---|
| Ao chegar uma conta | Importar, conferir, salvar | Funcionário |
| Ao entrar no sistema | Olhar o aviso/sino de vencimentos; dar "Já paguei" | Funcionário |
| Todo mês | Lançar os fornecedores manuais (LL, Câmara, combustível, manutenção) | Funcionário |
| Todo mês | Conferir **Pendências** no Painel | Funcionário |
| Mensal | Abrir o Painel da diretoria e imprimir, se necessário | Diretoria |
| Mensal | Revisar usuários ativos e a Auditoria | Administrador |
| Trimestral | Testar a restauração do backup do banco | Administrador |

---

# Problemas comuns

| Problema | O que fazer |
|---|---|
| A IA leu um valor errado | Corrija direto na tela de conferência antes de salvar. A conta nunca é salva sem você confirmar. |
| "Unidade consumidora não cadastrada" | Cadastre a unidade na própria conferência, ou associe a uma existente. |
| "Este mesmo arquivo já foi importado" | A conta já está salva; use o link para vê-la. |
| Arquivo recusado | Use JPG, PNG, WEBP ou PDF, até 12 MB e até 10 páginas, um arquivo por conta. |
| "Limite de uso do Gemini atingido" | Espere cerca de 1 minuto e tente de novo. |
| "A chave da API do Gemini é inválida" | O administrador atualiza `GEMINI_API_KEY` no Railway. |
| "Muitas tentativas" | Aguarde um minuto. |
| Não consigo entrar | Verifique usuário e senha. Se a conta bloqueou, aguarde 15 minutos ou peça ao administrador. Senha provisória com mais de 48 h: peça uma nova. |
| Importação ficou "processando" | Depois de 10 minutos aparece **Tentar novamente**. |
| Gráfico em branco | Confira o período escolhido (De/Até) e se há contas lançadas nele. |
| O sistema não inicia no Railway | Veja os *logs*: a mensagem diz qual variável está ausente ou fraca. |
| Impressão sem cores | Na janela de impressão, em *Mais definições*, marque **"Gráficos de segundo plano"**. |

---

# Checklist do primeiro dia

1. [ ] Gerar a chave do Gemini, a `SECRET_KEY` e a `DOCUMENT_ENCRYPTION_KEY` (e guardá-las).
2. [ ] Criar o projeto no Railway, o PostgreSQL e preencher as variáveis.
3. [ ] Gerar o domínio e confirmar que a tela de login abre.
4. [ ] Entrar como `admin` e trocar a senha.
5. [ ] Ativar o backup do banco.
6. [ ] **Administrador:** criar o usuário da diretoria e os dos funcionários; entregar as senhas provisórias de 4 dígitos.
7. [ ] **Funcionário:** entrar (trocando a senha), cadastrar as lojas (com região) e as unidades.
8. [ ] **Importar 3 ou 4 contas reais** (CEMIG e Coelba, foto e PDF) e conferir a leitura com cuidado.
9. [ ] Lançar o histórico dos meses anteriores (manual) para os gráficos fazerem sentido.
10. [ ] Imprimir uma folha da loja e uma ficha de conta para conferir o resultado no papel.

> **Importante:** a leitura das contas pela IA ainda não foi testada com a chave do Gemini de vocês. Por isso o passo 8 é essencial. Se algum campo vier errado de forma repetida, avise para ajustarmos as instruções da IA.
