"""Lista oficial de lojas da empresa: leitura da planilha colada, carga, vínculo das lojas antigas e permissões."""
from app.models import AuditLog, ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store
from app.services import company_stores
from tests.test_app_flow import _make_store
from tests.test_director import _user
from tests.test_roles import _seed_bill

LIST = "\n".join([
    "MULTICOM ATACADO E VAREJO - ECONOMART (MINAS GERAIS)\t\t\t\t\t\t\t\t",
    "MULTICOM\t6\t72620\tContagem\t28.548.486/0001-16\t003.034.575-0080\t72090583\t32.210-110\tAv General David Sarnoff, 3113 - Bairro Cidade Industrial / Contagem",
    "MULTICOM\t24\t189018\tContagem Colonial 28.548.486/0022-40\t003.034.575-1493\t72196218\t32.044-200\tRua Palmeiras, 2135 - Colonial - Contagem/MG",
    "MULTICOM\t32\t246466\tItuiutaba\t28.548.486/0035-65\t003.034.575-1981\t\t38.300-102\tAv. Jos João Dib, 3130, Centro - Ituiutaba/MG",
    " MULTICOM ATACADO E VAREJO - ECONOMART (BAHIA)\t\t\t\t\t\t\t\t",
    "MULTICOM\t22\t192894\tFeira de Santana\t28.548.486/0024-02\t217.398.226\t92.703-1\t44082-150\tRua Passo Alegre, Lagoa Salagada - Feira de Santana/BA",
    "MULTICOM ATACADO E VAREJO (CD, COMERCIAL E ETC)\t\t\t\t\t\t\t\t",
    "MULTICOM\t200\t119084\tPernambuco\t28.548.486/0008-92\t0975471-74\t31773-0\t55.590-000\tRod PE 060 - S/N - Suape Ipojuca/ PE",
    "MULTICOM\t300\t148175\tCD Rib.Neves\t28.548.486/0017-83\t003.034.575-1230\t120239095\t33.822-722\tAv. Jose Carlos Costa, 916 - Liberdade - Rib.Neves/MG",
    "MULTICOM\t501\t154738\tADM - Salvador\t28.548.486/0018-64\t-\t880.267/001-17\t41.820-774\tRua Frederico Simões, 125 - Salvador/BA",
    "REDE DROGAMART\t\t\t\t\t\t\t\t",
    "DROGAMART\t246774\t246774\tMatriz\t68.380.795/0001-44\t005.609.679-0011\t\t30494-270\tAv. Barão Homem de Melo, 4490 - Estoril - Belo Horizonte - MG",
])


def test_parse_reads_every_column_and_the_uf_from_the_cep():
    p = company_stores.parse(LIST)
    assert not p.errors and [r.code for r in p.rows] == ["6", "24", "32", "22", "200", "300", "501", "DROGAMART"]
    r = {r.code: r for r in p.rows}
    assert r["24"].name == "Contagem Colonial" and r["24"].cnpj == "28.548.486/0022-40"     # nome e CNPJ sem TAB entre eles
    assert r["6"].c5 == "72620" and r["6"].state_reg == "003.034.575-0080" and r["6"].municipal_reg == "72090583"
    assert r["6"].cep == "32.210-110" and r["6"].address.startswith("Av General David Sarnoff")
    assert r["32"].municipal_reg == "" and r["32"].cep == "38.300-102"                         # coluna vazia não desloca as outras
    assert r["501"].state_reg == ""                                                             # "-" = vazio
    assert {k: v.uf for k, v in r.items()} == {"6": "MG", "24": "MG", "32": "MG", "22": "BA", "200": "PE", "300": "MG",
                                                "501": "BA", "DROGAMART": "MG"}
    assert r["22"].group.endswith("(BAHIA)") and r["DROGAMART"].name == "Matriz" and r["DROGAMART"].c5 == "246774"


def test_parse_also_works_when_tabs_became_spaces():
    p = company_stores.parse(LIST.replace("\t", " "))
    assert not p.errors and len(p.rows) == 8
    assert {r.code: (r.name, r.uf) for r in p.rows}["24"] == ("Contagem Colonial", "MG")


def test_parse_flags_bad_lines():
    p = company_stores.parse("MULTICOM\tXX\t1\tLoja\t28.548.486/0001-16\n"
                             "MULTICOM\t6\t1\tA\t28.548.486/0001-16\nMULTICOM\t6\t2\tB\t28.548.486/0002-16")
    assert [e.error for e in p.errors][0].startswith("Número da filial") and "repetido" in p.errors[1].error
    assert [r.code for r in p.rows] == ["6"]


def test_admin_previews_then_loads_the_list(client, db):
    page = client.post("/admin/lojas/conferir", {"text": LIST})
    assert page.status_code == 200 and "Conferência: 8 loja(s)" in page.text and "Contagem Colonial" in page.text
    assert db.query(Store).count() == 0                                                          # conferir não grava
    r = client.post("/admin/lojas/carregar", {"text": LIST})
    assert r.status_code == 303
    s = db.query(Store).filter_by(code="24").one()
    assert s.official and s.name == "Contagem Colonial" and s.region == "MG" and s.cnpj == "28.548.486/0022-40"
    assert s.details["cep"] == "32.044-200" and s.group_name.endswith("(MINAS GERAIS)")
    assert db.query(AuditLog).filter_by(action="import", entity="company_stores").count() == 1
    client.post("/admin/lojas/carregar", {"text": LIST})                                         # carregar de novo não duplica
    assert db.query(Store).count() == 8


def test_store_lists_are_in_numeric_order(client, db):
    client.post("/admin/lojas/carregar", {"text": LIST})
    html = client.get("/points/new").text
    assert html.index("6 — Contagem") < html.index("24 — Contagem Colonial") < html.index("200 — Pernambuco")


def test_old_store_shows_up_to_be_linked_and_links_with_everything(client, db):
    old_id = _make_store(client, code="CD300")                                                   # criada antes da lista
    _seed_bill(client, db, old_id)
    assert "Vincule" not in client.get("/").text                                                 # sem lista ainda: sem aviso
    client.post("/admin/lojas/carregar", {"text": LIST})
    assert "1 loja(s) criada(s) antes da lista oficial" in client.get("/").text
    page = client.get("/stores").text
    assert "Vincule 1 loja(s) criada(s) antes da lista" in page                                   # na própria tela Lojas
    official = db.query(Store).filter_by(code="300").one()
    assert f'<option value="{official.id}" selected>' in page                                    # sugestão: CD300 -> 300
    confirm = client.get(f"/admin/lojas/vincular?legacy={old_id}&official={official.id}")
    assert confirm.status_code == 200 and "1</strong> ponto(s) de energia e <strong>1</strong> conta(s)" in confirm.text
    r = client.post("/admin/lojas/vincular", {"legacy_id": old_id, "official_id": official.id})
    assert r.status_code == 303
    db.expire_all()
    assert db.get(Store, old_id) is None
    unit = db.query(ConsumerUnit).one()
    assert unit.store_id == official.id and db.query(EnergyBill).one().unit_id == unit.id
    assert "CD300" in official.aliases and "CD Ribeirão" in official.aliases
    assert db.query(AuditLog).filter_by(action="link", entity="store").count() == 1
    assert "criada(s) antes da lista oficial" not in client.get("/").text


def test_linking_moves_manual_records_too(client, db):
    old_id = _make_store(client, code="L24", unit=None)
    t = db.query(RecordType).filter_by(code="ll-energia").one()
    assert client.post("/manual/lote", {"store_ids": [str(old_id)], "type_id": t.id, "reference": "2026-08", "value": "10"}).status_code == 303
    client.post("/admin/lojas/carregar", {"text": LIST})
    official = db.query(Store).filter_by(code="24").one()
    client.post("/admin/lojas/vincular", {"legacy_id": old_id, "official_id": official.id})
    db.expire_all()
    assert db.query(ManualRecord).one().store_id == official.id


def test_cannot_link_into_a_non_official_or_the_same_store(client, db):
    a = _make_store(client, code="A1", unit=None)
    b = _make_store(client, code="B1", unit=None)
    client.post("/admin/lojas/carregar", {"text": LIST})
    client.post("/admin/lojas/vincular", {"legacy_id": a, "official_id": b})
    official = db.query(Store).filter_by(code="6").one()
    client.post("/admin/lojas/vincular", {"legacy_id": official.id, "official_id": official.id})
    db.expire_all()
    assert db.get(Store, a) and db.get(Store, b) and db.query(Store).count() == 10


def test_only_admin_manages_the_list_and_employee_picks_from_it(client, db):
    func = _user(client, "func9", "operator")
    assert func.get("/admin/lojas").status_code == 403
    assert func.post("/admin/lojas/carregar", {"text": LIST}).status_code == 403
    assert func.post("/stores", {"code": "X1"}).status_code == 303                               # sem lista: funcionário ainda cria
    client.post("/admin/lojas/carregar", {"text": LIST})
    r = func.post("/stores", {"code": "X2", "name": "Nova"})
    assert r.status_code == 303 and r.headers["location"] == "/stores" and not db.query(Store).filter_by(code="X2").first()
    assert 'href="/stores/new"' not in func.get("/stores").text
    assert client.post("/stores", {"code": "999", "name": "Loja nova"}).status_code == 303       # admin inclui
    assert db.query(Store).filter_by(code="999").one().official


def test_panel_ignores_stores_without_bills(client, db):
    client.post("/admin/lojas/carregar", {"text": LIST})
    html = client.get("/diretoria").text
    assert "Contagem Colonial" not in html


def test_company_without_branch_number_uses_the_company_as_code():
    """A Drogamart não tem número de filial: a coluna vem vazia ou repete o código C5."""
    for line in ("DROGAMART\t\t246774\tMatriz\t68.380.795/0001-44\t005.609.679-0011\t\t30494-270\tAv. Barão - MG",
                 "DROGAMART\t246774\t246774\tMatriz\t68.380.795/0001-44\t005.609.679-0011\t\t30494-270\tAv. Barão - MG"):
        (row,) = company_stores.parse(line).rows
        assert (row.code, row.c5, row.name, row.uf) == ("DROGAMART", "246774", "Matriz", "MG")


def test_reloading_fixes_a_code_by_the_cnpj(client, db):
    """Lista carregada antes com a Drogamart como 246774: carregar de novo troca o código, sem criar outra loja."""
    old = LIST.replace("DROGAMART\t246774\t246774", "DROGAMART\t246774\t1")
    client.post("/admin/lojas/carregar", {"text": old})
    assert db.query(Store).filter_by(code="246774").one().official
    preview = client.post("/admin/lojas/conferir", {"text": LIST}).text
    assert "código muda de 246774 para DROGAMART" in preview
    client.post("/admin/lojas/carregar", {"text": LIST})
    db.expire_all()
    s = db.query(Store).filter_by(cnpj="68.380.795/0001-44").one()
    assert s.code == "DROGAMART" and "246774" in s.aliases and db.query(Store).count() == 8


def test_one_stores_screen_no_separate_menu(client, db):
    """Boas práticas: uma tela só de Lojas. Importar a lista é um botão nela; não há item de menu separado."""
    html = client.get("/stores").text
    assert 'href="/admin/lojas"' in html and "Importar lista de lojas" in html and "Lojas da empresa" not in html
    func = _user(client, "func10", "operator")
    assert "Importar lista de lojas" not in func.get("/stores").text
    r = client.post("/admin/lojas/carregar", {"text": LIST})
    assert r.headers["location"] == "/stores"
    assert "Atualizar lista de lojas" in client.get("/stores").text
