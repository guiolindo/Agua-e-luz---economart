# Teste manual no navegador: checklist

O que conferir com os próprios olhos depois de mexer em tela, CSS, JavaScript, login ou permissões, e depois de
cada deploy. Complementa os 450 testes automáticos (`pytest`), que não abrem um navegador de verdade. Leva cerca
de 15 minutos.

## Como rodar

1. Em ambiente local, com dados de demonstração (nunca a lista real de lojas):
   ```bash
   EXTRACTION_PROVIDER=mock DEBUG=true python run.py
   python -m scripts.seed_demo && python -m scripts.seed_demo_company
   ```
   Ou no Railway logo após o deploy, só lendo (sem excluir nem importar dados reais).
2. Abra `http://127.0.0.1:8000` com as ferramentas do navegador (F12): **Console** e **Rede** abertas.
3. Crie em *Usuários* um usuário de cada perfil (funcionário, diretoria, consulta) para os itens de cada um.
4. Marque cada item. Se algum falhar, não publique: corrija antes.

## Critério para passar

Cada item precisa cumprir os três:

1. **Nenhum erro vermelho no Console** (aviso amarelo pode).
2. **O botão responde** ao clique, sem ficar parado.
3. **Acontece o esperado** (abre, salva, volta, mostra a mensagem).

E em toda tela: sem rolagem lateral em 390 px de largura (modo celular do F12), exceto dentro das tabelas largas.

---

## Entrada

- [ ] `/login` carrega com logo e formulário; "mostrar senha" alterna.
- [ ] Senha errada mostra a mensagem embaixo; 5 erros seguidos bloqueiam a conta por 15 minutos.
- [ ] Senha certa entra no painel (diretoria cai direto em `/diretoria`).
- [ ] Admin com 2FA: pede o código de 6 dígitos; código errado avisa sem sair da tela.
- [ ] Usuário novo com senha provisória (4 dígitos) é obrigado a trocar a senha no primeiro acesso.
- [ ] **Sair** volta para o login; abrir um endereço interno depois disso pede login de novo.

## Funcionário

- [ ] **Importar conta** (`i` no teclado): enviar uma conta; a barra de progresso anda e abre a conferência com a
      imagem ao lado.
- [ ] Na conferência, editar um campo e **Confirmar**: cai na loja, com a conta no histórico e nos gráficos.
- [ ] Reenviar o mesmo arquivo: recusado na hora ("já foi importado"), sem chamar o Gemini.
- [ ] Enviar um arquivo que não é conta (ex.: foto qualquer): recusado com mensagem clara.
- [ ] **Lançamento manual** (`g m`) e **lançamento em lote** salvam e aparecem na loja.
- [ ] **+ Novo ponto de energia** (canto superior direito) abre, salva e volta para a tela onde estava.
- [ ] Sair de um formulário com alteração não salva pede confirmação.
- [ ] Sino de vencimentos lista os pontos; **Já paguei** tira o item da lista.
- [ ] Excluir uma conta: aparece **Desfazer** no aviso; clicar devolve a conta.
- [ ] Excluir de novo e abrir **Lixeira**: o item está lá e **Restaurar** devolve.
- [ ] **Imprimir relatório** da loja e **Imprimir** da conta: abrem na mesma aba, com **Voltar**; a prévia de
      impressão cabe em uma página A4.
- [ ] Trocar de conta/mês na ficha de impressão troca sem tela branca.

## Diretoria

- [ ] `/diretoria` abre na aba **Visão geral**; as abas **Lojas**, **Gasto evitável**, **Ano** (e **Contratos**,
      se houver conta com demanda) trocam sem recarregar os filtros.
- [ ] Filtro de período, região e fornecedor muda os números; o endereço guarda os filtros.
- [ ] Gráficos aparecem com legenda e o valor aparece ao passar o mouse.
- [ ] **Baixar planilha** e **Baixar apresentação** baixam e abrem (Excel e PowerPoint).
- [ ] **Imprimir painel** (cada opção do menu) mostra a prévia sem página em branco.
- [ ] Não aparece nenhum botão de importar, editar ou excluir.

## Consulta

- [ ] Vê lojas, contas e gráficos e imprime; não vê importar, lançar, excluir, lixeira nem administração.

## Administrador

- [ ] **Usuários**: criar mostra a senha provisória uma vez; redefinir, desbloquear, mudar perfil e desativar
      funcionam. Ações sobre outro administrador pedem a sua senha.
- [ ] **Painel admin**: uso por pessoa e coluna **Rede** preenchidos; "Ver em tabela" abre a tabela dos gráficos.
- [ ] **Auditoria**: as ações feitas acima aparecem, em português, com "na empresa"/"fora" quando a rede está
      cadastrada; **Verificar integridade** diz "Auditoria íntegra"; exportar CSV baixa.
- [ ] **Rede da empresa**: mostra o seu IP; cadastrar e remover um IP funciona.
- [ ] **Lixeira** do admin mostra os itens de todos, com quem excluiu.

## Em todas as telas

- [ ] `?` mostra os atalhos; `/` foca a busca da tela; `g` + letra navega (`g p` painel, `g c` contas, `g l` lojas,
      `g a` alertas, `g h` ajuda).
- [ ] **Ajuda** mostra o conteúdo do perfil que está logado.
- [ ] Trocar de tela não pisca branco.
- [ ] Parar o servidor com a tela aberta: aparece a faixa "servidor não respondeu"; abrir outro link mostra a
      página offline; religar e recarregar volta ao normal.
- [ ] Endereço inexistente mostra a página 404 do sistema; um erro 500 mostra o **Código do erro**.
- [ ] Navegação só pelo teclado (Tab): o foco aparece em cada botão e link.

## Depois do deploy no Railway

- [ ] `/health` responde `ok`.
- [ ] Os logs do deploy mostram as migrações aplicadas, sem erro.
- [ ] *Auditoria → Rede da empresa*: o IP mostrado é o seu IP real (compare com meuip.com.br), não o da CDN.
- [ ] Uma conta real importada aparece corretamente na conferência.
