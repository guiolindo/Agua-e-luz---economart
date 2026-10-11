# Bateria com o Gemini real

Testa a leitura de contas com **documentos fictícios** (nada da empresa vai para o Google; o plano gratuito pode usar o que for enviado para treinamento).

```bash
export GEM_DIR=/tmp/gemini_battery
python scripts/gemini_battery/gen.py          # HTML das contas + arquivos que não são conta + truth.json
node scripts/gemini_battery/shots.js          # HTML -> PNG/PDF (precisa do Playwright e de um Chromium)
python scripts/gemini_battery/variants.py     # foto girada, escura/borrada, baixa resolução, PDF de 2 páginas
GEMINI_API_KEY=... python scripts/gemini_battery/run.py
```

A chave vem só do ambiente: nunca grave em arquivo. No plano gratuito (~15 pedidos/min) uma rodada seguida de outra estoura o limite (429): espere 1 minuto.
Resultado de 11/10/2026 em `CHANGELOG.md`.
