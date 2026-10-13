"""Telas baixas (notebook 1366x768 ≈ 600 px úteis) e celular: regressões encontradas em produção em 11/10/2026."""
import re

CSS = open("app/static/css/app.css", encoding="utf-8").read()


def test_menu_footer_stays_visible_on_short_screens():
    """Botão Apresentação, usuário e Sair ficam colados no rodapé do menu (sem rolar) e o menu fica mais compacto."""
    assert re.search(r"\.side-foot \{ position: sticky; bottom: 0;", CSS)
    assert "@media (max-height: 820px) and (min-width: 801px)" in CSS


def test_login_chart_only_hides_on_really_short_windows():
    """O gráfico da tela de entrada encolhe em janelas baixas; antes sumia abaixo de 700 px (todo notebook 1366x768)."""
    assert "@media (max-height: 700px) and (min-width: 861px) { .auth-glass { display: none; } }" not in CSS
    assert "@media (max-height: 500px) and (min-width: 861px) { .auth-glass { display: none; } }" in CSS


def test_tablewrap_contains_visually_hidden_text():
    """.sr é position:absolute: sem position:relative no wrapper ele escapava do recorte e criava rolagem lateral no celular."""
    assert ".tablewrap { overflow-x: auto; position: relative; }" in CSS


def test_wide_tables_fit_the_laptop_without_side_scroll():
    """O funcionário reclamou de ter que arrastar a tabela de Contas para o lado (notebook 1366x768)."""
    assert ".actcell { white-space: normal;" in CSS                                          # botões de ação quebram em 2 linhas
    assert "@media (max-width: 1320px) { .hide-md { display: none; } }" in CSS               # colunas secundárias somem em tela estreita
    assert "table.dense th, table.dense td" in CSS and "table.heat td, table.heat th { padding: 5px 3px" in CSS
    unit = open("app/templates/units/detail.html", encoding="utf-8").read()
    assert 'class="right actcell' in unit and 'class="num hide-md" data-label="Dias">' in unit
    assert 'table class="dense"' in open("app/templates/stores/history.html", encoding="utf-8").read()
    assert 'class="right actcell"' in open("app/templates/bills/list.html", encoding="utf-8").read()


def test_bills_list_turns_into_cards_on_the_phone(client):
    """No celular a lista de Contas era uma tabela larga (botões fora da tela); agora cada conta vira um cartão."""
    assert "@media (max-width: 800px) {\n  table.cards, table.cards tbody { display: block;" in CSS
    assert 'grid-template-areas: "store val" "unit unit" "due orig" "act act"' in CSS
    html = client.get("/notas").text
    assert '<table class="cards">' in html


def test_card_stack_class_does_not_break_stacked_tables():
    """`.stack` (coluna de cartões do painel) virava display:grid também em table.stack (Usuários, Auditoria):
    o cabeçalho ficava desalinhado das linhas no computador."""
    assert re.search(r"^\.stack \{ display: grid", CSS, re.M) is None
    assert "div.stack { display: grid" in CSS


def test_lists_turn_into_cards_on_the_phone():
    """Auditoria de UX 13/10: listas comuns viram cartões no celular (table.stack + data-label), sem rolar para o lado."""
    for path, label in (("app/templates/dashboard.html", 'data-label="Situação"'),
                        ("app/templates/stores/settings.html", 'data-label="Distribuidora"'),
                        ("app/templates/stores/history.html", 'data-label="Vencimento"'),
                        ("app/templates/units/detail.html", 'data-label="Consumo (kWh)"'),
                        ("app/templates/admin/panel.html", 'data-label="Última atividade"')):
        html = open(path, encoding="utf-8").read()
        assert 'table class="stack"' in html and label in html, path
