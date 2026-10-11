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
    assert 'class="right actcell"' in unit and 'class="num hide-md">Dias' in unit
    assert 'table class="dense"' in open("app/templates/stores/history.html", encoding="utf-8").read()
    assert 'class="right actcell"' in open("app/templates/bills/list.html", encoding="utf-8").read()
