# Frontend — estrutura, padrões e como contribuir

Este documento descreve como as telas são montadas: templates Jinja2, CSS, JavaScript, gráficos, impressão e
acessibilidade. Tudo foi conferido em `app/templates/` e `app/static/`; o que não pôde ser verificado está marcado.

## Stack

- **Templates**: Jinja2, renderizados no servidor pelo FastAPI (`Jinja2Templates`). A página chega pronta; o
  JavaScript só acrescenta comportamento.
- **CSS**: um único arquivo, `app/static/css/app.css` (cerca de 580 linhas, 67 KB), com tokens em `:root`. Sem
  pré-processador, sem `@import`, sem framework.
- **JavaScript**: vanilla (ES2020), sem build, sem `npm`, sem módulos. Três arquivos próprios (`app.js`,
  `chart_panel.js`, `director.js`) mais o Chart.js 4.4.7 em `static/js/vendor/`.
- **Gráficos**: Chart.js, servido localmente (nenhum CDN, nenhuma origem externa permitida pelo CSP).
- **Fontes e ícones**: não há webfont carregada. `font-family` é `Inter, "Segoe UI", system-ui, …`, ou seja, usa o
  Inter só se estiver instalado na máquina. Ícones são SVG inline nos templates. Não há biblioteca de ícones.
- **Tema**: só claro. Não existe `prefers-color-scheme` no CSS.

A escolha de "sem build" é deliberada: o deploy no Railway roda o `uvicorn` direto, sem etapa de bundle, e qualquer
pessoa edita um arquivo e vê o resultado. O custo é que `app.js` concentra comportamentos de áreas diferentes
(ver [JavaScript](#javascript)).

Restrição de segurança que molda todo o frontend: o CSP não permite JavaScript inline sem `nonce` nem manipuladores
`onclick=`/`onchange=`. Ver [`security.md`](security.md).

---

## Estrutura de arquivos

```
app/
├── web.py                      # Jinja2Templates, filtros, globais e render()
├── templates/
│   ├── base.html               # casca: menu lateral, topbar, rodapé mobile, splash, despedida
│   ├── macros.html             # field, variation, csrf, bill_fields, hero
│   ├── _auth_brand.html        # painel da marca das telas de acesso (login e 2FA)
│   ├── login.html, login_2fa.html
│   ├── dashboard.html          # painel inicial
│   ├── help.html               # ajuda por perfil
│   ├── error.html              # 403/404/409/410/500
│   ├── account/                # password.html, two_factor.html
│   ├── admin/                  # users.html, audit.html
│   ├── alerts/                 # list.html (central de alertas)
│   ├── bills/                  # list.html (/notas), print.html (ficha A4 retrato)
│   ├── director/               # panel.html (painel da diretoria)
│   ├── imports/                # upload.html, progress.html, review.html
│   ├── manual/                 # form.html, batch.html, _modes.html
│   ├── partials/               # chart_panel.html (painel de gráfico reutilizável)
│   ├── points/                 # new.html, fragment.html (diálogo), _form.html
│   ├── stores/                 # list, form, settings, history, report (folha A4 paisagem)
│   ├── types/                  # list.html
│   └── units/                  # detail.html, edit.html, _dueday.html
└── static/
    ├── css/app.css
    ├── img/                    # logo.png, logo-white.png, favicon.png
    └── js/
        ├── app.js              # comportamentos globais (carregado em toda página)
        ├── chart_panel.js      # gráfico da loja/unidade (via partials/chart_panel.html)
        ├── director.js         # 8 gráficos do painel da diretoria
        └── vendor/chart.umd.min.js   # Chart.js 4.4.7
```

Convenção de nomes: arquivo começado por `_` é fragmento incluído por outro template (`{% include %}`), não uma
página.

---

## Como uma página é renderizada

Toda rota que devolve HTML chama `render(request, "pasta/pagina.html", user=user, **contexto)` (`app/web.py`).
`render` acrescenta ao contexto:

| Variável | Origem | Uso |
|---|---|---|
| `csrf_token` | `security.csrf_token(request)` | campo oculto dos formulários e `<meta name="csrf-token">` |
| `csp_nonce` | `request.state.csp_nonce` | atributo `nonce` de todo `<script>` inline |
| `login_stamp` | `session["iat"]` | identifica "este login" para o splash e para o aviso de vencimentos (uma vez por login) |
| `flashes` | `session.pop("flash")` | mensagens `{text, level}` mostradas no topo do conteúdo |
| `path` | `request.url.path` | marca o item de menu ativo |
| `user` | argumento (padrão `None`) | quando `None`, `base.html` renderiza o bloco `bare` (sem menu) |

Globais Jinja: `retention_days`, `greeting_now()` ("Bom dia/Boa tarde/Boa noite", fuso de Brasília), `today_long()`
("sexta-feira, 10 de outubro de 2026"), `login_max_attempts`, `login_block_minutes`, `ASSET_VERSION`.

Filtros (`app/utils/formatting.py` e `timezone.py`): `brl` ("R$ 1.234,56"), `num`, `pct` (com `signed`, usa "−"),
`month_label` ("SET/2026"), `date_br` ("10/10/2026"), `dt_br` ("10/10/2026 21:05", opções `seconds` e `short`).
Valor ausente vira "—".

`ASSET_VERSION` é um SHA-1 curto dos conteúdos de `app.css`, `app.js`, `chart_panel.js` e `director.js`,
calculado **uma vez, na importação do módulo**. Os templates referenciam `app.css?v={{ ASSET_VERSION }}`, o que
derruba o cache do navegador quando um desses arquivos muda (após reiniciar o servidor). O Chart.js em `vendor/`
fica de fora e é referenciado sem `?v=`.

### `base.html`

Blocos disponíveis para as páginas filhas:

| Bloco | Conteúdo |
|---|---|
| `title` | texto do `<title>`; convenção `Tela · Economart Energia` |
| `content` | área principal (`<main id="content">`), só para usuário logado |
| `bare` | tela sem menu (login, 2FA, erro) |
| `scripts` | `<script>` específicos da página, depois de `app.js` |

O que a casca monta para o usuário logado:

- link **"Ir para o conteúdo"** (`.skip`), primeiro elemento do `<body>`;
- `#bye` (despedida do logout) e `#splash` (abertura do sistema);
- `m-topbar` (menu, logo, sino) e `m-bottomnav` (rodapé mobile), visíveis só em ≤ 800 px;
- `<aside class="side">` com `nav` (itens por perfil), nome do usuário, *Alterar senha*, *2FA* (admin) e o
  formulário de *Sair*;
- `.topbar` com o botão **+ Novo ponto de energia** (escondido nas telas de importação, lançamento, administração,
  tipos, conta e notas) e o sino de vencimentos (só `operator`);
- aviso para o administrador sem 2FA em `/` e `/admin/users`;
- `#toasts` (região `aria-live`) e o `<dialog id="point-dialog">` (para quem pode escrever).

Os itens do menu dependem do perfil: *Importar conta*, *Lançamento manual* e *Tipos de registro* só com
`can_write`; *Painel da diretoria* com `can_see_executive`; *Painel* some para `director` (que tem o seu); *Auditoria*
e *Usuários* só para `admin`. Quem está com troca de senha obrigatória não vê o menu.

### Macros (`macros.html`)

| Macro | Uso |
|---|---|
| `field(name, label, form, errors, type, flagged, hint, required, step, placeholder)` | campo de formulário com rótulo, erro e dica; `id="f-<name>"`. `flagged` mostra "conferir" (campo lido com baixa confiança pela IA) |
| `variation(v)` | variação percentual com a classe `var-up`/`var-down`/`var-flat`, ou "—" |
| `csrf(token)` | `<input type="hidden" name="csrf_token">` |
| `bill_fields(form, errors, flagged)` | todos os campos de uma conta (referência, valor, datas, consumo HP/HFP/HR, demanda, impostos…), reutilizado na conferência da importação e no lançamento manual |
| `hero(eyebrow, title, sub, back_href, back_text)` | faixa de abertura; usa `{% call hero(...) %}` e o conteúdo do `call` entra em `.hero-actions` (botões) |

Importar: `{% from "macros.html" import csrf, hero %}`.

### Hero

`hero` é a faixa azul com degradê, grade sutil e brilho laranja no topo de **Painel, Painel da diretoria, Central
de alertas e Histórico da loja**: mesma linguagem visual do login. Estrutura: *eyebrow* (saudação ou contexto),
`<h1>`, subtítulo e ações. Fica oculta na impressão (`.hero` e `.no-print`). Exemplo de uso real
(`dashboard.html`): o *eyebrow* é `greeting_now() ~ ", " ~ user.username`, o subtítulo traz a data por extenso, o
mês e a contagem de pendências, e os botões são "Importar conta", "Lançamento manual", "Contas" e "Alertas".

---

## Apresentação do sistema (`/apresentacao`)

Página própria (não usa `base.html`): `templates/presentation.html` + `static/css/presentation.css` + `static/js/presentation.js`. Cada slide é uma `<section class="slide s-…" data-chapter="…">`; a navegação (setas, teclado, pontos, capítulos, toque, tela cheia, zoom) é toda do JS, sem script inline (CSP). As telas são `.webp` em `static/img/apresentacao/`, capturadas com dados de demonstração (Playwright, uma sessão por perfil: funcionário, diretoria, consulta; o admin não é mostrado). O botão no rodapé do menu e a rota dependem de `presentation_open()` (`app/utils/presentation.py`), que compara a hora de Brasília com `PRESENTATION_UNTIL`; passado o prazo o botão some e a rota devolve 404. Para refazer as telas, suba o app com um banco de demonstração (`scripts.seed_demo` + `scripts.seed_demo_company`), entre com cada perfil e recapture.

## CSS

### Tokens (`:root`)

| Grupo | Variáveis |
|---|---|
| Base | `--bg #f4f5f7`, `--surface #fff`, `--surface-2`, `--surface-3`, `--line #e5e7eb`, `--line-soft`, `--line-strong` |
| Texto | `--text #1f2937`, `--ink-2`, `--muted #5b6573` |
| Marca | `--accent #1b4f8a` (azul), `--accent-dark`, `--accent-soft`, `--accent-ink`, `--orange #f47920`, `--orange-dark`, `--orange-soft`, `--orange-line`, `--navy #10243f` |
| Estado | `--ok #1d7a46`, `--warn #9a6200`, `--bad #b3261e`, cada um com `-soft`, `-line` e (ok/bad/warn/info) `-ink` |
| Forma | `--radius 6px`, `--side 232px` (largura do menu) |

Convenção de uso: azul para ação e navegação, **laranja para o destaque principal** (botão *Importar conta*,
barra do item ativo, linha de tendência), verde/âmbar/vermelho **só** para estado (ok, atenção, erro/alta). Variação
de custo usa `var-up` em vermelho (subiu = ruim) e `var-down` em verde.

Paleta categórica dos gráficos, repetida em `chart_service.py` e `director.js`: `#1b4f8a`, `#f47920`, `#4f9a94`,
`#8a6aa3`, `#b08a3e`, `#7a8f5a` (o painel da diretoria usa 12 cores). Cinzas neutros `#9aa5b4`, `#b7c0cc`, `#7f8b9b`
para o que não é destaque; o item em destaque nos gráficos da loja é azul-escuro `#1b4f8a` com borda `#10243f`.

### Componentes principais

| Classe | O que é |
|---|---|
| `.shell`, `.side`, `.main` | grade da casca; `.side` é fixo (sticky, 100vh) |
| `.card`, `.card.flush`, `.card-head` | bloco branco com borda; `flush` remove o padding (para tabelas) |
| `.grid` + `.cols-2/3/4/.cols-main/.cols-main2` | grades; todas viram 1 coluna em ≤ 1100 px (4 colunas viram 2) |
| `.kpi` (`.label`, `.value`, `.sub`) | indicador numérico; recebe animação escalonada e *count-up* |
| `.btn` (`.primary`, `.accent`, `.danger`, `.sm`, `.cta`, `.on-dark`) | botões; `.cta` é o laranja do hero/menu, `.on-dark` é o vidro para o hero |
| `.field` (`.error`, `.flag`), `.row-2/3/4` | formulário; `.flag` pinta o campo âmbar e mostra "conferir" |
| `.seg` | grupo de opções em segmentos (radio estilizado) |
| `.flash` (`ok`, `info`, `warn`, `error`) | mensagem no topo da página; `role="alert"` em erro, `status` nos demais |
| `.badge` (`ok`, `warn`, `bad`) | rótulo de estado com ponto colorido |
| `.tablewrap`, `table` | tabela com rolagem horizontal; `td.num` alinha à direita com algarismos tabulares |
| `table.stack` | **tabela em cartões no celular** (ver abaixo) |
| `table.heat` | mapa de calor loja × mês do painel da diretoria |
| `.filterbar` | barra de filtro com borda azul à esquerda (usada em *Auditoria*) |
| `.sevfilter` / `.sevchip` | filtro por severidade da central de alertas: pílulas com contagem; `.on` é a selecionada |
| `.alist` / `.acard` | cartão de alerta com barra lateral por severidade (`sev-alta`, `sev-media`, `sev-baixa`) |
| `.toast`, `.bellpanel`, `.brow` | aviso lateral e painel do sino de vencimentos (`today`, `overdue`, `soon`) |
| `.dialog` | `<dialog>` nativo (ponto de energia rápido) |
| `.drop`, `.steps`, `.review`, `.docpane` | envio de arquivo (arrastar e soltar), progresso, conferência (campos + documento ao lado) |
| `.report`, `.sheet`, `.rtable`, `.chip`, `.infostrip`, `.sheet-foot` | folha de impressão (ver [Impressão](#impressão)) |
| `.insights` | destaques do painel da diretoria |
| `.empty` | estado vazio |
| `.skip`, `.sr` | link de pular conteúdo; texto só para leitor de tela |
| `.splash`, `.bye` | abertura e despedida |
| `.hero` | faixa de abertura |
| `.auth`, `.auth-brand`, `.auth-form`, `.auth-box` | telas de acesso |

### `table.stack`

Em ≤ 760 px, `table.stack` deixa de ser tabela: `thead` some, cada `tr` vira um cartão e cada `td` vira uma linha
`rótulo — valor`, com o rótulo vindo do atributo **`data-label`** da célula (`td::before { content:
attr(data-label) }`). Célula sem `data-label` fica sem rótulo; `td.cell-actions` alinha botões à esquerda e quebra
linha. Usada em `admin/users.html` e `admin/audit.html`, onde a rolagem lateral esconderia colunas (ações,
detalhes). As demais tabelas ficam em `.tablewrap` com rolagem horizontal (e `tabindex="0"` aplicado pelo JS).

Para usar: `<table class="stack">` e `data-label="…"` em cada `<td>`.

### Pontos de quebra

| Largura | O que muda |
|---|---|
| ≤ 1100 px | grades de 3 e 4 colunas colapsam; conferência empilha; documento deixa de ser *sticky* |
| ≤ 860 px | telas de acesso viram coluna única (painel da marca vira cabeçalho, `.auth-box` sobe 44 px sobre ele) |
| ≤ 800 px | **casca mobile**: menu vira *drawer*, aparecem `m-topbar` e `m-bottomnav` (com botão flutuante laranja *Importar*), `.topbar` interna some, KPIs em 2 colunas, botões com altura mínima de 44 px, campos com `font-size: 16px` (evita zoom no iOS) |
| ≤ 760 px | `table.stack` vira cartões; `.filterbar select` ocupa a largura toda |

A casca respeita `env(safe-area-inset-*)` (áreas seguras de iPhone) e a `meta viewport` usa `viewport-fit=cover`.

### Animações

Curtas e discretas: entrada dos cartões (`rise`), das linhas das 14 primeiras linhas de tabela (`row-in`), do
`flash` (`slide-down`), do toast (`tin`). `prefers-reduced-motion: reduce` zera as animações de forma global
(`animation-duration: .01ms`) e desliga por completo splash, despedida e animações do login.

---

## JavaScript

`app.js` é carregado com `defer` em toda página, inclusive no login. Cada bloco é uma função autoexecutável que sai
cedo se o elemento que usa não existe na página. Não há estado global, nem módulos.

### Comportamentos globais por atributo `data-*`

Delegação de eventos no `document` (por causa do CSP, não há `onclick=`):

| Atributo | Efeito |
|---|---|
| `data-print` | `window.print()` |
| `data-confirm="texto"` | `confirm()` antes de seguir (botão, link ou formulário) |
| `data-autosubmit` | envia o formulário ao mudar o campo (filtro de mês, filtro de auditoria) |
| `data-filter="seletor"` + `data-count="id"` | busca rápida em listas: esconde linhas que não contêm o texto; cabeçalhos de grupo (`.group-row`) só aparecem com filha visível; mostra "N resultado(s)" |
| `data-filter-blob` (na linha) | texto alternativo usado pela busca |
| `data-toggle-password="#id"` | botão *Mostrar/Ocultar* do campo de senha |
| `data-login-form` | formulário de login com estado "Entrando…" |
| `data-no-loading` | exclui o formulário do estado "Salvando…" |
| `data-bill-switch` | `<select>` que troca a conta na ficha de impressão |
| `data-drawer-toggle` | abre/fecha o menu mobile |
| `data-open-point`, `data-close-dialog` | abre/fecha o diálogo de ponto de energia |
| `data-copy-insights` | copia o resumo do painel da diretoria |
| `data-fit="N"` | altura útil (px) para o ajuste da folha de impressão |
| `data-flash` | nível da mensagem (ok/info somem sozinhas) |

### Splash (abertura)

`base.html` renderiza `#splash` só para usuário logado, e um `<script nonce>` no `<head>` marca `html.no-splash` se
`sessionStorage.economart_splash` já é igual ao `login_stamp` ou se o usuário prefere menos movimento. Resultado:
**uma abertura por login e por aba**, de cerca de 0,3 s (logo branca sobre o degradê, barrinha laranja), com fade. O
`app.js` grava o carimbo e remove o elemento. Se o JavaScript falhar, uma animação CSS (`splash-failsafe`, 3 s)
esconde o splash sozinha. Não aparece na impressão. A tela de login não tem splash.

### Logout com despedida

O formulário *Sair* é interceptado: o `POST /logout` sai **imediatamente** por `fetch` (com `X-CSRF-Token`,
`redirect: 'manual'`, `keepalive`) e, em paralelo, toca por cerca de 1,5 s a despedida (`#bye`: logo, barras
caindo, "Encerrando sessão…" e depois "Até logo, <usuário>"). Ao fim, se a resposta foi o redirecionamento
(`opaqueredirect`), vai para `/login?saiu=1` (que mostra "Sessão encerrada."); se o envio falhou, submete o
formulário normalmente, para nunca mostrar "sessão encerrada" sem ter encerrado. Com `prefers-reduced-motion`, a
interceptação é ignorada e o formulário segue o caminho normal.

### Indicadores com *count-up*

Valores de `.kpi .value` que são **puramente numéricos** (`R$ 1.234`, `17`, `12,5%`; regex própria) contam de zero
até o valor em 700 ms (*ease-out* cúbico), com atraso `120 + 60·i` ms por indicador. Valores com texto misturado e
valores zero não animam. O texto final é restaurado antes da impressão (`beforeprint`) e a animação não roda com
`prefers-reduced-motion`.

### Aviso de Caps Lock

No campo `#p` do login, `keydown`/`keyup` consultam `getModifierState('CapsLock')` e mostram "Caps Lock ligado"
(`#caps`, `role="status"`); some ao sair do campo.

### Selo de alertas no menu

`GET /api/alertas/contagem` preenche `#alert-count` ao lado de *Alertas* ("99+" acima de 99); a classe `hot` é
aplicada quando há alertas de severidade alta. Falha em silêncio.

### Copiar resumo

*Copiar resumo* (painel da diretoria) monta o texto `Destaques — Economart Energia` seguido de uma linha `• …` por
destaque e copia com `navigator.clipboard`; sem permissão, usa um `textarea` temporário e `execCommand('copy')`. O
botão mostra "Copiado" por 1,6 s.

### Vencimentos (sino, avisos e ponto rápido)

Só existe para `operator` (é quando `#bell` está no DOM):

- busca `GET /api/due`, pinta o sino (selo com a contagem de itens não "soon", "9+" acima de 9) e o painel;
- **toasts de 15 s**, pausados por mouse ou foco (quem navega por teclado não perde o aviso), com barra de tempo;
  no máximo 4 por vez, mais um resumo "+ N vencimentos";
- exibidos **uma vez por login e por dia**: `sessionStorage['due-shown']` guarda `login_stamp:hoje`; o logout apaga;
- **Já paguei** chama `POST /api/due/{unit}/ack` com `X-CSRF-Token` e recarrega a lista;
- no celular, o sino do topo (`#bell-m`) espelha o contador do desktop por `MutationObserver` e aciona o mesmo painel;
- `[data-open-point]` busca `GET /points/new?fragment=1&next=…`, injeta no `<dialog>` e o abre; se a requisição falha,
  navega para `/points/new`.

### Outros

- **Mensagens**: `ok` e `info` somem após 9 s; `warn` e `error` ficam. Cada `.flash` ganha um ícone SVG por nível.
- **Envio de formulário**: botões `submit` viram "Salvando…" e ficam desabilitados (aplicado com `setTimeout 0` para
  não cancelar o envio). `pageshow` com `persisted` desfaz isso ao voltar pelo histórico.
- **Barra de progresso** no topo ao clicar em link interno ou enviar formulário (desligada com
  `prefers-reduced-motion`).
- **Entrada em cascata** dos KPIs (`--d`, no máximo 180 ms de atraso).
- **Menu mobile** (*drawer*): abre pelo botão, fecha por clique no fundo, em link do menu, `Esc` ou ao passar de 800 px.
- **Folha de impressão**: `fitSheets()` calcula `--fit = min(1, data-fit / scrollHeight)` e o CSS aplica `zoom` na
  impressão. Roda no `load` e em `beforeprint`.
- **Acessibilidade automática**: associa `<label>` sem `for` ao controle do mesmo `.field`; controle sem rótulo
  ganha `aria-label` (cabeçalho da coluna, `placeholder` ou `name`); `.tablewrap` que rola horizontalmente recebe
  `tabindex="0"`, `role="region"` e `aria-label`.
- **Login**: posiciona a logo sobre o ponto final do gráfico (ver abaixo).

### Scripts específicos de página

Os que não valem para o sistema inteiro ficam inline no template, com `nonce`: `imports/upload.html` (arrastar e
soltar, prévia da imagem, botão), `imports/progress.html` (consulta `GET /import/{id}/status`), `imports/review.html`
(seleciona a opção de unidade ao focar), `manual/form.html` e `manual/batch.html` (campos dependentes, total de
lojas), `stores/history.html` (repassa o período à folha), `stores/report.html` e `bills/print.html` (desenham os
gráficos de impressão; os dados da ficha vão em `<script type="application/json" id="bill-data">`).

---

## Gráficos (Chart.js)

Chart.js 4.4.7 (UMD) em `static/js/vendor/chart.umd.min.js`. Páginas com gráfico incluem a tag explicitamente; não
há carregamento global.

| Onde | Script | Dados |
|---|---|---|
| Histórico da loja e da unidade | `chart_panel.js`, incluído por `partials/chart_panel.html` | `fetch GET /api/stores/{id}/chart` com os controles do painel |
| Painel da diretoria | `director.js` | JSON embutido em `#dir-data` |
| Folha da loja | script inline em `stores/report.html` | contexto do servidor |
| Ficha da conta | script inline em `bills/print.html` | `#bill-data` |

**`chart_panel.js`**: lê o estado inicial de `data-state` (`state|tojson`), monta barras, e a cada mudança de
controle (visão *Por unidade/Por tipo*, tipo, indicador, De, Até) refaz a requisição. Usa um contador (`inFlight`)
para descartar respostas atrasadas e `history.replaceState` para manter a URL compartilhável. Barra em destaque
(unidade da conta recém-importada) em azul-escuro com borda. O tooltip mostra o valor, a variação sobre o mês
anterior e as linhas detalhadas da série. Tipos de valor: `brl`, `kwh`, `kw`. Sem dados no período mostra "Sem dados
no período selecionado."; falha de rede mostra "Não foi possível carregar o gráfico."

**`director.js`**: oito gráficos — gasto por mês empilhado por fornecedor com linha de variação; ranking de lojas
(15 maiores); variação do último mês por loja (vermelho sobe, verde cai); composição por fornecedor (100%);
evolução das lojas (5 primeiras visíveis, seleção por caixas); R$/kWh com linha da média; uso da demanda contratada
com linha de 100%; comparação de duas lojas, com tabela de diferença em R$ e %. Animações desligadas
(`animation: false`) para a impressão sair completa. Antes de imprimir, redimensiona todas as instâncias.

Todos os `<canvas>` têm `role="img"` e `aria-label` (descrição curta do gráfico). Os dados completos para quem usa
leitor de tela estão nas tabelas HTML da mesma página (mapa de calor, comparação de duas lojas, tabela
comparativa) e nos destaques em texto do painel.

---

## Impressão

O sistema imprime em A4 e a impressão é parte do produto (a folha substitui a planilha original). Regras gerais em
`@media print`:

- esconde `.side`, `.no-print`, `.flash`, `.hero`, `.splash`, `.bye`;
- `print-color-adjust: exact` (cores de fundo e dos gráficos saem no papel; quem usa Chrome pode precisar marcar
  "Gráficos de segundo plano");
- `@page` global: **A4 paisagem**, margem 10 mm; `bills/print.html` redefine para **A4 retrato** num `<style>`
  inline.

### Folha da loja (`/stores/{id}/report`)

`.report.sheet`, A4 paisagem, uma página: cabeçalho da loja (`.sheet-head`), *Resumo mensal* com todos os
fornecedores e Total Geral, faixa de informações da última conta (`.infostrip`), gráfico de barras com linha de
variação, tabela Valor / Dias / Variação e rodapé "emitido em … por <usuário>" (`.sheet-foot`). O agrupamento por
mês de referência ou de vencimento ("Como na planilha") é escolhido na tela. O ajuste para caber em uma página é
automático (`data-fit="700"`, `zoom` na impressão); com *um por folha* (`all=1`) o ajuste fica desligado e cada
fornecedor ocupa uma folha.

### Ficha da conta (`/bills/{id}/print`)

`.report.bill-print.sheet`, A4 retrato (`data-fit="1030"`): dados da conta, comparativo com o mês anterior, itens
faturados e três gráficos dos últimos 12 meses (valor com variação, consumo HP/HFP, demanda com a contratada), com
o mês escolhido em destaque. Na tela dá para trocar de conta e marcar **Incluir foto/PDF original**
(`?doc=1`), que acrescenta uma página com o original. Como o navegador não imprime PDF embutido, as páginas do PDF
vão como imagem PNG por `GET /documents/{id}/pages/{n}.png` (até 6 páginas, ~115 dpi).

### Painel da diretoria

Botão *Imprimir painel*: aparece o cabeçalho de relatório (`.print-head`, com logo, título e metadados), os filtros
e o seletor de lojas somem, os KPIs vão a 4 por linha, os gráficos encolhem (190–210 px) e duas colunas, e **todas
as animações são desligadas** (elementos que só aparecem na impressão começariam invisíveis no primeiro quadro).

### Botões de impressão

Usam `data-print`; não há `onclick`. O botão "Imprimir códigos" do 2FA usa o mesmo atributo.

---

## Tela de login

`login.html` e `login_2fa.html` usam o mesmo layout (`.auth`, duas colunas) e `_auth_brand.html`:

- **Esquerda (painel da marca)**: degradê azul, grade com máscara, dois brilhos (`.auth-glow`) que derivam
  lentamente (22 e 26 s), título "Controle de Energia" e uma frase (`pitch`, definida pelo template: "Contas,
  vencimentos e custos de energia das lojas." no login; "Acesso de administrador protegido por verificação em
  duas etapas." no 2FA), e um painel de vidro com um gráfico **decorativo, sem números reais** (SVG com 12 barras e
  uma linha de tendência, marcado `aria-hidden`).
- **Direita**: formulário com ícones nos campos, botão de mostrar/ocultar senha, aviso de Caps Lock, e o rodapé
  "Conexão protegida · acesso monitorado".

Sequência de animação (só CSS, mais uma medição em JS):

1. as 12 barras crescem em cascata (0,35 s + 60 ms por barra, 0,9 s cada);
2. a linha laranja de tendência se desenha (de 1,1 s a ~2,9 s);
3. o ponto final aparece (2,7 s) e começa a pulsar (3 s, em laço);
4. a **logo nasce do ponto final do gráfico** (2,9 s, 1,5 s de duração): `app.js` mede o deslocamento entre a
   logo e o ponto e passa ao CSS como `--lx`/`--ly`; a logo sai pequena e desfocada daquele ponto e cresce até o
   lugar dela;
5. título, painel de vidro e rodapé sobem em fade (0,12 s, 0,3 s, 0,5 s); os filhos do `.auth-box` entram em
   sequência.

Ou seja, a composição completa leva cerca de 4,4 s; o formulário já está utilizável desde o início. No celular
(≤ 860 px) o gráfico fica escondido: `app.js` não encontra o ponto (largura 0), não define `--lx`/`--ly` e a logo
entra pela animação padrão (0,5 s de atraso, 0,9 s).

Comportamento do formulário:

- foco inicial: usuário; se a página volta de um erro (o nome digitado é preservado, a senha nunca), foco na senha;
- ao enviar, o botão mostra "Entrando…" com *spinner* e `aria-busy`;
- em erro (`401`), a página renderiza com a classe `.auth.again`: **as animações de abertura não repetem** e só a
  mensagem de erro balança (`shake`, 0,45 s);
- mensagens possíveis: "Usuário ou senha incorretos." e o bloqueio com minutos restantes, ambas em `.flash.error`
  com `role="alert"`; "Sessão encerrada." (`.flash.ok`, `role="status"`) depois do logout;
- ≤ 860 px: o painel da marca vira um cabeçalho só com a logo (frase, vidro e rodapé escondidos) e o cartão do
  formulário sobe sobre ele;
- `prefers-reduced-motion`: nenhuma animação roda e a logo aparece direto.

A tela de 2FA (`login_2fa.html`) repete o layout com um campo de código grande (`inputmode="numeric"`,
`autocomplete="one-time-code"`, aceita também o código de recuperação `abcd-ef12`) e o link "Voltar ao login".

---

## Acessibilidade

O que o código faz:

- `<html lang="pt-BR">`; link "Ir para o conteúdo" (`.skip`) que leva a `<main id="content" tabindex="-1">`;
- navegação principal em `<nav aria-label="Principal">`, item ativo com `aria-current="page"`;
- foco visível em todos os controles (`:focus-visible`); no menu escuro o contorno é branco;
- rótulos em todos os campos (e o ajuste automático do `app.js` como rede de segurança);
- mensagens com `role="alert"` (erro) e `role="status"` (demais); região de toasts `aria-live="polite"`; contador
  do sino com `aria-label` atualizado ("Vencimentos: N pendente(s)");
- botões de menu e sino com `aria-expanded` e `aria-controls`;
- toasts de vencimento pausam por foco, não só por mouse;
- tabelas largas rolam por teclado (`tabindex="0"` e `role="region"` aplicados quando há overflow);
- todo `<canvas>` com `role="img"` e `aria-label`; o painel da diretoria tem tabelas HTML equivalentes;
- `prefers-reduced-motion` respeitado em CSS e em JS (progresso, *count-up*, splash, despedida);
- alvos de toque de 44 px e campos com 16 px no mobile;
- cor nunca é o único sinal: a variação é gerada no servidor como texto com seta (`Variation.text`: "↑ 4,96%",
  "↓ 8,21%", "→ 0,00%"); severidade de alerta tem texto ("Alta", "Média", "Baixa") além da barra lateral; campos a
  conferir têm o texto "conferir".

O README afirma uma auditoria axe-core (WCAG 2.1 A/AA) em 18 telas, desktop e celular, sem violações. **Essa
auditoria não é reproduzível a partir do repositório** (nenhum script ou teste a executa) e não foi reexecutada
aqui; trate-a como informação histórica. Ela também não substitui teste com leitor de tela real.

Limites conhecidos: contraste entre o texto branco e o laranja `#f47920` do botão *cta* não foi medido; o `aria-label`
dos gráficos descreve o assunto, não os valores; o estado de carregamento ("Salvando…") não é anunciado
a leitores de tela.

---

## Convenções de texto

Regra do projeto (`AGENTS.md`): o sistema é profissional e simplificado. **Mensagens curtas, específicas, sem tom de
assistente, sem condescendência e sem mensagem genérica quando dá para dizer o que houve.**

Em prática:

- diga o que aconteceu e, se houver, o que fazer: "Dia de vencimento inválido (use de 1 a 31).", "Seu perfil é
  somente de consulta.", "É preciso manter pelo menos um administrador ativo.", "Este arquivo já foi analisado e não
  é uma conta de energia.";
- não use "Ops", "Algo deu errado", exclamações, emojis nem perguntas retóricas;
- não agradeça nem peça desculpa; sem "por favor" em mensagens de erro;
- mensagem de sucesso é um fato no passado: "Loja CD300 cadastrada.", "Conta excluída.", "Tipo “Gerador” criado.";
- erros de campo ficam junto ao campo (`.err`), com a regra, não com "inválido";
- na falha do Gemini, a mensagem traduz a causa (chave inválida, modelo não encontrado, limite atingido, serviço
  indisponível) sem expor chave, URL nem *stack*;
- nomes de ação são verbos: "Importar conta", "Confirmar e salvar", "Redefinir senha", "Baixar CSV";
- rótulos de campo sem dois-pontos; obrigatório marcado com `*`;
- aspas tipográficas “ ” nas mensagens com nome de registro; reticências `…` (um caractere);
- números e datas no padrão brasileiro: `R$ 1.234,56`, `12,5%`, `10/10/2026`, `SET/2026` (gráficos: `SET/26`),
  horário de Brasília; ausência de valor é "—".

Honestidade sobre o estado atual: ainda existem textos genéricos de última instância em `app/main.py` ("Algo deu
errado." quando o `detail` não é texto; "Ocorreu um erro inesperado. Tente novamente; se persistir, avise o
administrador." no `500`) e em `gemini_service.py` ("Não foi possível analisar a conta agora. Tente novamente em
instantes." quando não há causa conhecida). São a rede de segurança, não o padrão a seguir.

---

## Como contribuir

### Criar uma página

1. Crie `app/templates/<area>/<nome>.html` com `{% extends "base.html" %}`, `{% block title %}Nome · Economart
   Energia{% endblock %}` e `{% block content %}`.
2. Para abrir a tela com a faixa de contexto, importe e use `hero`. Para a tela de listagem comum, use
   `.page-head` com `.crumbs` e `<h1>`.
3. A rota chama `render(request, "<area>/<nome>.html", user=user, ...)` e usa a dependência de perfil adequada
   (`current_user`, `writer_required`...). Ver [`api-reference.md`](api-reference.md).
4. Todo formulário `POST` leva `{{ csrf(csrf_token) }}`; a rota leva `dependencies=[Depends(verify_csrf)]`.
5. Mensagem após ação: `flash(request, "texto.", "ok"|"info"|"warn"|"error")` e `303`.
6. JavaScript: de preferência um atributo `data-*` tratado em `app.js`. Script próprio da página vai em
   `{% block scripts %}` com `<script nonce="{{ csp_nonce }}">`. Nunca `onclick=` e nunca `<script>` sem `nonce`.
7. Estilo: reuse os componentes e os tokens. `style="…"` inline funciona (o CSP permite), mas é o que se quer evitar.
8. Item de menu novo: edite `base.html` (menu lateral e, se for atalho principal, `m-bottomnav`), com
   `aria-current` no item ativo.

### Mudar a paleta

Altere os tokens em `:root` de `app.css`. Cores de gráfico estão duplicadas em `chart_service.py` (`categorical`,
`colors`), `director.js` (`PALETTE`, `UP`, `DOWN`, …) e nos scripts inline de `stores/report.html` e
`bills/print.html`; não derivam dos tokens CSS.

### Mexer em impressão

Rode `tests/test_report_sheet.py` (confere o Total Geral da folha ao centavo) e imprima uma folha real em PDF antes
de concluir. Alterar `data-fit` ou a altura de `.rchart` muda quantas linhas cabem.

### Checagem antes de commitar

```bash
ruff check --select F,E9 .
python -m pytest -q
```

`tests/test_security.py` falha se uma página ganhar manipulador inline ou `<script>` sem `nonce`.

---

## Pontos de atenção

- **`app.js` concentra tudo** (~370 linhas, 24 KB): vencimentos, logout, splash, acessibilidade, indicadores. Cada
  bloco é isolado, mas não há módulos nem testes de JavaScript.
- **Não há teste automatizado de frontend** além dos testes HTTP que renderizam as páginas e conferem CSP e
  `nonce`. Comportamento de JavaScript (toasts, logout animado, *count-up*) é verificado só à mão.
- Cores de gráfico duplicadas fora dos tokens (acima).
- `style-src 'unsafe-inline'` no CSP por causa dos `style=` nos templates (cerca de 100). Migrá-los para classes
  permitiria remover a exceção.
- `?v={{ ASSET_VERSION }}` só muda após reiniciar o servidor; `chart.umd.min.js` não tem versão na URL.
- `chart_panel.html` inclui o `<script>` do Chart.js a cada uso; usar o parcial duas vezes na mesma página carrega
  o script duas vezes.
- Telas não testadas em navegador neste levantamento: o conteúdo acima vem da leitura do código, não de
  captura de tela.
