"""Roda a bateria no Gemini real: GEMINI_API_KEY=... python scripts/gemini_battery/run.py (veja README.md)."""
import os, sys, json, time, mimetypes, concurrent.futures as cf
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.environ.setdefault("DEBUG", "true")
from app.services.gemini_service import GeminiService
G = os.environ.get("GEM_DIR", "/tmp/gemini_battery") + "/"
truth = json.load(open(G + "truth.json"))
svc = GeminiService(api_key=os.environ["GEMINI_API_KEY"])
cases = [("cemig.png", "cemig"), ("coelba.png", "coelba"), ("energisa.png", "energisa"), ("cemiggt.png", "cemiggt"), ("coelba.pdf", "coelba"),
         ("v_cemig_rot90.jpg", "cemig"), ("v_cemig_escuro_borrado.jpg", "cemig"), ("v_energisa_baixa_res.jpg", "energisa"), ("v_coelba_2paginas.pdf", "coelba"),
         ("nb_cardapio.png", None), ("nb_agua.png", None), ("nb_boleto.png", None), ("nb_contrato.png", None), ("nb_branco.png", None), ("nb_selfie.png", None), ("nb_paisagem.png", None)]
def norm(v): return None if v is None else (str(v).replace(".", "").replace("-", "").replace("/", "") if isinstance(v, str) else float(v))
def run(c):
    f, k = c
    data = open(G + f, "rb").read(); mime = mimetypes.guess_type(f)[0]
    t0 = time.time()
    try:
        r = svc.extract(data, mime)
    except Exception as e:
        return f, k, None, f"{type(e).__name__}: {str(e)[:140]}", time.time() - t0
    return f, k, r, None, time.time() - t0
out = []
with cf.ThreadPoolExecutor(2) as ex:
    for f, k, r, err, dt in ex.map(run, cases):
        if err: print(f"{f:32s} ERRO {err} ({dt:.1f}s)"); out.append((f, False)); continue
        if k is None:
            ok = r.is_energy_bill is False and all(getattr(r, x) is None for x in ("total_value", "consumer_unit_number", "due_date"))
            print(f"{f:32s} {'OK ' if ok else 'FALHA'} não-conta: is_energy_bill={r.is_energy_bill} motivo={r.not_bill_reason!r} total={r.total_value} uc={r.consumer_unit_number} ({dt:.1f}s)"); out.append((f, ok)); continue
        exp = truth[k]; bad = []
        for fld, ev in exp.items():
            gv = getattr(r, fld, None)
            if fld == "utility": 
                if gv is None or ev.lower().split()[0] not in gv.lower(): bad.append((fld, ev, gv))
            elif isinstance(ev, bool) or isinstance(ev, str):
                if norm(gv) != norm(ev): bad.append((fld, ev, gv))
            else:
                if gv is None or abs(float(gv) - float(ev)) > 0.01: bad.append((fld, ev, gv))
        # campos que NÃO existem na conta devem vir null (zero chute)
        extra = [x for x in ("consumption_hp_kwh", "demand_hp_kw") if k == "energisa" and getattr(r, x) not in (None, 0)]
        ok = not bad and not extra
        print(f"{f:32s} {'OK ' if ok else 'FALHA'} {len(exp)-len(bad)}/{len(exp)} campos ({dt:.1f}s)" + (f"  divergências={bad}" if bad else "") + (f" inventou={extra}" if extra else "")); out.append((f, ok))
print("RESULTADO", sum(o for _, o in out), "/", len(out))
