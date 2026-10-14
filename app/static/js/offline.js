// Tela "sem conexão": tenta de novo sozinha quando a internet volta (evento do navegador + checagem a cada 5 s).
(function () {
  const pill = document.getElementById('net-pill'), retry = document.getElementById('retry');
  let busy = false;
  const check = async () => {
    if (busy) return; busy = true;
    try {
      const r = await fetch('/health', { cache: 'no-store' });
      if (r.ok) { pill.textContent = 'Conexão de volta. Abrindo…'; pill.classList.add('ok'); setTimeout(() => location.reload(), 600); return; }
    } catch (e) { /* ainda sem conexão */ }
    busy = false;
  };
  retry.addEventListener('click', () => { pill.textContent = 'Tentando…'; check().then(() => { if (!busy) pill.textContent = 'Aguardando a conexão…'; }); });
  addEventListener('online', check);
  setInterval(check, 5000);
})();
