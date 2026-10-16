// Comportamentos globais sem JS inline (compatível com CSP sem 'unsafe-inline' em script).
document.addEventListener('click', (e) => {
  const chain = e.target.closest('[data-print-chain]');       // folha da loja e, ao fechar a impressão, a conta original (2º trabalho)
  if (chain) { e.preventDefault(); const next = chain.dataset.next; document.documentElement.classList.add('sheet-only');
    window.addEventListener('afterprint', () => { window.location.href = next; }, { once: true }); window.print(); return; }
  const sheet = e.target.closest('[data-print-sheet]');       // só a folha da loja (a conta original vai em outro trabalho de impressão)
  if (sheet) { e.preventDefault(); document.documentElement.classList.add('sheet-only'); window.print(); return; }
  const back = e.target.closest('[data-back]');                // "Voltar" da página de erro: volta de onde veio (se houver)
  if (back && history.length > 1) { e.preventDefault(); history.back(); return; }
  const print = e.target.closest('[data-print]');
  if (print) { e.preventDefault(); window.print(); return; }
});
window.addEventListener('afterprint', () => document.documentElement.classList.remove('sheet-only'));
// Confirmações numa janela do próprio sistema (no lugar do confirm()/prompt() do navegador, que mostrava a senha
// digitada em texto aberto). Roda na captura: segura o envio, pergunta e, se confirmado, envia de novo.
const NO_FILL = 'autocomplete="off" readonly data-no-autofill data-lpignore="true" data-1p-ignore data-bwignore data-form-type="other"';
const ask = (msg, { password = false, danger = false, ok = 'Confirmar' } = {}) => new Promise((resolve) => {
  let d = document.getElementById('ask-dialog');
  if (!d) {
    d = document.createElement('dialog'); d.id = 'ask-dialog'; d.className = 'dialog ask';
    d.setAttribute('aria-labelledby', 'ask-msg');
    d.innerHTML = '<form method="dialog"><p class="ask-msg" id="ask-msg"></p>'
      + '<div class="field ask-pw"><label for="ask-pw">Sua senha</label><input type="password" id="ask-pw" ' + NO_FILL + '></div>'
      + '<div class="ask-actions"><button class="btn" type="submit" value="no">Cancelar</button><button class="btn primary" type="submit" value="ok" id="ask-ok"></button></div></form>';
    document.body.appendChild(d);
    d.querySelector('#ask-pw').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); if (e.target.value) d.close('ok'); } });
  }
  const pw = d.querySelector('#ask-pw'), okb = d.querySelector('#ask-ok');
  d.querySelector('.ask-msg').textContent = msg; okb.textContent = ok;
  okb.classList.toggle('danger', danger); okb.classList.toggle('primary', !danger);
  d.querySelector('.ask-pw').hidden = !password; pw.value = '';
  d.returnValue = '';
  d.addEventListener('close', () => resolve(d.returnValue === 'ok' ? (password ? pw.value : true) : null), { once: true });
  pw.readOnly = true;                   // trava de novo: o navegador não preenche a cada vez que a janela abre
  d.showModal(); (password ? pw : okb).focus();
});
// Senha pedida DENTRO do sistema (confirmar ação, trocar senha, 2FA): o navegador não preenche sozinho; só no login.
// O campo nasce só-leitura (o preenchimento automático pula esses campos) e libera no toque, no clique ou no foco.
// Ao enviar, a senha segue num campo oculto e o visível fica vazio: o navegador não oferece "salvar senha" com o
// usuário errado (ex.: o formulário de criar usuário, que tem o nome do usuário novo ao lado).
const unlockPw = (e) => {
  const t = e.target; if (!t || !t.closest) return;
  if (t.matches('input[data-no-autofill]')) { t.readOnly = false; return; }
  // campo só-leitura fica fora da validação ("required"): libera antes de o formulário ser conferido no envio
  const f = (e.type === 'keydown' ? e.key === 'Enter' || (e.key === ' ' && !!t.closest('button')) : !!t.closest('button, input[type=submit]')) && t.closest('form');
  if (f) f.querySelectorAll('input[data-no-autofill]').forEach((i) => { i.readOnly = false; });
};
document.addEventListener('pointerdown', unlockPw, true);
document.addEventListener('keydown', unlockPw, true);
document.addEventListener('focusin', unlockPw);
window.addEventListener('submit', (e) => {
  if (e.defaultPrevented) return;
  e.target.querySelectorAll('input[data-no-autofill][name]').forEach((i) => {
    const h = document.createElement('input'); h.type = 'hidden'; h.name = i.name; h.value = i.value; h.dataset.pwCarry = '';
    i.form.appendChild(h); i.dataset.name = i.name; i.removeAttribute('name'); i.value = ''; i.readOnly = true;
  });
});
window.addEventListener('pageshow', () => {           // voltou pelo histórico: o campo volta a ter nome, sem senha
  document.querySelectorAll('input[data-pw-carry]').forEach((h) => h.remove());
  document.querySelectorAll('input[data-no-autofill][data-name]').forEach((i) => { i.name = i.dataset.name; delete i.dataset.name; });
});
const isDanger = (el) => !!(el && (el.classList.contains('danger') || el.querySelector && el.querySelector('.danger')));
const setHidden = (f, name, value) => {
  let h = f.querySelector('input[name=' + name + ']');
  if (!h) { h = document.createElement('input'); h.type = 'hidden'; h.name = name; f.appendChild(h); }
  h.value = value;
};
document.addEventListener('click', (e) => {
  const c = e.target.closest('button[data-confirm], a[data-confirm]');
  if (!c) return;
  if (c.dataset.confirmed) { delete c.dataset.confirmed; return; }
  e.preventDefault(); e.stopImmediatePropagation();
  ask(c.dataset.confirm, { danger: isDanger(c) }).then((r) => { if (r) { c.dataset.confirmed = '1'; c.click(); } });
}, true);
document.addEventListener('submit', (e) => {
  const f = e.target;
  if (!f.dataset || (!f.dataset.confirm && !f.dataset.confirmPassword)) return;
  if (f.dataset.confirmed) { delete f.dataset.confirmed; return; }
  e.preventDefault(); e.stopImmediatePropagation();
  const sub = e.submitter;
  const go = () => { f.dataset.confirmed = '1'; if (f.requestSubmit) f.requestSubmit(sub && sub.form === f ? sub : undefined); else f.submit(); };
  if (f.dataset.confirmPassword) {      // ação sensível (ex.: tirar o 2FA de outro admin): confirma com a SUA senha
    ask(f.dataset.confirmPassword, { password: true, danger: isDanger(f) }).then((pw) => { if (pw) { setHidden(f, 'confirm_password', pw); go(); } });
  } else {
    ask(f.dataset.confirm, { danger: isDanger(f) }).then((r) => { if (r) go(); });
  }
}, true);
document.addEventListener('change', (e) => {
  const t = e.target;
  if (t.id === 'doc' && t.type === 'checkbox' && t.form && !t.hidden) {   // imprimir conta: incluir o original
    const u = new URL(location.href); if (t.checked) u.searchParams.set('doc', '1'); else u.searchParams.delete('doc');
    u.hash = t.checked ? 'original' : ''; location.replace(u.toString()); return;   // replace: o Voltar leva para a tela anterior, não ao mesmo relatório
  }
  if (t.id === 'new-role') {   // criar usuário como admin: mostra o campo de confirmação de senha
    const f = document.getElementById('new-role-confirm'); if (f) f.hidden = t.value !== 'admin';
  }
  if (t.matches('[data-autosubmit]') && t.form) {
    if (t.name === 'role' && t.value === 'admin') {   // promover alguém a admin: confirma com a SUA senha antes de enviar
      const f = t.form, before = [...t.options].find((o) => o.defaultSelected);
      ask('Promover ' + (t.dataset.user || 'este usuário') + ' a administrador? Confirme com a sua senha.', { password: true, ok: 'Promover' })
        .then((pw) => { if (!pw) { if (before) t.value = before.value; return; } setHidden(f, 'confirm_password', pw); f.submit(); });
      return;
    }
    t.form.submit();
  }
  if (t.matches('select[data-bill-switch]')) {
    const doc = document.getElementById('doc');
    location.replace('/bills/' + t.value + '/print' + (doc && doc.checked ? '?doc=1' : ''));
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

  init();
})();

// Unidade consumidora (ponto de energia) de qualquer tela, numa janela. Fica fora do bloco dos avisos de vencimento:
// o administrador não tem o sino, mas também cadastra unidades.
(function () {
  const $ = (id) => document.getElementById(id);
  const dlg = $('point-dialog');
  document.addEventListener('click', async (e) => {
    if (e.target.closest('[data-close-dialog]') && dlg) { e.preventDefault(); dlg.close(); return; }
    const open = e.target.closest('[data-open-point]');
    if (!open || !dlg) return;
    try {
      const store = /^\d+$/.test(open.dataset.store || '') ? '&store_id=' + open.dataset.store : '';     // aberto de uma loja: já vem escolhida
      const r = await fetch('/points/new?fragment=1' + store + '&next=' + encodeURIComponent(location.pathname + location.search), { headers: { Accept: 'text/html' } });
      if (!r.ok) throw new Error(r.status);
      $('point-dialog-body').innerHTML = await r.text(); dlg.showModal(); const f = open.dataset.store ? dlg.querySelector('#pt-num') : dlg.querySelector('select, input'); if (f) f.focus();
    } catch (err) { location.href = '/points/new' + (open.dataset.store ? '?store_id=' + encodeURIComponent(open.dataset.store) : ''); }
  });
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
  const b = f.querySelector('button[type="submit"]'); if (b) { setTimeout(() => { b.classList.add('loading'); b.setAttribute('aria-busy', 'true'); const l = b.querySelector('.lbl'); if (l) l.textContent = 'Entrando…'; else b.textContent = 'Entrando…'; b.disabled = true; }, 0); } }));
// Aviso de Caps Lock no campo de senha.
(function () {
  const p = document.getElementById('p'), w = document.getElementById('caps'); if (!p || !w) return;
  const check = (e) => { if (e.getModifierState) w.hidden = !e.getModifierState('CapsLock'); };
  p.addEventListener('keydown', check); p.addEventListener('keyup', check); p.addEventListener('blur', () => { w.hidden = true; });
})();

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
  // em telas com muitos KPIs (painel executivo tem 8).
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

// Abertura do sistema: segura ~0,3 s e some em fade; uma vez por login e por aba.
(function () {
  const sp = document.getElementById('splash'); if (!sp) return;
  const done = () => sp.remove();
  if (document.documentElement.classList.contains('no-splash')) { done(); return; }
  try { sessionStorage.setItem('economart_splash', sp.dataset.stamp || ''); } catch (e) { /* sem storage: abre de novo na próxima, sem problema */ }
  const hold = Math.max(0, 340 - performance.now());
  const go = () => setTimeout(() => { sp.classList.add('out'); setTimeout(done, 340); }, hold);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go();
})();

// Telas de acesso: a logo nasce do ponto final do gráfico. Mede o deslocamento até o ponto e entrega ao CSS.
(function () {
  const logo = document.querySelector('.auth-logo'), dot = document.querySelector('.auth-art .dot');
  if (!logo || !dot || !dot.getBoundingClientRect().width) return;
  logo.style.animation = 'none';                       // mede sem a transformação do primeiro quadro da animação
  const a = logo.getBoundingClientRect(), d = dot.getBoundingClientRect();
  logo.style.setProperty('--lx', (d.left + d.width / 2 - (a.left + a.width / 2)) + 'px');
  logo.style.setProperty('--ly', (d.top + d.height / 2 - (a.top + a.height / 2)) + 'px');
  void logo.offsetWidth; logo.style.animation = '';    // reinicia a animação já com os valores
})();

// Logout: envia o encerramento da sessão já no primeiro instante e toca a despedida (~1,5 s) antes de ir ao login.
// Se o envio falhar, cai no formulário normal (nunca mostra "sessão encerrada" sem ter encerrado).
document.querySelectorAll('form[action="/logout"]').forEach((f) => f.addEventListener('submit', (e) => {
  const ov = document.getElementById('bye');
  if (!ov || matchMedia('(prefers-reduced-motion: reduce)').matches || f.dataset.busy) return;
  e.preventDefault(); f.dataset.busy = '1';
  const token = f.querySelector('[name=csrf_token]').value;
  ov.hidden = false; void ov.offsetWidth; ov.classList.add('on'); document.body.classList.add('is-leaving');
  const sent = fetch('/logout', { method: 'POST', headers: { 'X-CSRF-Token': token }, credentials: 'same-origin', redirect: 'manual', keepalive: true }).catch(() => null);
  const shown = new Promise((r) => setTimeout(r, 1500));
  Promise.all([sent, shown]).then(([resp]) => {
    if (resp && resp.type === 'opaqueredirect') location.replace('/login?saiu=1');
    else HTMLFormElement.prototype.submit.call(f);
  });
}));

// Painel executivo: copia o resumo em texto (para WhatsApp/e-mail).
document.querySelectorAll('[data-copy-insights]').forEach((btn) => btn.addEventListener('click', async () => {
  const card = btn.closest('.insights'); if (!card) return;
  const lines = [...card.querySelectorAll('li')].map((li) => '• ' + li.lastElementChild.textContent.trim());
  const text = card.querySelector('h2').textContent.trim() + ' — Economart Energia\n' + lines.join('\n');
  try { await navigator.clipboard.writeText(text); }
  catch (e) { const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); try { document.execCommand('copy'); } catch (_) { /* sem permissão */ } t.remove(); }
  const old = btn.textContent; btn.textContent = 'Copiado'; setTimeout(() => { btn.textContent = old; }, 1600);
}));

// Indicadores: os números "contam" até o valor (700 ms, uma vez). Só mexe em valores puramente numéricos (R$ 1.234, 17, 12,5%).
(function () {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const re = /^(R\$\s?)?(\d{1,3}(?:\.\d{3})+|\d+)(,\d+)?(\s*%)?$/;
  const items = [];
  document.querySelectorAll('.kpi .value').forEach((el, i) => {
    const node = [...el.childNodes].find((n) => n.nodeType === 3 && n.textContent.trim());
    if (!node) return;
    const m = node.textContent.trim().match(re); if (!m) return;
    const dec = m[3] ? m[3].length - 1 : 0, target = parseFloat(m[2].replace(/\./g, '') + (m[3] ? '.' + m[3].slice(1) : ''));
    if (!isFinite(target) || target === 0) return;
    items.push({ node, final: node.textContent, prefix: m[1] || '', suffix: m[4] || '', dec, target, delay: 120 + i * 60 });
  });
  if (!items.length) return;
  const fmt = (v, d) => v.toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
  const t0 = performance.now();
  const tick = (now) => {
    let live = false;
    items.forEach((it) => {
      const p = Math.min(1, Math.max(0, (now - t0 - it.delay) / 700));
      if (p < 1) live = true;
      const e = 1 - Math.pow(1 - p, 3);
      it.node.textContent = p >= 1 ? it.final : it.prefix + fmt(it.target * e, it.dec) + it.suffix;
    });
    if (live) requestAnimationFrame(tick);
  };
  items.forEach((it) => { it.node.textContent = it.prefix + fmt(0, it.dec) + it.suffix; });
  requestAnimationFrame(tick);
  addEventListener('beforeprint', () => items.forEach((it) => { it.node.textContent = it.final; }));
})();

// Selo de alertas abertos no menu (busca leve; falha em silêncio).
(function () {
  const el = document.getElementById('alert-count'); if (!el) return;
  fetch('/api/alertas/contagem', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    .then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (!d || !d.count) return;
      el.textContent = d.count > 99 ? '99+' : String(d.count); el.hidden = false; el.classList.toggle('hot', d.high > 0);
    }).catch(() => {});
})();

// Painel executivo: ao imprimir, escolhe o papel (A4 em várias páginas ou A3 em uma folha só).
(() => {
  const menu = document.querySelector('.printmenu'); if (!menu) return;
  const btn = menu.querySelector('[data-print-menu]'), list = menu.querySelector('.printmenu-list');
  const toggle = (open) => { list.hidden = !open; btn.setAttribute('aria-expanded', String(open)); };
  // O hero tem overflow:hidden e isolation:isolate: um menu dentro dele ficava cortado e atrás dos cartões seguintes.
  // Ao abrir, a lista vai para o <body> e é posicionada (fixa) a partir do botão, sem sair da tela (celular).
  const open = () => {
    document.body.appendChild(list);
    Object.assign(list.style, { position: 'fixed', zIndex: '1000', right: 'auto' });
    toggle(true);                                              // visível, para medir a largura
    const r = btn.getBoundingClientRect(), w = list.offsetWidth;
    const left = Math.min(Math.max(8, r.right - w), innerWidth - w - 8);
    Object.assign(list.style, { top: (r.bottom + 6) + 'px', left: left + 'px' });
  };
  btn.addEventListener('click', (e) => { e.stopPropagation(); if (list.hidden) open(); else toggle(false); });
  list.addEventListener('click', (e) => e.stopPropagation());
  document.addEventListener('click', () => toggle(false));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') toggle(false); });
  addEventListener('resize', () => toggle(false)); addEventListener('scroll', () => toggle(false));   // só a rolagem da página (sem captura)
  const a3 = document.getElementById('page-a3'), root = document.documentElement;
  const reset = () => { root.classList.remove('print-a3'); if (a3) a3.media = 'not all'; root.style.removeProperty('--a3fit'); };
  list.addEventListener('click', (e) => {
    const o = e.target.closest('[data-print-size]'); if (!o) return;
    toggle(false);
    if (o.dataset.printSize === 'a3' && a3) {
      a3.media = 'print'; root.classList.add('print-a3');
      const n = Number((document.querySelector('.dirpanel') || {}).dataset?.stores || 0);
      root.style.setProperty('--a3fit', String(Math.max(0.62, Math.min(1, 1030 / (1190 + n * 28)))));   // altura natural medida: ~1190 px + 28 px por loja; folha A3 útil ~1060 px.
      // piso de 62%: até ~18 lojas cabem numa folha; acima disso a letra ficaria ilegível e o painel segue numa 2ª folha A3
    }
    setTimeout(() => window.print(), 80);                                                              // deixa o navegador aplicar o layout A3
  });
  addEventListener('afterprint', reset);
})();

// Botão "Apresentação do sistema": brilha até a pessoa abrir a apresentação uma vez neste navegador.
(function () {
  const b = document.querySelector('.present-btn');
  if (!b) return;
  let seen = false;
  try { seen = localStorage.getItem('apresentacao-vista') === '1'; } catch (e) { /* sem armazenamento: continua brilhando */ }
  if (!seen) b.classList.add('shine');
  b.addEventListener('click', () => { try { localStorage.setItem('apresentacao-vista', '1'); } catch (e) { /* ignora */ } });
})();

// ---------------------------------------------------------------- conexão, sessão e atalhos
// Faixa no topo quando a internet cai ou o servidor não responde. O que foi digitado fica na tela; envio de formulário
// sem conexão é segurado (em vez de trocar a tela por um erro do navegador e perder o que foi preenchido).
const net = (() => {
  let bar = null, serverDown = false, wasOff = false, hideT = 0;
  const el = () => {
    if (!bar) { bar = document.createElement('div'); bar.className = 'netbar no-print'; bar.setAttribute('role', 'status'); bar.setAttribute('aria-live', 'polite'); bar.hidden = true; document.body.appendChild(bar); }
    return bar;
  };
  const show = (text, kind) => { clearTimeout(hideT); const b = el(); b.textContent = text; b.className = 'netbar no-print ' + (kind || 'off'); b.hidden = false; };
  const hide = () => { if (bar) bar.hidden = true; };
  const offline = () => { wasOff = true; show('Sem internet. O que você digitou continua na tela: envie quando a conexão voltar.'); };
  const back = () => { if (!wasOff && !serverDown) return; wasOff = false; serverDown = false; show('Conexão de volta.', 'ok'); hideT = setTimeout(hide, 2500); };
  addEventListener('offline', offline);
  addEventListener('online', back);
  if (!navigator.onLine) offline();
  return {
    error() { if (!navigator.onLine) return offline(); serverDown = true; show('O servidor não respondeu. Tente de novo em instantes.'); },
    ok() { if (serverDown && navigator.onLine) back(); },
    blockSubmit() { show('Sem internet: nada foi enviado. O que você digitou continua na tela; envie quando a conexão voltar.'); el().classList.add('pulse'); },
  };
})();
document.addEventListener('submit', (e) => {
  if (!navigator.onLine && e.target.method && e.target.method.toLowerCase() === 'post') { e.preventDefault(); e.stopImmediatePropagation(); net.blockSubmit(); }
}, true);

// Sessão: avisa 5 min antes de terminar por falta de uso (e deixa continuar com 1 clique) ou pelo limite de horas.
// Sem o aviso, quem passava muito tempo conferindo uma conta perdia o que digitou ao clicar em Salvar.
const session = (() => {
  const b = document.body, idle = Number(b.dataset.idle || 0), maxLeft = Number(b.dataset.maxLeft || 0);
  if (!idle) return { touch() {} };
  const t0 = Date.now(), WARN = 5 * 60 * 1000;
  let idleEnd = t0 + idle * 1000; const maxEnd = maxLeft ? t0 + maxLeft * 1000 : Infinity;
  let d = null, tick = 0;
  const mmss = (ms) => { const s = Math.max(0, Math.ceil(ms / 1000)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
  const build = () => {
    d = document.createElement('dialog'); d.className = 'dialog ask'; d.id = 'session-dialog'; d.setAttribute('aria-labelledby', 'sess-msg');
    d.innerHTML = '<p class="ask-msg" id="sess-msg"></p><div class="ask-actions"><button class="btn" type="button" id="sess-later">Fechar</button><button class="btn primary" type="button" id="sess-go"></button></div>';
    document.body.appendChild(d);
    d.querySelector('#sess-later').addEventListener('click', () => { d.dataset.dismissed = '1'; d.close(); });
    d.querySelector('#sess-go').addEventListener('click', async () => {
      const end = Math.min(idleEnd, maxEnd);
      if (Date.now() >= end) { location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search); return; }
      if (maxEnd - Date.now() <= WARN) { d.close(); return; }           // limite de horas: não há como estender
      try { const r = await fetch('/api/alertas/contagem', { credentials: 'same-origin', headers: { Accept: 'application/json' } }); if (r.ok && !r.redirected) { d.close(); return; } } catch (e) { /* cai abaixo */ }
      location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search);
    });
  };
  const render = () => {
    const now = Date.now(), end = Math.min(idleEnd, maxEnd), left = end - now, byMax = maxEnd <= idleEnd;
    if (left > WARN) { if (d && d.open) d.close(); return; }
    if (!d) build();
    const msg = d.querySelector('#sess-msg'), go = d.querySelector('#sess-go'), later = d.querySelector('#sess-later');
    if (left <= 0 && !d.dataset.ended) { d.dataset.ended = '1'; delete d.dataset.dismissed; }
    if (left <= 0) { msg.textContent = 'Sua sessão terminou. Entre de novo para continuar.'; go.textContent = 'Entrar de novo'; later.hidden = true; }
    else if (byMax) { msg.textContent = 'Sua sessão chega ao limite de horas em ' + mmss(left) + '. Salve o que estiver fazendo; depois é só entrar de novo.'; go.textContent = 'Entendi'; later.hidden = true; }
    else { msg.textContent = 'Sua sessão vai terminar em ' + mmss(left) + ' por falta de uso.'; go.textContent = 'Continuar conectado'; later.hidden = false; }
    if (!d.open && !d.dataset.dismissed) { d.showModal(); go.focus(); }
  };
  tick = setInterval(render, 1000);
  document.addEventListener('visibilitychange', render);
  return { touch() { idleEnd = Date.now() + idle * 1000; if (d) { delete d.dataset.dismissed; render(); } } };
})();

// Toda chamada ao servidor feita pela página renova o prazo da sessão e informa a faixa de conexão.
(() => {
  const orig = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href), own = url.origin === location.origin;
    return orig(input, init).then((r) => {
      if (own) { net.ok(); if (r.ok && !r.redirected) session.touch(); }
      return r;
    }, (err) => { if (own && !(err && err.name === 'AbortError')) net.error(); throw err; });   // falha ao chamar outro endereço não é "servidor fora"
  };
})();

// Formulários longos (conferência da conta, lançamento manual, lote): avisa antes de sair da tela sem salvar.
(() => {
  const forms = document.querySelectorAll('form[data-dirty-guard]'); if (!forms.length) return;
  let dirty = false, sending = false;
  const mark = (e) => { if (e.target.type !== 'search') dirty = true; };     // filtrar a lista não é dado digitado
  forms.forEach((f) => { f.addEventListener('input', mark); f.addEventListener('change', mark); });
  document.addEventListener('submit', (e) => { if (!e.defaultPrevented) sending = true; });
  window.addEventListener('pageshow', () => { sending = false; });
  window.addEventListener('beforeunload', (e) => { if (dirty && !sending) { e.preventDefault(); e.returnValue = ''; } });
})();

// Atalhos de teclado (fora de campos de texto): "/" busca, "i" importa conta, "g" + letra navega, "?" mostra a lista.
// Só valem para o que existe no menu de quem está usando.
(() => {
  const nav = document.querySelector('.side .nav'); if (!nav) return;
  const GO = [['p', '/', 'Painel'], ['e', '/diretoria', 'Painel executivo'], ['c', '/notas', 'Contas'], ['l', '/stores', 'Lojas'],
    ['a', '/alertas', 'Alertas'], ['m', '/manual', 'Lançamento manual'], ['h', '/ajuda', 'Ajuda']]
    .filter(([, href]) => nav.querySelector('a[href="' + href + '"]:not(.cta)'));
  const canImport = !!nav.querySelector('a.cta[href="/import"]');
  let prefix = 0, help = null;
  const showHelp = () => {
    if (!help) {
      help = document.createElement('dialog'); help.className = 'dialog shortcuts'; help.setAttribute('aria-labelledby', 'sc-title');
      const rows = [['/', 'Buscar nesta tela'], ...(canImport ? [['i', 'Importar conta']] : []), ...GO.map(([k, , name]) => ['g ' + k, name]), ['?', 'Esta lista'], ['Esc', 'Fechar janelas']];
      help.innerHTML = '<button class="iconbtn dclose" type="button" aria-label="Fechar">×</button><h2 id="sc-title">Atalhos de teclado</h2><table class="shortcuts-table"><tbody></tbody></table>';
      const tb = help.querySelector('tbody');
      rows.forEach(([k, label]) => {
        const tr = document.createElement('tr'), a = document.createElement('td'), b = document.createElement('td');
        k.split(' ').forEach((part, i) => { if (i) a.append(' depois '); const kb = document.createElement('kbd'); kb.textContent = part; a.append(kb); });
        b.textContent = label; tr.append(a, b); tb.append(tr);
      });
      help.querySelector('.dclose').addEventListener('click', () => help.close());
      document.body.appendChild(help);
    }
    help.showModal();
  };
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
    const t = e.target; if (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || document.querySelector('dialog[open]')) return;
    if (prefix && Date.now() - prefix < 1200) {
      prefix = 0; const hit = GO.find(([k]) => k === e.key.toLowerCase());
      if (hit) { e.preventDefault(); location.href = hit[1]; } return;
    }
    if (e.key === 'g') { prefix = Date.now(); return; }
    if (e.key === '?') { e.preventDefault(); showHelp(); return; }
    if (e.key === '/') { const q = document.querySelector('.main input[type=search]'); if (q) { e.preventDefault(); q.focus(); q.select(); } return; }
    if (e.key === 'i' && canImport) { e.preventDefault(); location.href = '/import'; }
  });
})();

// Tela "sem conexão": um service worker mostra uma página própria (que volta sozinha quando a internet volta) em vez do
// erro do navegador. Ele não guarda nenhuma página com dados: só a tela offline e o logo.
if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
  addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => {}); });
}

