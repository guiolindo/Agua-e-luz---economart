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

// ---------------------------------------------------------------- vencimentos: aviso lateral (15 s), sino e ponto de energia rápido
(function () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (!meta) return;
  const csrf = meta.content, TOAST_MS = 15000;
  const $ = (id) => document.getElementById(id);
  if (!$('bell')) return;   // primeiro acesso (troca de senha): sem sino, sem avisos
  const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  const dateBR = (iso) => iso.split('-').reverse().join('/');
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let state = { items: [], can_ack: false, today: '' };

  function line(i) {
    return '<strong>' + esc(i.store) + '</strong> · <span class="mono">' + esc(i.number) + '</span>' + (i.supplier ? ' · ' + esc(i.supplier) : '') +
      (i.description ? '<div class="muted small">' + esc(i.description) + '</div>' : '') +
      '<div class="small">' + dateBR(i.due) + (i.value != null ? ' · ' + money.format(i.value) : ' · conta ainda não lançada') + '</div>';
  }
  async function ack(i) {
    const r = await fetch('/api/due/' + i.unit_id + '/ack', { method: 'POST', headers: { 'X-CSRF-Token': csrf, Accept: 'application/json' } });
    if (r.ok) await refresh();
  }
  function actions(i) {
    const a = document.createElement('div'); a.className = 'dactions';
    const view = document.createElement('a'); view.className = 'btn sm'; view.textContent = 'Ver ponto'; view.href = '/units/' + i.unit_id; a.appendChild(view);
    if (state.can_ack && i.status !== 'soon') {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'btn sm primary'; b.textContent = 'Já paguei';
      b.addEventListener('click', () => ack(i)); a.appendChild(b);
    }
    return a;
  }
  function toast(i) {
    const el = document.createElement('div');
    el.className = 'toast ' + i.status; el.setAttribute('role', i.status === 'today' ? 'alert' : 'status');
    el.innerHTML = '<div class="thead"><span class="tlabel">' + esc(i.label) + '</span><button type="button" class="tclose" aria-label="Fechar aviso">×</button></div><div class="tbody">' + line(i) + '</div><div class="tbar"><i></i></div>';
    el.querySelector('.tbody').appendChild(actions(i));
    const bar = el.querySelector('.tbar i'); bar.style.animationDuration = TOAST_MS + 'ms';
    let left = TOAST_MS, started = Date.now(), timer;
    const close = () => { clearTimeout(timer); el.classList.add('out'); setTimeout(() => el.remove(), 250); };
    const run = () => { started = Date.now(); bar.style.animationPlayState = 'running'; timer = setTimeout(close, left); };
    const pause = () => { clearTimeout(timer); left -= Date.now() - started; bar.style.animationPlayState = 'paused'; };
    el.addEventListener('mouseenter', pause); el.addEventListener('mouseleave', run);
    el.addEventListener('focusin', pause); el.addEventListener('focusout', run);   // quem navega por teclado não perde o aviso
    el.querySelector('.tclose').addEventListener('click', close);
    $('toasts').appendChild(el); run();
  }
  function paintBell() {
    const urgent = state.items.filter((i) => i.status !== 'soon').length, c = $('bell-count');
    c.hidden = urgent === 0; c.textContent = urgent > 9 ? '9+' : urgent;
    $('bell').setAttribute('aria-label', urgent ? 'Vencimentos: ' + urgent + ' pendente(s)' : 'Vencimentos');
    const p = $('bell-panel'); p.innerHTML = '<h2>Vencimentos</h2>';
    if (!state.items.length) { p.insertAdjacentHTML('beforeend', '<p class="muted small" style="margin:6px 0 0">Nenhuma conta vencendo nos próximos dias.</p>'); return; }
    state.items.forEach((i) => { const row = document.createElement('div'); row.className = 'brow ' + i.status;
      row.innerHTML = '<div class="tlabel">' + esc(i.label) + '</div>' + line(i); row.appendChild(actions(i)); p.appendChild(row); });
  }
  async function refresh() {
    try { const r = await fetch('/api/due', { headers: { Accept: 'application/json' } }); if (!r.ok) return; state = await r.json(); } catch (e) { return; }
    paintBell(); return state;
  }
  async function init() {
    await refresh();
    const key = (document.body.dataset.login || '') + ':' + state.today;       // 1x por login por dia
    let seen = null; try { seen = sessionStorage.getItem('due-shown'); } catch (e) { /* storage bloqueado */ }
    const pending = state.items.filter((i) => i.status !== 'soon');
    if (seen !== key && pending.length) {
      pending.slice(0, 4).forEach(toast);
      if (pending.length > 4) toast({ status: 'overdue', label: '+ ' + (pending.length - 4) + ' vencimentos', store: 'Veja no sino', number: '', supplier: '', description: '', due: state.today, value: null, unit_id: 0 });
      try { sessionStorage.setItem('due-shown', key); } catch (e) { /* ok */ }
    }
  }
  const bell = $('bell');
  bell.addEventListener('click', () => { const p = $('bell-panel'); p.hidden = !p.hidden; bell.setAttribute('aria-expanded', String(!p.hidden)); });
  document.addEventListener('click', (e) => { if (!e.target.closest('.bellwrap')) { $('bell-panel').hidden = true; bell.setAttribute('aria-expanded', 'false'); } });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { $('bell-panel').hidden = true; bell.setAttribute('aria-expanded', 'false'); } });
  document.addEventListener('submit', (e) => { if (e.target.action && e.target.action.endsWith('/logout')) { try { sessionStorage.removeItem('due-shown'); } catch (x) { /* ok */ } } });

  // ponto de energia de qualquer tela
  const dlg = $('point-dialog');
  document.addEventListener('click', async (e) => {
    if (e.target.closest('[data-close-dialog]') && dlg) { e.preventDefault(); dlg.close(); return; }
    const open = e.target.closest('[data-open-point]');
    if (!open || !dlg) return;
    try {
      const r = await fetch('/points/new?fragment=1&next=' + encodeURIComponent(location.pathname + location.search), { headers: { Accept: 'text/html' } });
      if (!r.ok) throw new Error(r.status);
      $('point-dialog-body').innerHTML = await r.text(); dlg.showModal(); const f = dlg.querySelector('select, input'); if (f) f.focus();
    } catch (err) { location.href = '/points/new'; }
  });
  init();
})();

// ---------------------------------------------------------------- UX geral
// Mensagens de sucesso/informação somem sozinhas; erros e avisos ficam até serem lidos.
document.querySelectorAll('[data-flash="ok"], [data-flash="info"]').forEach((el) => setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 300); }, 9000));
// Botões de envio mostram "Salvando…" e não deixam clicar duas vezes.
document.addEventListener('submit', (e) => {
  const f = e.target; if (e.defaultPrevented || f.dataset.noLoading !== undefined || f.method.toLowerCase() !== 'post') return;
  f.querySelectorAll('button:not([type]), button[type="submit"]').forEach((b) => {
    if (b.form !== f) return; b.dataset.label = b.textContent; setTimeout(() => { b.disabled = true; b.classList.add('loading'); b.textContent = 'Salvando…'; }, 0); });
});
window.addEventListener('pageshow', (e) => { if (e.persisted) document.querySelectorAll('button.loading').forEach((b) => { b.disabled = false; b.classList.remove('loading'); b.textContent = b.dataset.label; }); });
// Busca rápida em listas (data-filter="#alvo tr")
document.addEventListener('input', (e) => {
  const t = e.target; if (!t.matches('[data-filter]')) return;
  const q = t.value.trim().toLowerCase(); let shown = 0;
  document.querySelectorAll(t.dataset.filter).forEach((row) => { const hit = !q || row.textContent.toLowerCase().includes(q); row.hidden = !hit; if (hit) shown++; });
  const out = document.getElementById(t.dataset.count); if (out) out.textContent = shown + ' resultado(s)';
});

// ---------------------------------------------------------------- acessibilidade
(function () {
  // 1) Todo campo precisa de rótulo: associa <label> sem "for" ao controle do mesmo .field; sem rótulo algum, usa o cabeçalho da coluna.
  let n = 0;
  document.querySelectorAll('.field').forEach((f) => {
    const label = f.querySelector('label:not([for])'), ctl = f.querySelector('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea');
    if (!label || !ctl || ctl.labels && ctl.labels.length) return;
    if (!ctl.id) ctl.id = 'auto-' + (++n);
    label.htmlFor = ctl.id;
  });
  document.querySelectorAll('input:not([type=hidden]), select, textarea').forEach((c) => {
    if ((c.labels && c.labels.length) || c.getAttribute('aria-label') || c.getAttribute('aria-labelledby')) return;
    const td = c.closest('td'), th = td && td.closest('table') && td.closest('table').querySelectorAll('thead th')[td.cellIndex];
    c.setAttribute('aria-label', (th && th.textContent.trim()) || c.placeholder || c.name || 'Campo');
  });
  // 2) Áreas roláveis (tabelas largas) precisam ser alcançáveis por teclado.
  const scrollables = () => document.querySelectorAll('.tablewrap').forEach((w) => {
    if (w.scrollWidth > w.clientWidth) { w.tabIndex = 0; w.setAttribute('role', 'region'); const h = w.closest('.card, section') && w.closest('.card, section').querySelector('h2'); w.setAttribute('aria-label', (h ? h.textContent.trim() : 'Tabela') + ' (rolagem horizontal)'); }
  });
  scrollables(); window.addEventListener('resize', scrollables); window.addEventListener('load', scrollables);
})();

// Login: mostrar/ocultar senha e feedback de envio.
document.querySelectorAll('[data-toggle-password]').forEach((b) => b.addEventListener('click', () => {
  const i = document.querySelector(b.dataset.togglePassword); if (!i) return;
  const show = i.type === 'password'; i.type = show ? 'text' : 'password'; b.textContent = show ? 'Ocultar' : 'Mostrar'; b.setAttribute('aria-pressed', String(show)); }));
document.querySelectorAll('[data-login-form]').forEach((f) => f.addEventListener('submit', () => {
  const b = f.querySelector('button[type="submit"]'); if (b) { setTimeout(() => { b.disabled = true; b.classList.add('loading'); b.textContent = 'Entrando…'; }, 0); } }));
