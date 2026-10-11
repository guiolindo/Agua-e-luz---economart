"""Variantes difíceis das contas fictícias (foto girada, escura e borrada, baixa resolução, PDF de 2 páginas). Rode depois de shots.js."""
import os
import random

from PIL import Image, ImageEnhance, ImageFilter

G = os.environ.get("GEM_DIR", "/tmp/gemini_battery") + "/"
random.seed(3)
a = Image.open(G + "cemig.png").convert("RGB")
a.rotate(90, expand=True).save(G + "v_cemig_rot90.jpg", quality=85)
b = a.resize((a.width // 2, a.height // 2)).rotate(4, expand=True, fillcolor=(120, 120, 120))
b = ImageEnhance.Brightness(b).enhance(.45).filter(ImageFilter.GaussianBlur(1.6))
px = b.load()
for _ in range(60000):
    x, y = random.randrange(b.width), random.randrange(b.height)
    v = random.randint(-25, 25)
    r, g, bl = px[x, y]
    px[x, y] = tuple(max(0, min(255, c + v)) for c in (r, g, bl))
b.save(G + "v_cemig_escuro_borrado.jpg", quality=35)
c = Image.open(G + "energisa.png").convert("RGB")
c.resize((520, round(c.height * 520 / c.width))).save(G + "v_energisa_baixa_res.jpg", quality=30)
Image.open(G + "coelba.png").convert("RGB").save(G + "v_coelba_2paginas.pdf", save_all=True, append_images=[Image.open(G + "nb_boleto.png").convert("RGB")], resolution=110)
