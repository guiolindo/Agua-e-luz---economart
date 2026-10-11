"""Gera contas de energia 100% FICTÍCIAS (CEMIG, Coelba, Energisa, CEMIG G&T) e arquivos que NÃO são conta, com o gabarito em truth.json."""
import json, os
from PIL import Image, ImageDraw, ImageFont
G = os.environ.get("GEM_DIR", "/tmp/gemini_battery") + "/"
os.makedirs(G, exist_ok=True)
truth = {}
def page(title_bar, color, logo, blocks, foot=""):
    return f"""<html><body style="margin:0;font-family:Arial,Helvetica,sans-serif;color:#222"><div style="width:900px;padding:28px 36px;background:#fff">
<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:4px solid {color};padding-bottom:10px"><div style="font-size:34px;font-weight:800;color:{color}">{logo}</div><div style="text-align:right;font-size:13px">{title_bar}</div></div>{{body}}
<div style="font-size:11px;color:#666;margin-top:14px">{foot}</div></div></body></html>"""
def bill_html(kind):
    s = lambda t: f"<div style='background:#eee;padding:4px 8px;font-weight:700;font-size:13px;margin:12px 0 4px'>{t}</div>"
    css = "<style>td{padding:3px 6px;font-size:13px;border-bottom:1px solid #ddd}.r{text-align:right}table{width:100%;border-collapse:collapse}</style>"
    if kind == "cemig":
        truth[kind] = dict(is_energy_bill=True, consumer_unit_number="10.000.000.002-00", reference_month="2026-09", due_date="2026-10-09", issue_date="2026-10-02", total_value=18345.67,
                           consumption_hp_kwh=4210, consumption_hfp_kwh=61870, demand_hp_kw=118, demand_hfp_kw=142, contracted_demand_kw=150, invoice_number="200100300", days=30, utility="CEMIG")
        b = f"""{css}<div style="display:flex;justify-content:space-between;margin-top:10px;font-size:13px"><div><b>COMERCIAL EXEMPLO DOIS LTDA</b><br>AV DAS FLORES 100 - CENTRO<br>BELO HORIZONTE/MG - CEP 30000-000<br>CNPJ 00.000.000/0001-00</div>
<div style="text-align:right">Unidade Consumidora<br><b style="font-size:20px">10.000.000.002-00</b><br>Classe: Comercial · TUSD Livre A4 Verde</div></div>
{s("DADOS DA FATURA")}<table><tr><td>Referência</td><td class=r><b>SET/2026</b></td><td>Vencimento</td><td class=r><b style="font-size:18px">09/10/2026</b></td></tr><tr><td>Emissão</td><td class=r>02/10/2026</td><td>Nota Fiscal / Série</td><td class=r>200100300 / 000</td></tr>
<tr><td>Leitura anterior</td><td class=r>31/08/2026</td><td>Leitura atual</td><td class=r>30/09/2026 (30 dias)</td></tr></table>
{s("ITENS DA FATURA")}<table><tr><td>Energia Elétrica Ponta TUSD</td><td class=r>4.210 kWh</td><td class=r>1.840,20</td></tr><tr><td>Energia Elétrica Fora Ponta TUSD</td><td class=r>61.870 kWh</td><td class=r>8.215,40</td></tr>
<tr><td>Demanda Ponta</td><td class=r>118 kW</td><td class=r>2.100,00</td></tr><tr><td>Demanda Fora Ponta</td><td class=r>142 kW</td><td class=r>3.180,00</td></tr><tr><td>Demanda contratada: 150 kW</td><td></td><td class=r></td></tr><tr><td>PIS/COFINS</td><td></td><td class=r>1.102,33</td></tr><tr><td>ICMS (isento)</td><td></td><td class=r>0,00</td></tr><tr><td>Contrib. Iluminação Pública</td><td></td><td class=r>1.907,74</td></tr></table>
<div style="text-align:right;margin-top:16px;font-size:13px">TOTAL A PAGAR<div style="font-size:30px;font-weight:800">R$ 18.345,67</div></div>"""
        return page("CEMIG DISTRIBUIÇÃO S.A.<br>Nota Fiscal/Conta de Energia Elétrica", "#00529b", "CEMIG", [], "Documento fictício gerado para teste.").replace("{body}", b)
    if kind == "coelba":
        truth[kind] = dict(is_energy_bill=True, consumer_unit_number="7.000.000.003-11", reference_month="2026-08", due_date="2026-09-16", total_value=47912.10,
                           consumption_hp_kwh=9800.5, consumption_hfp_kwh=98400.25, demand_hp_kw=210.5, demand_hfp_kw=255.3, contracted_demand_kw=260, icms_value=8230.44, pis_cofins_value=2405.10, utility="Coelba")
        b = f"""{css}<div style="margin-top:10px;font-size:13px"><b>SUPERMERCADO EXEMPLO TRES S/A</b><br>RUA DO COMERCIO 55, FEIRA DE SANTANA/BA<br></div>
<table style="margin-top:8px"><tr><td>Código da instalação</td><td class=r><b style="font-size:19px">7.000.000.003-11</b></td><td>Mês/Ano</td><td class=r><b>AGO/2026</b></td><td>Vencimento</td><td class=r><b style="font-size:17px">16/09/2026</b></td></tr></table>
{s("GRANDEZAS FATURADAS — A4 LIVRE VERDE")}<table><tr><td>Consumo Ponta (kWh)</td><td class=r>9.800,50</td></tr><tr><td>Consumo Fora Ponta (kWh)</td><td class=r>98.400,25</td></tr><tr><td>Demanda Ponta (kW)</td><td class=r>210,5</td></tr><tr><td>Demanda Fora Ponta (kW)</td><td class=r>255,3</td></tr><tr><td>Demanda Contratada (kW)</td><td class=r>260</td></tr></table>
{s("TRIBUTOS")}<table><tr><td>ICMS</td><td class=r>8.230,44</td></tr><tr><td>PIS</td><td class=r>520,10</td></tr><tr><td>COFINS</td><td class=r>1.885,00</td></tr></table>
<div style="text-align:right;margin-top:16px;font-size:13px">Valor a pagar<div style="font-size:30px;font-weight:800">R$ 47.912,10</div></div>"""
        return page("NEOENERGIA COELBA<br>Fatura de Energia Elétrica", "#e5a900", "coelba", [], "Documento fictício gerado para teste.").replace("{body}", b)
    if kind == "energisa":
        truth[kind] = dict(is_energy_bill=True, consumer_unit_number="100.200.300-04", reference_month="2026-09", due_date="2026-10-11", total_value=412.30, consumption_kwh=288, days=31, utility="Energisa")
        b = f"""{css}<div style="margin-top:10px;font-size:13px"><b>PADARIA EXEMPLO QUATRO ME</b><br>RUA B 10, CATAGUASES/MG</div>
<table style="margin-top:8px"><tr><td>Unidade Consumidora</td><td class=r><b style="font-size:19px">100.200.300-04</b></td><td>Referência</td><td class=r><b>09/2026</b></td><td>Vencimento</td><td class=r><b style="font-size:17px">11/10/2026</b></td></tr></table>
{s("B3 COMERCIAL — CONVENCIONAL BAIXA TENSÃO")}<table><tr><td>Leitura anterior 20/08/2026 · Leitura atual 21/09/2026</td><td class=r>31 dias</td></tr><tr><td>Consumo em kWh</td><td class=r>288</td></tr><tr><td>Consumo faturado</td><td class=r>312,40</td></tr><tr><td>Bandeira tarifária</td><td class=r>29,90</td></tr><tr><td>ICMS</td><td class=r>70,00</td></tr></table>
<div style="text-align:right;margin-top:16px;font-size:13px">TOTAL<div style="font-size:30px;font-weight:800">R$ 412,30</div></div>"""
        return page("ENERGISA MINAS RIO<br>Nota Fiscal de Energia", "#d2232a", "Energisa", [], "Documento fictício gerado para teste.").replace("{body}", b)
    if kind == "cemiggt":
        truth[kind] = dict(is_energy_bill=True, consumer_unit_number="4000000001", reference_month="2026-08", due_date="2026-09-14", total_value=31250.00, consumption_hp_kwh=5000, consumption_hfp_kwh=70000, utility="Cemig Geração e Transmissão")
        b = f"""{css}<div style="margin-top:10px;font-size:13px"><b>COMERCIAL EXEMPLO CINCO LTDA</b><br>Contrato de compra de energia — Mercado Livre</div>
<table style="margin-top:8px"><tr><td>Unidade</td><td class=r><b style="font-size:19px">4000000001</b></td><td>Referência</td><td class=r><b>AGO/2026</b></td><td>Vencimento</td><td class=r><b style="font-size:17px">14/09/2026</b></td></tr></table>
{s("ENERGIA FATURADA")}<table><tr><td>Energia Ponta (kWh)</td><td class=r>5.000</td></tr><tr><td>Energia Fora Ponta (kWh)</td><td class=r>70.000</td></tr><tr><td>Preço médio</td><td class=r>R$ 0,4167/kWh</td></tr></table>
<div style="text-align:right;margin-top:16px;font-size:13px">VALOR DA FATURA<div style="font-size:30px;font-weight:800">R$ 31.250,00</div></div>"""
        return page("CEMIG GERAÇÃO E TRANSMISSÃO S.A.<br>Nota Fiscal de Venda de Energia", "#00529b", "CEMIG GT", [], "Documento fictício gerado para teste.").replace("{body}", b)
for k in ("cemig", "coelba", "energisa", "cemiggt"):
    open(G + f"{k}.html", "w").write(bill_html(k))
json.dump(truth, open(G + "truth.json", "w"), ensure_ascii=False, indent=1)
# não-contas
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans"
f = ImageFont.truetype(F + ".ttf", 26); fb = ImageFont.truetype(F + "-Bold.ttf", 40)
def text_img(name, title, lines, size=(900, 1200)):
    im = Image.new("RGB", size, "white"); d = ImageDraw.Draw(im); d.text((50, 50), title, font=fb, fill="#222")
    y = 140
    for l in lines: d.text((50, y), l, font=f, fill="#333"); y += 46
    im.save(G + name)
text_img("nb_cardapio.png", "CARDÁPIO — Pizzaria Exemplo", ["Margherita ............ R$ 42,00", "Calabresa ............ R$ 45,00", "Portuguesa .......... R$ 48,00", "Refrigerante 2L ..... R$ 12,00", "Taxa de serviço 10%"])
text_img("nb_agua.png", "COPASA — Conta de água e esgoto", ["Cliente: JOSE EXEMPLO", "Matrícula 123456-7", "Referência: SET/2026", "Vencimento: 10/10/2026", "Consumo: 18 m³", "Total a pagar: R$ 96,40"])
text_img("nb_boleto.png", "BOLETO BANCÁRIO", ["Beneficiário: LOJA EXEMPLO LTDA", "Pagador: ECONOMART TESTE", "Vencimento: 15/10/2026", "Valor: R$ 1.250,00", "03399.12345 12345.678901 23456.789012 1 98760000125000"])
text_img("nb_contrato.png", "CONTRATO DE PRESTAÇÃO DE SERVIÇOS", ["Cláusula 1ª — O objeto deste contrato é a", "prestação de serviços de manutenção predial.", "Cláusula 2ª — O prazo é de 12 meses.", "Cláusula 3ª — Valor mensal de R$ 3.000,00."])
Image.new("RGB", (900, 1200), "white").save(G + "nb_branco.png")
# "selfie": rosto desenhado
im = Image.new("RGB", (900, 1200), "#8fb8d8"); d = ImageDraw.Draw(im); d.ellipse([250, 250, 650, 700], fill="#e0b48c"); d.ellipse([340, 400, 390, 450], fill="white"); d.ellipse([510, 400, 560, 450], fill="white"); d.ellipse([355, 415, 375, 435], fill="black"); d.ellipse([525, 415, 545, 435], fill="black"); d.arc([360, 500, 540, 620], 20, 160, fill="#7a2f2f", width=8); d.rectangle([200, 700, 700, 1200], fill="#3a5a8c")
im.save(G + "nb_selfie.png")
# paisagem
im = Image.new("RGB", (900, 1200)); d = ImageDraw.Draw(im)
for y in range(1200): d.line([(0, y), (900, y)], fill=(int(80 + y * .1), int(150 + y * .05), int(230 - y * .12)))
d.polygon([(0, 800), (300, 450), (600, 800)], fill="#456"); d.polygon([(300, 800), (650, 380), (900, 800)], fill="#345"); d.rectangle([0, 800, 900, 1200], fill="#4a8a4a"); d.ellipse([650, 100, 780, 230], fill="#ffe27a")
im.save(G + "nb_paisagem.png")
print("ok", list(truth))
