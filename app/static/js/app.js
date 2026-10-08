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
  if (t.id === 'doc' && t.type === 'checkbox' && t.form && !t.hidden) {   // imprimir conta: incluir o original
    const u = new URL(location.href); if (t.checked) u.searchParams.set('doc', '1'); else u.searchParams.delete('doc');
    u.hash = t.checked ? 'original' : ''; location.href = u.toString(); return;
  }
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
// Busca rápida em listas (data-filter="#alvo tr"). Linhas de grupo (.group-row)
// aparecem apenas quando há pelo menos uma linha filha visível.
document.addEventListener('input', (e) => {
  const t = e.target; if (!t.matches('[data-filter]')) return;
  const q = t.value.trim().toLowerCase(); let shown = 0;
  const rows = Array.from(document.querySelectorAll(t.dataset.filter));
  rows.forEach((row) => {
    if (row.classList.contains('group-row')) return;  // avaliadas depois
    const blob = row.dataset.filterBlob || row.textContent;
    const hit = !q || blob.toLowerCase().includes(q);
    row.hidden = !hit; if (hit) shown++;
  });
  // Esconde cabeçalhos de grupo sem nenhuma linha visível abaixo (até o próximo grupo)
  let cur = null;
  rows.forEach((row) => {
    if (row.classList.contains('group-row')) { cur = row; cur.hidden = true; return; }
    if (cur && !row.hidden) cur.hidden = false;
  });
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

// Barra de progresso no topo quando o usuário clica em um link interno
// (dá sensação de responsividade enquanto a próxima página carrega).
(function () {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const bar = document.createElement('div');
  bar.className = 'nav-progress';
  document.body.appendChild(bar);
  const start = () => { bar.classList.remove('on'); void bar.offsetWidth; bar.classList.add('on'); };
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a'); if (!a || a.target === '_blank' || a.hasAttribute('download')) return;
    const url = new URL(a.href, location.href);
    if (url.origin !== location.origin || url.pathname === location.pathname && url.search === location.search) return;
    start();
  });
  document.addEventListener('submit', (e) => {
    const f = e.target; if (!f || f.method?.toLowerCase() === 'get' && f.hasAttribute('data-autosubmit')) return;
    if (f.target === '_blank') return;
    start();
  });
  window.addEventListener('pagehide', () => bar.classList.remove('on'));
})();

// Delay em cascata para animar os cartões KPI em sequência (efeito "stagger")
(function () {
  // Stagger limitado a 180ms no total pra não deixar as últimas cards aparecerem tarde
  // em telas com muitos KPIs (painel da diretoria tem 8).
  document.querySelectorAll('.grid.cols-4 > .kpi, .grid.cols-3 > .kpi, .grid.cols-2 > .kpi').forEach((el, i) => {
    el.style.setProperty('--d', Math.min(i * 40, 180) + 'ms');
  });
})();

// Ícones automáticos nos alerts/flash: usa SVGs inline por tipo. O markup
// permanece acessível (role="alert"/"status" + texto), o ícone é só visual.
(function () {
  const icons = {
    ok: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    warn: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
  };
  document.querySelectorAll('.flash').forEach((el) => {
    if (el.querySelector('.flash-ico')) return;
    const lvl = el.dataset.flash || (el.classList.contains('error') ? 'error' : el.classList.contains('warn') ? 'warn' : el.classList.contains('info') ? 'info' : 'ok');
    const span = document.createElement('span');
    span.className = 'flash-ico';
    span.style.cssText = 'display:inline-flex;align-items:center;flex-shrink:0';
    span.innerHTML = icons[lvl] || icons.info;
    const body = document.createElement('div');          // o texto (com <strong>, links...) fica numa coluna só
    body.className = 'flash-body';
    while (el.firstChild) body.appendChild(el.firstChild);
    el.append(span, body);
  });
})();

// Drawer mobile: hamburger abre/fecha o menu lateral; backdrop e Esc fecham.
(function () {
  const body = document.body;
  const open = () => { body.classList.add('drawer-open'); document.querySelector('[aria-controls="side"]')?.setAttribute('aria-expanded', 'true'); };
  const close = () => { body.classList.remove('drawer-open'); document.querySelector('[aria-controls="side"]')?.setAttribute('aria-expanded', 'false'); };
  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-drawer-toggle]');
    if (t) { e.preventDefault(); body.classList.contains('drawer-open') ? close() : open(); return; }
    // Clicou num link dentro do drawer -> fecha
    if (body.classList.contains('drawer-open') && e.target.closest('.side a')) close();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
  // Fecha ao redimensionar pra desktop (evita que o drawer-open fique travado)
  matchMedia('(min-width: 801px)').addEventListener?.('change', (ev) => { if (ev.matches) close(); });
})();

// Sino de vencimentos no mobile: espelha o estado do sino desktop (mesmo endpoint, mesmo contador).
(function () {
  const mBell = document.getElementById('bell-m');
  const mCount = document.getElementById('bell-count-m');
  const dCount = document.getElementById('bell-count');
  if (!mBell || !mCount) return;
  const sync = () => {
    if (!dCount) return;
    const hidden = dCount.hidden;
    mCount.hidden = hidden;
    mCount.textContent = dCount.textContent;
  };
  // Observa mudanças no contador desktop (JS existente atualiza aquele)
  if (dCount) new MutationObserver(sync).observe(dCount, { attributes: true, childList: true, characterData: true, subtree: true });
  sync();
  // Clicar no sino mobile dispara o click no sino desktop (abre o mesmo painel)
  mBell.addEventListener('click', () => document.getElementById('bell')?.click());
})();
