---
name: apresentacao-animada-pptx
description: Cria apresentações em PowerPoint (.pptx) com visual de palco escuro, luz, vidro e animação em cascata em todos os slides, no nível de um site de apresentação moderno. A IA escolhe a própria paleta para o tema. Use quando pedirem slides, deck, apresentação ou PowerPoint com "cara profissional", "animado", "moderno", "estilo apple/keynote/site", ou quando a saída precisar ser .pptx editável com animações nativas.
---

# Apresentação animada em PPTX

Esta skill produz um `.pptx` **editável**, com **animações nativas do PowerPoint** (nada de vídeo ou GIF), no
estilo de uma apresentação web premium: palco escuro com luz, manchas de cor que flutuam, títulos que sobem linha a
linha, cartões de vidro, números grandes em degradê, telas em moldura com marcadores pulsando, cortina na troca de
capítulo e barra de progresso que cresce entre os slides.

O tema é livre. A paleta é **sua**: escolha uma para cada assunto (seção "Paleta própria"). O que não muda é a
linguagem visual e o **nível de animação**.

## Como trabalhar

1. **Entenda o conteúdo e monte o roteiro** antes de desenhar: uma mensagem por slide, capítulos (2 a 5),
   capa → conteúdo → encerramento com próximo passo. Cerca de 1,5 a 2 minutos por slide ao vivo.
2. **Escolha a paleta e as fontes** (seções abaixo). Rode a checagem de contraste.
3. **Salve o motor** `motion.py` (bloco no fim deste arquivo) ao lado do seu script. Precisa de
   `pip install python-pptx pillow lxml` (python-pptx 1.0 ou mais novo).
4. **Escreva um script `build.py`** usando o kit (`stage`, `eyebrow`, `title`, `lead`, `glass`, `device`,
   `hotspot`, `curtain`, `numeral`...) e as receitas de slide. Todo slide termina com `transition(...)` e
   `m.commit()`.
5. **Confira** (seção "Conferência"): renderize em imagem, olhe cada slide, rode a checagem estrutural.
6. **Entregue** o `.pptx` dizendo: a transição Morph e os laços aparecem no PowerPoint 2019/365 (Windows ou Mac);
   no Google Slides e no Keynote as animações viram esmaecer simples ou somem, e o layout continua certo.

## Linguagem visual

**Palco** (fundo de todo slide, `stage()`):
- degradê radial com a luz saindo do alto à esquerda: `glow` → `bg1` → `bg0`;
- três manchas de luz grandes e desfocadas (accent, cool, glow) que flutuam em laço lento (26 s, 31 s, 36 s, vai e
  volta) e mudam um pouco de lugar a cada slide (com Morph, elas "andam" na troca);
- grade fina quase invisível (3,5% de opacidade, passo de 0,67 pol.);
- barra de progresso de 2 px no rodapé, em degradê cool → accent com brilho, que cresce de slide para slide;
- contador `03 / 12` no canto inferior direito (texto 55%);
- capítulos em pílula no alto, o atual preenchido com degradê quente e sombra colorida.

**Tipografia**
- *Eyebrow* (abre todo slide): caixa alta, 10–11 pt, negrito, espaçamento +2,6 pt, cor `accent2`, com um traço de
  0,42 pol. em degradê antes.
- *Título*: fonte display pesada, espaçamento **negativo** (−3,5% do tamanho), entrelinha 0,9, cada linha numa caixa
  própria. Uma palavra ou trecho de destaque por slide em **degradê quente** (`accent2` → `accent`). Tamanhos:
  capa 72–96 pt; divisor 80–96 pt; slide comum 40–50 pt; ao lado de imagem 36–44 pt.
- *Lead*: 16–19 pt, branco 80%, entrelinha 1,35, até ~60 caracteres por linha.
- *Notas e legendas*: 11–13 pt, branco 55%.
- *Números grandes*: 60–130 pt, display, espaçamento negativo, degradê branco → `accent2` → `accent`.
- *Numerais de fundo* (divisor, "01" dos passos): só contorno, branco 16–22%.

**Superfícies**
- *Vidro* (`glass`): branco 9% → 3% em degradê, contorno branco 14% de 0,75 pt, cantos de ~0,22 pol., sombra preta
  funda e difusa.
- *Ícone*: quadrado arredondado em degradê quente com sombra da própria cor; símbolo simples dentro.
- *Pílulas/chips*: branco 5,5%, contorno 14%, cantos totalmente redondos.
- *Botão*: degradê quente com sombra colorida.
- *Tela* (`device`): moldura de navegador (três bolinhas vermelha/amarela/verde, barra de endereço), sombra funda e
  um halo de luz accent/cool atrás.
- *Marcadores* (`hotspot`): círculo accent numerado com borda branca, anel pulsando, etiqueta escura ao lado.

**Composição**
- Margem lateral de 0,85–0,9 pol.; conteúdo alinhado à esquerda; muito espaço vazio.
- Cartões em grade (3 ou 4 colunas) com o mesmo tamanho e espaçamento de ~0,2 pol.
- Texto e tela lado a lado: texto em ~1/3, tela em ~2/3 (alterne o lado entre slides).
- Nunca encha o slide: se não cabe, divida em dois slides.

## Linguagem de movimento

Nada espera clique: tudo começa sozinho quando o slide abre, em **cascata**, na ordem de leitura. Ritmo do site:
primeiro elemento em 280 ms, +110 ms por item (`at(i)`), +130 ms por linha de título, entradas de 700–1000 ms com
desaceleração no fim. A cascata inteira termina em até ~2,5 s.

| No site (CSS/JS) | No PPTX (`Motion`) | Uso |
|---|---|---|
| `.rv`: sobe 28 px + aparece + desfoque | `rise()`: aparece + sobe 4,5% da altura, desacelerando | quase tudo: eyebrow, lead, cartões, itens |
| `.ln`: linha sobe de dentro de uma máscara | `line()`: limpar de baixo + subida curta | cada linha de título |
| `.dev`: tela cresce de 94% e sobe | `zoom()`: 94% → 100% + sobe + aparece | screenshots, imagem principal |
| contador 0 → N | `pop()`: surge do zero, passa 8–14% e volta | números grandes, marcadores |
| barras crescendo (`scaleY`) | `wipe(frm="bottom")` com 70 ms entre barras | gráficos decorativos, colunas |
| sublinhado crescendo (`scaleX`) | `wipe(frm="left")` | barra embaixo de cartões, traço do eyebrow |
| manchas do fundo à deriva | `drift()`: caminho vai-e-volta infinito | só no palco |
| anel `ping` do marcador | `breathe()`: escala vai-e-volta infinita | anel dos marcadores, brilho atrás de número |
| cortina na troca de capítulo | `curtain()` + `sweep()`: faixa diagonal atravessa a tela | 1º slide de cada capítulo |
| comparador antes/depois | `wipe(frm="right")` na metade "depois" + `move_in()` da alça | slide antes × depois |
| troca de slide (desliza + esmaece) | `transition("morph")` (reserva: esmaecer) | todos os slides |
| barra de progresso | forma `!!progress` + Morph | automático no `stage()` |

Regras:
- **Todo elemento de conteúdo entra animado.** Só o palco (fundo, grade, progresso, contador, capítulos) fica parado.
- **Laços infinitos só no palco e nos anéis dos marcadores.** Nunca em texto.
- **Ordem**: eyebrow → linhas do título → lead → conteúdo (cartões da esquerda para a direita) → detalhes
  (marcadores 1, 2, 3 a cada ~450 ms, depois que a tela entrou).
- **Transição**: `morph` em todos os slides; no divisor de capítulo use `fade` curto (400 ms), porque a cortina faz o
  efeito. Morph casa formas pelo nome: o kit dá nomes `!!...` às peças do palco para elas deslizarem entre slides.
- Para passar sozinho (quiosque, apresentação em loop), `transition(..., advance_ms=9000)`.
- Contagem de números (0 → N) não existe no PowerPoint: use `pop()`. Desfoque animado também não: a subida com
  esmaecer substitui.

## Receitas de slide

Coordenadas em polegadas num slide 16:9 (13,333 × 7,5). `m = stage(...)` sempre primeiro.

**Capa**: eyebrow (y≈1,55) · título de 2 linhas 72–90 pt com a palavra-chave em destaque · lead · 2 a 4 chips
(`rise` a cada meio passo) · à direita, 10–14 barras arredondadas no alto (`ROUND_2_SAME_RECTANGLE`) em degradê
vertical accent/cool que somem para baixo, com brilho, crescendo com `wipe(frm="bottom")`. Transição `fade`.

**Passos (3–4)**: eyebrow · título em 2 linhas · cartões de vidro lado a lado, cada um com ícone, numeral "01" em
contorno no canto, título 20 pt, texto 12–13 pt e um sublinhado quente embaixo (`wipe` da esquerda, depois do cartão).

**Números (3–5)**: cartões de vidro com o número enorme em degradê (`pop` com overshoot 1,08) e a legenda embaixo
(`rise` 250 ms depois).

**Divisor de capítulo**: numeral gigante em contorno à direita (`fade` lento, 1,4 s) · eyebrow "Capítulo N" ·
título 80–96 pt · lead · `curtain(s, t, m)`. Transição `fade` 400 ms.

**Texto + tela**: à esquerda eyebrow, título 2 linhas, 3–4 itens com losango em degradê; à direita `device()` com
o screenshot e 2–3 `hotspot()` sobre ele. Alterne os lados entre slides seguidos.

**Antes × depois**: imagem "antes" inteira (`zoom`); por cima, a metade direita da imagem "depois"
(`crop_left = .5`) entrando com `wipe(frm="right")` em 1,9 s a partir de 1,1 s; alça (linha branca com brilho +
círculo accent "⟷") com `move_in()` sincronizada; etiquetas "Antes" (escura) e "Depois" (accent) no alto.

**Cartões (3)**: vidro, ícone em quadrado frio translúcido, título 22 pt, texto 13 pt.

**Encerramento**: eyebrow "Próximo passo" · título grande com a data ou o pedido em destaque · botão em degradê.

## Paleta própria

Escolha uma paleta **para o assunto**, não uma genérica. Se trocar a paleta por outra apresentação e ela "servir
igual", ela não é específica o bastante. Monte assim:

1. **Matiz do palco**: um matiz ligado ao tema (café → marrom; saúde → verde-azulado; finanças → azul-petróleo;
   energia → azul-noite; moda → ameixa). `bg0` com luminosidade ~5%, `bg1` ~12–15% do mesmo matiz, `glow` ~25–30%
   e mais saturado (é a luz do canto).
2. **Accent quente**: a cor de ação, bem saturada, em contraste de matiz com o palco (laranja, coral, cobre,
   magenta, âmbar, lima). É ela que domina os destaques.
3. **accent2**: o mesmo accent bem mais claro (eyebrows, fim dos degradês).
4. **cool**: uma cor de apoio fria ou complementar (menta, ciano, lavanda), usada com parcimônia: segunda série,
   uma das manchas, ícones dos cartões.
5. Texto sempre branco (`ink`), com 80% e 55% para os níveis secundários.

Proporção: palco ~70%, accent ~15–20%, cool ≤ 10%. Um accent só; nada de arco-íris.

Cheque o contraste antes de construir (o kit tem `contrast` e `mix`):

```python
for nome, cor, a in (("texto", t.ink, 1), ("texto 80%", t.ink, .8), ("texto 55%", t.ink, .55), ("eyebrow", t.accent2, 1)):
    c = contrast(mix(t.bg0, cor, a) if a < 1 else cor, t.bg1)
    assert c >= 4.5, (nome, c)          # texto pequeno: 4,5:1 no mínimo
assert contrast(t.accent, t.bg1) >= 3   # destaque em título grande: 3:1 no mínimo
```

Palco claro só se o tema pedir (ex.: um relatório para imprimir): `bg0`/`bg1` quase brancos, `ink` escuro, `glow`
um tom pastel; o kit funciona igual, porque vidro, grade e textos derivam de `ink`. O palco escuro é a assinatura
do estilo: prefira-o.

Exemplos só para calibrar (não copie):

| Tema | bg0 | bg1 | glow | accent | accent2 | cool |
|---|---|---|---|---|---|---|
| Café especial | 0E0907 | 24150F | 5A2E1A | E8743B | F6C177 | 5FC9B0 |
| Clínica | 04121A | 0A2633 | 0F4C5C | FF6B6B | FFC2B8 | 7ADFD0 |
| Investimentos | 060B14 | 0E1A2E | 1D3A66 | F2B33D | FFE3A3 | 7FA7FF |

## Fontes

Use fontes que existem no PowerPoint de quem vai abrir. Pares que funcionam:

| Display (títulos) | Texto | Onde existe |
|---|---|---|
| Segoe UI Black | Segoe UI | Windows |
| Aptos Display (negrito) | Aptos | Microsoft 365 |
| Bahnschrift SemiBold | Segoe UI | Windows 10+ |
| Arial Black | Arial | Windows e Mac |
| Georgia (negrito) | Arial | Windows e Mac (tom editorial) |

Defina em `Theme(display=..., text=...)`. A prévia no LibreOffice troca a fonte por uma parecida: a largura pode
variar um pouco, por isso o kit recusa linha de título que não cabe com folga (`est_width`).

## O kit (resumo do `motion.py`)

| Função | O que faz |
|---|---|
| `Theme(bg0, bg1, glow, accent, accent2, cool, display=, text=, chapters=[...])` | paleta, fontes e capítulos |
| `stage(slide, t, i, total, capítulo)` → `Motion` | palco completo; chame primeiro |
| `eyebrow(s, t, x, y, texto, m, i)` | rótulo com traço, animado |
| `title(s, t, x, y, w, [linhas], pt, m, i, emphasis=)` → `(caixas, y_fim)` | título em linhas, com destaque |
| `lead(s, t, x, y, w, texto, m, i)` | parágrafo de apoio |
| `text(s, x, y, w, h, texto, pt, t, alpha=, bold=, font=, align=, spc=)` | texto simples (sem animação) |
| `glass(s, t, x, y, w, h)` | cartão de vidro |
| `icon_tile(s, t, x, y, "✦")` | ícone em quadrado quente |
| `numeral(s, t, x, y, w, h, "03", pt)` | número gigante em contorno |
| `device(s, t, imagem, x, y, w, legenda, m, i)` → `(grupo, (ix, iy, iw, ih), pic)` | tela em moldura |
| `hotspot(s, t, cx, cy, n, rótulo, m, atraso, side="r")` | marcador numerado |
| `curtain(s, t, m)` | cortina de capítulo |
| `fill`, `gradient`, `line`, `effects(glow=, shadow=, soft_edge_pt=)`, `corner`, `text_gradient`, `text_outline`, `tracking`, `background` | acabamento |
| `transition(s, "morph"\|"fade"\|"push"\|"wipe"\|"cover"\|"split"\|"zoom", dur, advance_ms=)` | transição |
| `Motion`: `rise`, `fade`, `line`, `wipe`, `zoom`, `pop`, `sweep`, `move_in`, `drift`, `breathe`, `commit` | animações |
| `at(i)`, `BASE`, `STEP`, `LINE_STEP` | ritmo da cascata |
| `alt_text(forma, texto)`, `notes(s, texto)` | acessibilidade e notas do apresentador |

Texto translúcido (`alpha` < 1) vira cor sólida misturada com o fundo: o LibreOffice e o Google Slides cortam a
última letra de texto com transparência.

## Exemplo mínimo

```python
from pptx import Presentation
from pptx.util import Inches
from pptx.enum.shapes import MSO_SHAPE
from motion import *

t = Theme(bg0="0E0907", bg1="24150F", glow="5A2E1A", accent="E8743B", accent2="F6C177", cool="5FC9B0",
          chapters=["A marca", "O produto"])
prs = Presentation(); prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
TOTAL = 3

# capa
s = prs.slides.add_slide(prs.slide_layouts[6]); m = stage(s, t, 0, TOTAL, "A marca")
eyebrow(s, t, .9, 1.55, "Torrefação Serra Alta", m, 0)
_, y = title(s, t, .85, 1.95, 7.6, ["Café que", "chega quente"], 80, m, 1, emphasis="quente")
lead(s, t, .9, y + .25, 6.4, "Do grão à xícara em 48 horas.", m, 4, size=19)
for k, h in enumerate([.3, .5, .4, .65, .5, .8, .6, .95, .7, 1.0]):
    b = s.shapes.add_shape(MSO_SHAPE.ROUND_2_SAME_RECTANGLE, Inches(8.4 + k * .45), Inches(7.45 - 4.4 * h), Inches(.34), Inches(4.4 * h))
    c = t.cool if k % 3 == 2 else t.accent
    gradient(b, [(0, c, .95), (.75, c, .12), (1, c, 0)], angle=90); line(b, None); effects(b, glow=(c, .35, 10))
    m.wipe(b, 300 + k * 70, dur=1300, frm="bottom")
notes(s, "Abra com a promessa.")
transition(s, "fade", 700); m.commit()

# divisor de capítulo
s = prs.slides.add_slide(prs.slide_layouts[6]); m = stage(s, t, 1, TOTAL, "O produto")
m.fade(numeral(s, t, 6.6, .55, 6.5, 6.4, "02", 360, alpha=.16), at(1), dur=1400)
eyebrow(s, t, .9, 2.4, "Capítulo 2", m, 1)
title(s, t, .85, 2.8, 9.5, ["O produto"], 84, m, 2, emphasis="produto")
curtain(s, t, m)
transition(s, "fade", 400); m.commit()

# números
s = prs.slides.add_slide(prs.slide_layouts[6]); m = stage(s, t, 2, TOTAL, "O produto")
eyebrow(s, t, .9, .95, "Em resumo", m, 0)
title(s, t, .85, 1.3, 11, ["Em números"], 46, m, 1, emphasis="números")
for n, (big, lab) in enumerate([("48 h", "da torra à porta"), ("12", "origens por ano"), ("84+", "pontos de nota")]):
    x = .9 + n * 3.9
    m.rise(glass(s, t, x, 2.6, 3.65, 3.4), at(2 + n))
    tb = text(s, x + .3, 2.9, 3.1, 1.6, big, 66, t, bold=True, font=t.display, spc=-3)
    text_gradient(tb.text_frame.paragraphs[0].runs[0], [(0, "FFFFFF", 1), (.55, t.accent2, 1), (1, t.accent, 1)], 60)
    m.pop(tb, at(2 + n) + 450, overshoot=1.08)
    m.rise(text(s, x + .3, 4.7, 3.1, 1, lab, 14, t, alpha=.8), at(2 + n) + 250)
transition(s, "morph", 900); m.commit()

prs.save("apresentacao.pptx")
```

## Conferência

**1. Veja cada slide** como imagem e procure: texto saindo de caixa ou sobrepondo, elemento colado na borda,
contraste fraco, slide cheio demais. A imagem mostra o **estado final** de cada slide (a cortina começa fora do
slide e a alça do antes/depois já está no meio, então nada fica escondido na prévia).

```bash
soffice --headless --convert-to pdf apresentacao.pptx && pdftoppm -r 60 -png apresentacao.pdf slide
```

**2. Checagem estrutural** das animações:

```python
import re, zipfile
from lxml import etree
z = zipfile.ZipFile("apresentacao.pptx")
for name in sorted(n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)):
    raw = z.read(name).decode(); x = etree.fromstring(raw.encode())
    kids = [etree.QName(c).localname for c in x]
    ids = re.findall(r'<p:cTn id="(\d+)"', raw)
    alvos = set(re.findall(r'spTgt spid="(\d+)"', raw))
    formas = set(x.xpath("//p:cNvPr/@id", namespaces={"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}))
    assert kids[:2] == ["cSld", "clrMapOvr"] and "timing" in kids, (name, kids)
    assert len(ids) == len(set(ids)) and alvos <= formas, name
    print(name, "ok,", len(alvos), "formas animadas")
```

**3. Animações no LibreOffice** (opcional): `soffice --headless --convert-to odp apresentacao.pptx` e procure
`anim:` no `content.xml` de dentro do `.odp`; se as entradas aparecem lá, o arquivo está sendo lido.

**4.** Morph, laços e cortina só se veem rodando a apresentação no PowerPoint. Diga isso ao entregar.

Erros comuns:
- `ValueError: linha de título não cabe`: reduza o tamanho, encurte ou quebre em mais linhas. Não aumente a caixa
  para fora da margem.
- Chamar `m.commit()` antes de terminar de adicionar animações no slide: o `commit` grava só o que já existe.
- Esquecer `stage()` primeiro: o fundo fica por cima do conteúdo.
- Animar forma que está dentro de um grupo: anime o grupo inteiro.
- Cor com `#` ou com 8 dígitos: use 6 dígitos hex sem `#`.

## motion.py

Salve exatamente como está, num arquivo `motion.py` ao lado do script.

```python
"""motion.py: estilo e animação de apresentação para python-pptx (transições, entradas em cascata, laços).

Tudo é OOXML nativo do PowerPoint: nenhuma imagem animada, nenhum vídeo. Use com python-pptx >= 1.0.
"""
import itertools
from lxml import etree
from pptx.oxml.ns import qn
from pptx.util import Emu

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
P159 = "http://schemas.microsoft.com/office/powerpoint/2015/09/main"

# ----------------------------------------------------------------------------- ritmo (igual ao site)
BASE = 280        # ms até o primeiro elemento começar depois que o slide abre
STEP = 110        # ms entre um elemento e o próximo da cascata
LINE_STEP = 130   # ms entre linhas de um título
DUR = 750         # duração padrão de uma entrada


def at(i: float, base: int = BASE, step: int = STEP) -> int:
    """Atraso do i-ésimo item da cascata (ms)."""
    return int(base + i * step)


# ----------------------------------------------------------------------------- cor, preenchimento, efeitos
def _hex(c: str) -> str:
    c = c.lstrip("#").upper()
    assert len(c) == 6, f"cor precisa ter 6 dígitos hex: {c}"
    return c


def _clr(c: str, alpha: float = 1.0) -> str:
    a = "" if alpha >= 1 else f'<a:alpha val="{int(alpha * 100000)}"/>'
    return f'<a:srgbClr val="{_hex(c)}">{a}</a:srgbClr>'


def _grad_xml(stops, angle: float | None = 90, radial: str | None = None, center=(.5, .5)) -> str:
    """stops = [(posição 0..1, cor, alfa)]. angle em graus (90 = de cima para baixo) ou radial = "circle"
    (center = de onde a luz sai, em fração da forma)."""
    gs = "".join(f'<a:gs pos="{int(p * 100000)}">{_clr(c, a)}</a:gs>' for p, c, a in stops)
    if radial:
        cx, cy = (int(v * 100000) for v in center)
        shade = (f'<a:path path="{radial}"><a:fillToRect l="{cx}" t="{cy}" r="{100000 - cx}" b="{100000 - cy}"/>'
                 f'</a:path>')
    else:
        shade = f'<a:lin ang="{int(angle * 60000)}" scaled="0"/>'
    return f'<a:gradFill xmlns:a="{A}" rotWithShape="1"><a:gsLst>{gs}</a:gsLst>{shade}</a:gradFill>'


def _spPr(shape):
    return shape._element.spPr


def _replace_fill(spPr, xml: str):
    for tag in ("a:noFill", "a:solidFill", "a:gradFill", "a:blipFill", "a:pattFill", "a:grpFill"):
        for el in spPr.findall(qn(tag)):
            spPr.remove(el)
    el = etree.fromstring(xml)
    geom = spPr.find(qn("a:prstGeom")) if spPr.find(qn("a:prstGeom")) is not None else spPr.find(qn("a:custGeom"))
    if geom is not None:
        geom.addnext(el)
    else:
        spPr.append(el)


def fill(shape, color: str, alpha: float = 1.0):
    _replace_fill(_spPr(shape), f'<a:solidFill xmlns:a="{A}">{_clr(color, alpha)}</a:solidFill>')


def gradient(shape, stops, angle: float = 90, radial: str | None = None):
    _replace_fill(_spPr(shape), _grad_xml(stops, angle, radial))


def no_fill(shape):
    _replace_fill(_spPr(shape), f'<a:noFill xmlns:a="{A}"/>')


def line(shape, color: str | None, alpha: float = 1.0, width_pt: float = 1.0):
    spPr = _spPr(shape)
    for el in spPr.findall(qn("a:ln")):
        spPr.remove(el)
    inner = '<a:noFill/>' if color is None else f'<a:solidFill>{_clr(color, alpha)}</a:solidFill>'
    ln = etree.fromstring(f'<a:ln xmlns:a="{A}" w="{int(width_pt * 12700)}">{inner}</a:ln>')
    after = None
    for tag in ("a:noFill", "a:solidFill", "a:gradFill", "a:blipFill", "a:pattFill", "a:grpFill"):
        after = spPr.find(qn(tag)) if spPr.find(qn(tag)) is not None else after
    if after is not None:
        after.addnext(ln)
    else:
        geom = spPr.find(qn("a:prstGeom"))
        (geom.addnext(ln) if geom is not None else spPr.append(ln))


def effects(shape, glow: tuple | None = None, soft_edge_pt: float | None = None, shadow: tuple | None = None):
    """glow=(cor, alfa, raio_pt); shadow=(cor, alfa, desfoque_pt, distância_pt); soft_edge_pt=borda esfumada."""
    spPr = _spPr(shape)
    for el in spPr.findall(qn("a:effectLst")):
        spPr.remove(el)
    parts = []
    if glow:
        c, a, r = glow
        parts.append(f'<a:glow rad="{int(r * 12700)}">{_clr(c, a)}</a:glow>')
    if shadow:
        c, a, blur, dist = shadow
        parts.append(f'<a:outerShdw blurRad="{int(blur * 12700)}" dist="{int(dist * 12700)}" dir="5400000" '
                     f'algn="t" rotWithShape="0">{_clr(c, a)}</a:outerShdw>')
    if soft_edge_pt:
        parts.append(f'<a:softEdge rad="{int(soft_edge_pt * 12700)}"/>')
    el = etree.fromstring(f'<a:effectLst xmlns:a="{A}">{"".join(parts)}</a:effectLst>')
    ln = spPr.find(qn("a:ln"))
    anchor = ln if ln is not None else None
    if anchor is None:
        for tag in ("a:noFill", "a:solidFill", "a:gradFill", "a:blipFill", "a:pattFill"):
            if spPr.find(qn(tag)) is not None:
                anchor = spPr.find(qn(tag))
    (anchor.addnext(el) if anchor is not None else spPr.append(el))


def corner(shape, ratio: float):
    """Arredondamento de ROUNDED_RECTANGLE: fração do lado menor (0.12 ≈ cartão; 0.5 = pílula)."""
    shape.adjustments[0] = max(0.0, min(0.5, ratio))


def background(slide, stops, radial: str | None = "circle", angle: float = 90, center=(.2, 0)):
    """Fundo do slide em degradê. Radial com a luz saindo do alto à esquerda, como o "palco" do site."""
    cSld = slide._element.find(qn("p:cSld"))
    for el in cSld.findall(qn("p:bg")):
        cSld.remove(el)
    bg = etree.fromstring(f'<p:bg xmlns:p="{P}" xmlns:a="{A}"><p:bgPr>{_grad_xml(stops, angle, radial, center)}'
                          f'<a:effectLst/></p:bgPr></p:bg>')
    cSld.insert(0, bg)


def text_gradient(run, stops, angle: float = 0):
    """Degradê dentro das letras (palavra de destaque do título)."""
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:solidFill", "a:gradFill", "a:noFill"):
        for el in rPr.findall(qn(tag)):
            rPr.remove(el)
    el = etree.fromstring(_grad_xml(stops, angle))
    ln = rPr.find(qn("a:ln"))
    (ln.addnext(el) if ln is not None else rPr.insert(0, el))


def text_outline(run, color: str, alpha: float = 0.22, width_pt: float = 1.5):
    """Letra só com contorno (numeral gigante dos divisores, números "01" dos passos)."""
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ln", "a:solidFill", "a:gradFill", "a:noFill"):
        for el in rPr.findall(qn(tag)):
            rPr.remove(el)
    rPr.insert(0, etree.fromstring(f'<a:noFill xmlns:a="{A}"/>'))
    rPr.insert(0, etree.fromstring(f'<a:ln xmlns:a="{A}" w="{int(width_pt * 12700)}"><a:solidFill>{_clr(color, alpha)}'
                                   f'</a:solidFill></a:ln>'))


def tracking(run, points: float):
    """Espaço entre letras em pontos (negativo aperta títulos grandes; positivo abre os "eyebrows")."""
    run._r.get_or_add_rPr().set("spc", str(int(points * 100)))


def alt_text(shape, text: str):
    shape._element.xpath("./*[1]/p:cNvPr")[0].set("descr", text)


# ----------------------------------------------------------------------------- transições
def _place_transition(slide, el):
    sld = slide._element
    for old in sld.findall(qn("p:transition")) + sld.findall(f"{{{MC}}}AlternateContent"):
        sld.remove(old)
    timing = sld.find(qn("p:timing"))
    if timing is not None:
        timing.addprevious(el)
    else:
        ext = sld.find(qn("p:extLst"))
        (ext.addprevious(el) if ext is not None else sld.append(el))


def transition(slide, kind: str = "morph", dur: int = 900, advance_ms: int | None = None, direction: str = "l"):
    """kind: morph (o padrão do estilo), fade, push, wipe, cover, split, zoom.
    Morph pede PowerPoint 2019/365: os outros programas usam o esmaecer de reserva."""
    adv = f' advTm="{advance_ms}"' if advance_ms else ""
    spd = "slow" if dur >= 900 else "med" if dur >= 600 else "fast"
    simple = {"fade": "<p:fade/>", "push": f'<p:push dir="{direction}"/>', "wipe": f'<p:wipe dir="{direction}"/>',
              "cover": f'<p:cover dir="{direction}"/>', "split": '<p:split orient="vert" dir="out"/>',
              "zoom": '<p:zoom dir="in"/>'}
    if kind == "morph":
        xml = (f'<mc:AlternateContent xmlns:mc="{MC}" xmlns:p="{P}" xmlns:p14="{P14}">'
               f'<mc:Choice xmlns:p159="{P159}" Requires="p159">'
               f'<p:transition spd="slow" p14:dur="{dur}"{adv}><p159:morph option="byObject"/></p:transition></mc:Choice>'
               f'<mc:Fallback><p:transition spd="{spd}"{adv}><p:fade/></p:transition></mc:Fallback></mc:AlternateContent>')
    else:
        xml = (f'<mc:AlternateContent xmlns:mc="{MC}" xmlns:p="{P}" xmlns:p14="{P14}">'
               f'<mc:Choice Requires="p14"><p:transition spd="{spd}" p14:dur="{dur}"{adv}>{simple[kind]}</p:transition></mc:Choice>'
               f'<mc:Fallback><p:transition spd="{spd}"{adv}>{simple[kind]}</p:transition></mc:Fallback></mc:AlternateContent>')
    _place_transition(slide, etree.fromstring(xml))


# ----------------------------------------------------------------------------- animações
class Motion:
    """Junta as animações de um slide e grava o <p:timing>. Tudo começa sozinho quando o slide abre
    (sem clique), cada efeito com o seu atraso: é a cascata do site.

        m = Motion(slide)
        m.rise(eyebrow, at(0)); m.line(title_l1, at(1, step=LINE_STEP)); m.pop(stat, at(3))
        m.drift(blob, dx=.06, dy=.04, dur=26000)          # laço infinito, vai e volta
        m.commit()
    """

    def __init__(self, slide):
        self.slide = slide
        self.items: list[tuple[int, str, list, dict]] = []   # (atraso, classe, comportamentos, extras)
        self._ids = itertools.count(4)
        self.text_shapes: set[int] = set()

    # --- peças de comportamento
    def _id(self):
        return next(self._ids)

    @staticmethod
    def _tgt(spid):
        return f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'

    def _visible(self, spid):
        return (f'<p:set><p:cBhvr><p:cTn id="{self._id()}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/>'
                f'</p:stCondLst></p:cTn>{self._tgt(spid)}<p:attrNameLst><p:attrName>style.visibility</p:attrName>'
                f'</p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>')

    def _filter(self, spid, flt, dur, direction="in"):
        return (f'<p:animEffect transition="{direction}" filter="{flt}"><p:cBhvr><p:cTn id="{self._id()}" dur="{dur}"/>'
                f'{self._tgt(spid)}</p:cBhvr></p:animEffect>')

    def _prop(self, spid, attr, keys, dur, decel=100000, accel=0):
        tav = "".join(f'<p:tav tm="{int(t * 100000)}"><p:val><p:strVal val="{v}"/></p:val></p:tav>' for t, v in keys)
        ease = (f' decel="{decel}"' if decel else "") + (f' accel="{accel}"' if accel else "")
        return (f'<p:anim calcmode="lin" valueType="num"><p:cBhvr additive="base"><p:cTn id="{self._id()}" dur="{dur}"'
                f'{ease} fill="hold"/>{self._tgt(spid)}<p:attrNameLst><p:attrName>{attr}</p:attrName></p:attrNameLst>'
                f'</p:cBhvr><p:tavLst>{tav}</p:tavLst></p:anim>')

    def _motion(self, spid, dx, dy, dur, accel=0, decel=0, sx=0.0, sy=0.0):
        ease = (f' accel="{accel}"' if accel else "") + (f' decel="{decel}"' if decel else "")
        return (f'<p:animMotion origin="layout" path="M {sx:.4f} {sy:.4f} L {dx:.4f} {dy:.4f} E" pathEditMode="relative" '
                f'ptsTypes="AA"><p:cBhvr><p:cTn id="{self._id()}" dur="{dur}"{ease} fill="hold"/>{self._tgt(spid)}'
                f'<p:attrNameLst><p:attrName>ppt_x</p:attrName><p:attrName>ppt_y</p:attrName></p:attrNameLst>'
                f'</p:cBhvr><p:rCtr x="0" y="0"/></p:animMotion>')

    def _scale(self, spid, by, dur):
        return (f'<p:animScale><p:cBhvr><p:cTn id="{self._id()}" dur="{dur}" fill="hold"/>{self._tgt(spid)}</p:cBhvr>'
                f'<p:by x="{int(by * 100000)}" y="{int(by * 100000)}"/></p:animScale>')

    def _add(self, shape, delay, cls, preset, sub, behaviors, **extra):
        spid = shape.shape_id
        if shape._element.tag == qn("p:sp") and shape._element.find(qn("p:txBody")) is not None:
            self.text_shapes.add(spid)
        self.items.append((int(delay), cls, behaviors(spid), dict(preset=preset, sub=sub, **extra)))
        return self

    # --- entradas (o elemento começa escondido e aparece)
    def rise(self, shape, delay, dur=DUR, dist=0.045):
        """Sobe e aparece (a revelação padrão do site: .rv). dist = fração da altura do slide."""
        return self._add(shape, delay, "entr", 42, 0, lambda s: self._visible(s) + self._filter(s, "fade", int(dur * .8))
                         + self._prop(s, "ppt_y", [(0, f"#ppt_y+{dist}"), (1, "#ppt_y")], dur))

    def fade(self, shape, delay, dur=DUR):
        return self._add(shape, delay, "entr", 10, 0, lambda s: self._visible(s) + self._filter(s, "fade", dur))

    def line(self, shape, delay, dur=950):
        """Linha de título que sobe de dentro de uma "máscara" (.ln do site): limpar de baixo + subir."""
        return self._add(shape, delay, "entr", 22, 4, lambda s: self._visible(s) + self._filter(s, "wipe(up)", int(dur * .7))
                         + self._prop(s, "ppt_y", [(0, "#ppt_y+0.03"), (1, "#ppt_y")], dur))

    def wipe(self, shape, delay, dur=1100, frm="left"):
        """Revela limpando. frm: left, right, bottom, top (barras que crescem, sublinhados, antes/depois)."""
        flt = {"left": "wipe(right)", "right": "wipe(left)", "bottom": "wipe(up)", "top": "wipe(down)"}[frm]
        sub = {"left": 8, "right": 2, "bottom": 4, "top": 1}[frm]
        return self._add(shape, delay, "entr", 22, sub, lambda s: self._visible(s) + self._filter(s, flt, dur))

    def zoom(self, shape, delay, dur=1000, frm=0.94, dist=0.06):
        """Tela/imagem principal: cresce um pouco, sobe e aparece (.dev do site)."""
        return self._add(shape, delay, "entr", 53, 16, lambda s: self._visible(s) + self._filter(s, "fade", int(dur * .7))
                         + self._prop(s, "ppt_w", [(0, f"#ppt_w*{frm}"), (1, "#ppt_w")], dur)
                         + self._prop(s, "ppt_h", [(0, f"#ppt_h*{frm}"), (1, "#ppt_h")], dur)
                         + self._prop(s, "ppt_y", [(0, f"#ppt_y+{dist}"), (1, "#ppt_y")], dur))

    def pop(self, shape, delay, dur=600, overshoot=1.14):
        """Surge do zero e passa um pouco do tamanho (números grandes, marcadores numerados)."""
        keys_w = [(0, "0"), (0.7, f"#ppt_w*{overshoot}"), (1, "#ppt_w")]
        keys_h = [(0, "0"), (0.7, f"#ppt_h*{overshoot}"), (1, "#ppt_h")]
        return self._add(shape, delay, "entr", 53, 16, lambda s: self._visible(s) + self._filter(s, "fade", int(dur * .5))
                         + self._prop(s, "ppt_w", keys_w, dur, decel=0) + self._prop(s, "ppt_h", keys_h, dur, decel=0))

    def sweep(self, shape, delay, dur=950, across: float = 2.3):
        """Cortina de troca de capítulo: a forma (fora do slide, à esquerda) atravessa a tela inteira."""
        return self._add(shape, delay, "path", 0, 0, lambda s: self._visible(s)
                         + self._motion(s, across, 0, dur, accel=45000, decel=45000))

    def move_in(self, shape, delay, frm_dx, frm_dy=0.0, dur=1900):
        """Aparece deslocada (frm_dx/frm_dy em fração do slide) e desliza até onde está no slide (alça do antes/depois).
        Em PDF ou miniatura a forma aparece na posição final."""
        return self._add(shape, delay, "path", 0, 0, lambda s: self._visible(s)
                         + self._motion(s, 0, 0, dur, decel=100000, sx=frm_dx, sy=frm_dy))

    # --- ênfase em laço (o "palco vivo")
    def drift(self, shape, dx=0.06, dy=0.04, dur=26000, delay=0):
        """Vai e volta para sempre (manchas de luz do fundo)."""
        return self._add(shape, delay, "path", 0, 0, lambda s: self._motion(s, dx, dy, dur, accel=50000, decel=50000),
                         repeat=True)

    def breathe(self, shape, by=1.12, dur=2400, delay=0):
        """Pulsa para sempre (anel em volta de marcador, brilho atrás de número)."""
        return self._add(shape, delay, "emph", 6, 0, lambda s: self._scale(s, by, dur), repeat=True)

    # --- gravação
    def commit(self):
        if not self.items:
            return
        self.items.sort(key=lambda x: x[0])
        pars = []
        for k, (delay, cls, beh, ex) in enumerate(self.items):
            node = "afterEffect" if k == 0 else "withEffect"
            rep = ' repeatCount="indefinite" autoRev="1"' if ex.get("repeat") else ""
            pars.append(f'<p:par><p:cTn id="{self._id()}" presetID="{ex["preset"]}" presetClass="{cls}" '
                        f'presetSubtype="{ex["sub"]}" fill="hold" grpId="0" nodeType="{node}"{rep}>'
                        f'<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst><p:childTnLst>{beh}</p:childTnLst>'
                        f'</p:cTn></p:par>')
        bld = "".join(f'<p:bldP spid="{s}" grpId="0" animBg="1"/>' for s in sorted(self.text_shapes))
        xml = (f'<p:timing xmlns:p="{P}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">'
               f'<p:childTnLst><p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
               f'<p:childTnLst><p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/>'
               f'<p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst>'
               f'<p:par><p:cTn id="{self._id()}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
               f'{"".join(pars)}</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>'
               f'</p:childTnLst></p:cTn><p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl>'
               f'</p:cond></p:prevCondLst><p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl>'
               f'</p:cond></p:nextCondLst></p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>'
               + (f'<p:bldLst>{bld}</p:bldLst>' if bld else "") + '</p:timing>')
        sld = self.slide._element
        for old in sld.findall(qn("p:timing")):
            sld.remove(old)
        el = etree.fromstring(xml)
        for n, ctn in enumerate(el.iter(qn("p:cTn")), 1):     # ids na ordem do documento, como o PowerPoint grava
            ctn.set("id", str(n))
        ext = sld.find(qn("p:extLst"))
        (ext.addprevious(el) if ext is not None else sld.append(el))


# ----------------------------------------------------------------------------- contraste (WCAG)
def contrast(fg: str, bg: str) -> float:
    def lum(c):
        c = _hex(c)
        ch = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def mix(c1: str, c2: str, t: float) -> str:
    """Cor entre c1 e c2 (t=0 → c1). Útil para "branco a 55% sobre o fundo" na hora de checar contraste."""
    a, b = _hex(c1), _hex(c2)
    return "".join(f"{round(int(a[i:i+2], 16) * (1 - t) + int(b[i:i+2], 16) * t):02X}" for i in (0, 2, 4))


EMU_PER_IN = 914400
SLIDE_W, SLIDE_H = Emu(12192000), Emu(6858000)     # 16:9 (13,333 × 7,5 pol.)


# ============================================================================= kit visual
from dataclasses import dataclass, field          # noqa: E402
from pptx.enum.shapes import MSO_SHAPE             # noqa: E402
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN    # noqa: E402
from pptx.util import Inches, Pt                   # noqa: E402


@dataclass
class Theme:
    """A paleta é escolhida pela IA para cada tema (ver SKILL.md, "Paleta própria")."""
    bg0: str            # fundo mais escuro (bordas do palco)
    bg1: str            # fundo do centro de luz
    glow: str           # cor da luz no canto do palco
    accent: str         # cor quente principal (destaques, botões, barras)
    accent2: str        # tom claro do accent (eyebrow, fim dos degradês)
    cool: str           # cor fria de apoio (segunda série, ícones)
    ink: str = "FFFFFF"  # texto
    display: str = "Segoe UI Black"   # títulos
    text: str = "Segoe UI"            # texto corrido
    chapters: list = field(default_factory=list)


def _tb(slide, x, y, w, h, name=None):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE          # caixa fixa: o layout não muda com a fonte que o PC tiver
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    if name:
        tb.name = name
    return tb


def _run(p, text, size, color, font, bold=False, alpha=1.0, spc=None, bg=None):
    """Texto translúcido vira cor sólida misturada com o fundo (bg): o LibreOffice e o Google Slides cortam a última
    letra de texto com transparência, e o resultado na tela é o mesmo."""
    if alpha < 1 and bg:
        color, alpha = mix(bg, color, alpha), 1.0
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.name = font
    rPr = r._r.get_or_add_rPr()
    for el in rPr.findall(qn("a:solidFill")):
        rPr.remove(el)
    rPr.insert(0, etree.fromstring(f'<a:solidFill xmlns:a="{A}">{_clr(color, alpha)}</a:solidFill>'))
    if spc is not None:
        tracking(r, spc)
    return r


def text(slide, x, y, w, h, s, size, t: Theme, color=None, alpha=1.0, bold=False, font=None, align=PP_ALIGN.LEFT,
         spc=None, anchor=MSO_ANCHOR.TOP, line_spacing=1.12, name=None):
    tb = _tb(slide, x, y, w, h, name)
    tb.text_frame.vertical_anchor = anchor
    first = True
    for para in s.split("\n"):
        p = tb.text_frame.paragraphs[0] if first else tb.text_frame.add_paragraph()
        first = False
        p.alignment = align
        p.line_spacing = line_spacing
        _run(p, para, size, color or t.ink, font or t.text, bold, alpha, spc, bg=t.bg1)
    return tb


def stage(slide, t: Theme, index: int, total: int, chapter: str | None = None, blobs: bool = True):
    """O palco vivo: fundo radial, manchas de luz que flutuam (laço), grade sutil, barra de progresso que cresce
    entre slides (Morph), contador e capítulos. Chame PRIMEIRO em todo slide (fica atrás de tudo).
    Devolve o Motion do slide (já com os laços do fundo)."""
    m = Motion(slide)
    background(slide, [(0, t.glow, 1), (0.42, t.bg1, 1), (1, t.bg0, 1)], radial="circle")
    if blobs:
        # posições mudam um pouco a cada slide: com Morph, as manchas "andam" na troca de slide também
        k = index % 4
        spots = [(-2.0 + k * .25, -2.6, 7.2, t.glow, .55), (8.6 - k * .2, 0.6, 6.2, t.accent, .30),
                 (3.6 + k * .3, 4.4, 5.6, t.cool, .26)]
        for n, (x, y, d, c, a) in enumerate(spots, 1):
            b = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
            b.name = f"!!blob{n}"
            gradient(b, [(0, c, a), (0.65, c, 0)], radial="circle")
            line(b, None)
            effects(b, soft_edge_pt=40)
            m.drift(b, dx=[.07, -.06, -.08][n - 1], dy=[.06, .08, -.05][n - 1], dur=[26000, 31000, 36000][n - 1])
    # grade sutil (64 px no site ≈ 0,67 pol.)
    g = slide.shapes.add_group_shape()
    g.name = "!!grid"
    for i in range(1, 20):
        ln = g.shapes.add_connector(1, Inches(i * .667), Inches(0), Inches(i * .667), Inches(7.5))
        ln.line.width = Pt(.5)
        lnx = ln._element.spPr.find(qn("a:ln"))
        lnx.insert(0, etree.fromstring(f'<a:solidFill xmlns:a="{A}">{_clr(t.ink, .035)}</a:solidFill>'))
    for j in range(1, 12):
        ln = g.shapes.add_connector(1, Inches(0), Inches(j * .667), Inches(13.333), Inches(j * .667))
        ln.line.width = Pt(.5)
        lnx = ln._element.spPr.find(qn("a:ln"))
        lnx.insert(0, etree.fromstring(f'<a:solidFill xmlns:a="{A}">{_clr(t.ink, .035)}</a:solidFill>'))
    # barra de progresso (Morph faz ela crescer de um slide para o outro)
    track = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(7.47), Inches(13.333), Inches(.03))
    track.name = "!!track"
    fill(track, t.ink, .08)
    line(track, None)
    w = max(.05, 13.333 * (index + 1) / total)
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(7.47), Inches(w), Inches(.03))
    bar.name = "!!progress"
    gradient(bar, [(0, t.cool, 1), (1, t.accent, 1)], angle=0)
    line(bar, None)
    effects(bar, glow=(t.accent, .6, 6))
    ctr = text(slide, 11.95, 7.0, 1.2, .3, f"{index + 1:02d} / {total:02d}", 10, t, alpha=.55, bold=True,
               font=t.display, spc=1, name="!!counter")
    ctr.text_frame.word_wrap = False
    if t.chapters:
        x = 6.667 - .62 * len(t.chapters)
        pill_bg = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x - .06), Inches(.28),
                                         Inches(1.24 * len(t.chapters) + .12), Inches(.42))
        pill_bg.name = "!!chapters"
        corner(pill_bg, .5)
        fill(pill_bg, t.ink, .05)
        line(pill_bg, t.ink, .14, .75)
        for n, ch in enumerate(t.chapters):
            if ch == chapter:
                on = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x + n * 1.24), Inches(.32),
                                            Inches(1.2), Inches(.34))
                on.name = "!!chapter-on"
                corner(on, .5)
                gradient(on, [(0, t.accent, 1), (1, t.accent2, 1)], angle=0)
                line(on, None)
                effects(on, shadow=(t.accent, .5, 10, 3))
            text(slide, x + n * 1.24, .32, 1.2, .34, ch, 9.5, t, alpha=1 if ch == chapter else .55, bold=True,
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    return m


def eyebrow(slide, t: Theme, x, y, s, m: Motion, i=0):
    """Rótulo em caixa alta com um traço antes (abre todo slide)."""
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y + .1), Inches(.42), Inches(.025))
    gradient(bar, [(0, t.accent, 1), (1, t.accent, 0)], angle=0)
    line(bar, None)
    tb = text(slide, x + .55, y, 8, .3, s.upper(), 10.5, t, color=t.accent2, bold=True, spc=2.6)
    m.wipe(bar, at(i), dur=700)
    m.rise(tb, at(i))
    return tb


def title(slide, t: Theme, x, y, w, lines: list[str], size: float, m: Motion, i=1, emphasis: str | None = None,
          line_gap: float = 0.98):
    """Título em linhas separadas (cada uma sobe de dentro de uma máscara). `emphasis` = palavra/trecho que ganha
    o degradê quente (no máximo um por slide)."""
    h = size / 72 * line_gap * 1.08
    shapes = []
    for ln_txt in lines:                       # cada linha precisa caber inteira: título que quebra sobrepõe o resto
        need = est_width(ln_txt, size)
        if need > w:
            raise ValueError(f"linha de título não cabe: {ln_txt!r} precisa de ~{need:.1f} pol. e tem {w:.1f}. "
                             f"Reduza o tamanho, encurte ou quebre em mais linhas.")
    for n, ln_txt in enumerate(lines):
        tb = _tb(slide, x, y + n * h, w, h * 1.15)
        p = tb.text_frame.paragraphs[0]
        p.line_spacing = 0.9
        parts = ln_txt.split(emphasis) if emphasis and emphasis in ln_txt else [ln_txt]
        for k, part in enumerate(parts):
            if part:
                _run(p, part, size, t.ink, t.display, bold=True, spc=-size * .035)
            if k < len(parts) - 1:
                r = _run(p, emphasis, size, t.accent, t.display, bold=True, spc=-size * .035)
                text_gradient(r, [(0, t.accent2, 1), (.55, t.accent, 1), (1, t.accent, 1)], angle=0)
        m.line(tb, at(i + n, step=LINE_STEP))
        shapes.append(tb)
    return shapes, y + len(lines) * h


def est_width(s: str, size_pt: float, factor: float = 0.55) -> float:
    """Largura aproximada (pol.) de um texto em fonte de título pesada. Conservador de propósito."""
    return len(s) * size_pt * factor / 72


def lead(slide, t: Theme, x, y, w, s, m: Motion, i, size=17, h=1.2):
    tb = text(slide, x, y, w, h, s, size, t, alpha=.80, line_spacing=1.35)
    m.rise(tb, at(i))
    return tb


def glass(slide, t: Theme, x, y, w, h, radius=.22, name=None):
    """Cartão de vidro: branco quase transparente em degradê + contorno fino + sombra funda."""
    c = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        c.name = name
    corner(c, radius / min(w, h))   # radius em polegadas (0,22" ≈ os 20 px do site)
    gradient(c, [(0, t.ink, .09), (1, t.ink, .03)], angle=70)
    line(c, t.ink, .14, .75)
    effects(c, shadow=("000000", .35, 24, 10))
    return c


def icon_tile(slide, t: Theme, x, y, glyph: str, size=.62):
    """Quadrado arredondado em degradê quente com um símbolo (use um caractere simples: ✓ ★ ⚡ ◆ ▲ ● ✦ ⟶)."""
    tile = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(size), Inches(size))
    corner(tile, .28)
    gradient(tile, [(0, t.accent, 1), (1, t.accent2, 1)], angle=45)
    line(tile, None)
    effects(tile, shadow=(t.accent, .55, 14, 5))
    tf = tile.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    _run(p, glyph, size * 30, t.ink, t.text, bold=True)
    return tile


def numeral(slide, t: Theme, x, y, w, h, s, size, alpha=.22, align=PP_ALIGN.RIGHT):
    """Número/sigla gigante só com contorno (divisores de capítulo, "01" dos passos)."""
    tb = _tb(slide, x, y, w, h)
    tb.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    tb.text_frame.word_wrap = False                 # numeral nunca quebra linha
    p = tb.text_frame.paragraphs[0]
    p.alignment = align
    r = _run(p, s, size, t.ink, t.display, bold=True, spc=-size * .06)
    text_outline(r, t.ink, alpha, max(1.0, size / 160))
    return tb


def device(slide, t: Theme, image_path, x, y, w, caption="", m: Motion | None = None, i=2):
    """Moldura de navegador com a imagem, brilho atrás e entrada em zoom. Devolve (grupo, caixa da imagem em pol.)."""
    from PIL import Image
    iw, ih = Image.open(image_path).size
    ih_in = w * ih / iw
    chrome_h = .3
    halo = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + w * .06), Inches(y + .3), Inches(w * .88), Inches(ih_in))
    gradient(halo, [(0, t.accent, .45), (.55, t.cool, .25), (1, t.cool, 0)], radial="circle")
    line(halo, None)
    effects(halo, soft_edge_pt=36)
    g = slide.shapes.add_group_shape()
    frame = g.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(ih_in + chrome_h))
    corner(frame, .035)
    gradient(frame, [(0, t.bg1, 1), (1, t.bg0, 1)], angle=90)
    line(frame, t.ink, .16, .75)
    effects(frame, shadow=("000000", .55, 40, 18))
    for n, c in enumerate(("FF6159", "FFBD2E", "28C940")):
        d = g.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + .16 + n * .17), Inches(y + .1), Inches(.1), Inches(.1))
        fill(d, c)
        line(d, None)
    if caption:
        cap = g.shapes.add_textbox(Inches(x + .8), Inches(y + .04), Inches(w - 1.6), Inches(.22))
        cap.text_frame.margin_top = cap.text_frame.margin_bottom = 0
        p = cap.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        _run(p, caption, 8.5, t.ink, t.text, alpha=.55, bg=t.bg1)
    pic = g.shapes.add_picture(str(image_path), Inches(x), Inches(y + chrome_h), Inches(w), Inches(ih_in))
    g.name = "screen"
    if m:
        m.fade(halo, at(i) + 200, dur=1400)
        m.zoom(g, at(i))
    return g, (x, y + chrome_h, w, ih_in), pic


def hotspot(slide, t: Theme, cx, cy, n: int, label: str, m: Motion, delay: int, side="r"):
    """Marcador numerado sobre a imagem: surge com mola, anel pulsando para sempre e etiqueta ao lado."""
    d = .3
    ring = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - d / 2 - .04), Inches(cy - d / 2 - .04),
                                  Inches(d + .08), Inches(d + .08))
    no_fill(ring)
    line(ring, t.accent, .9, 1.5)
    dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - d / 2), Inches(cy - d / 2), Inches(d), Inches(d))
    fill(dot, t.accent)
    line(dot, "FFFFFF", .9, 2)
    effects(dot, shadow=("000000", .5, 10, 4))
    tf = dot.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    _run(p, str(n), 10, "FFFFFF", t.text, bold=True)
    lw = .3 + len(label) * .085
    lx = cx + .3 if side == "r" else cx - .3 - lw
    tag = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(lx), Inches(cy - .17), Inches(lw), Inches(.34))
    corner(tag, .3)
    fill(tag, t.bg0, .94)
    line(tag, t.ink, .18, .75)
    effects(tag, shadow=("000000", .45, 14, 5))
    tf = tag.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = Inches(.06)
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    _run(p, label, 10, t.ink, t.text, bold=True)
    m.pop(dot, delay)
    m.fade(ring, delay + 300, dur=400)
    m.breathe(ring, by=1.35, dur=1200, delay=delay + 700)
    m.rise(tag, delay + 200, dur=600, dist=.01)
    return dot


def curtain(slide, t: Theme, m: Motion, delay=0):
    """Cortina de capítulo: faixa diagonal na cor quente que atravessa a tela ao abrir o divisor.
    Começa FORA do slide (à esquerda): em PDF, miniatura ou programa sem animação, não cobre nada."""
    w = 13.333 * 1.1
    c = slide.shapes.add_shape(MSO_SHAPE.PARALLELOGRAM, Inches(-w - .2), Inches(-.2), Inches(w), Inches(7.9))
    c.adjustments[0] = .18
    gradient(c, [(0, t.accent, 1), (.9, t.accent, 1), (.93, t.accent2, 1), (.96, t.bg1, 1), (1, t.bg1, 1)], angle=0)
    line(c, None)
    c.name = "curtain"
    m.sweep(c, delay, dur=950, across=(w * 2 + .4) / 13.333)
    return c


def notes(slide, s: str):
    slide.notes_slide.notes_text_frame.text = s
```
