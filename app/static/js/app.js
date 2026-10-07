// Comportamentos globais sem JS inline (compatível com CSP sem 'unsafe-inline' em script).
document.addEventListener('click', (e) => {
  const print = e.target.closest('[data-print]');
  if (print) { e.preventDefault(); window.print(); return; }
  const c = e.target.closest('button[data-confirm], a[data-confirm]');
  if (c && !window.confirm(c.dataset.confirm)) e.preventDefault();
});
document.addEventListener('submit', (e) => {
  const msg = e.target.dataset && e.target.dataset.confirm;
  if (msg && !window.confirm(msg)) e.preventDefault();
});
document.addEventListener('change', (e) => {
  const t = e.target;
  if (t.matches('[data-autosubmit]') && t.form) t.form.submit();
  if (t.matches('select[data-bill-switch]')) {
    const doc = document.getElementById('doc');
    location.href = '/bills/' + t.value + '/print' + (doc && doc.checked ? '?doc=1' : '');
  }
});

// Folha de impressão de uma página: reduz (zoom) só o necessário para caber na altura útil do papel.
function fitSheets() {
  document.querySelectorAll('[data-fit]').forEach((el) => {
    el.style.removeProperty('--fit');
    const h = el.scrollHeight, max = parseFloat(el.dataset.fit);
    el.style.setProperty('--fit', Math.min(1, max / h).toFixed(3));
  });
}
window.addEventListener('load', () => setTimeout(fitSheets, 50));
window.addEventListener('beforeprint', fitSheets);
