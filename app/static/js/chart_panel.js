(function () {
  const panel = document.querySelector('[data-chart-panel]');
  if (!panel || typeof Chart === 'undefined') return;
  const state = JSON.parse(panel.dataset.state);
  const canvas = panel.querySelector('canvas');
  const box = panel.querySelector('.chart-box');
  const empty = panel.querySelector('.chart-empty');
  const note = panel.querySelector('[data-chart-note]');
  const q = (n) => panel.querySelector('[name="' + n + '"]');
  let chart = null, inFlight = 0;

  const nfBRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  const nfNum = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 });
  const fmt = (kind, v) => v == null ? '—' : kind === 'brl' ? nfBRL.format(v) : nfNum.format(v) + (kind === 'kwh' ? ' kWh' : kind === 'kw' ? ' kW' : '');
  const fmtAxis = (kind, v) => kind === 'brl' ? 'R$ ' + nfNum.format(v) : nfNum.format(v);

  function params() {
    const p = new URLSearchParams();
    const view = panel.querySelector('[name="view"]:checked');
    p.set('view', view ? view.value : 'units');
    ['type_id', 'indicator', 'start', 'end'].forEach((n) => { const el = q(n); if (el && el.value) p.set(n, el.value); });
    if (state.highlight) p.set('highlight', state.highlight);
    if (state.unit_id) p.set('unit_id', state.unit_id);
    return p;
  }

  function syncVisibility() {
    const view = panel.querySelector('[name="view"]:checked');
    const types = view && view.value === 'types';
    panel.querySelectorAll('[data-when="units"]').forEach((el) => { el.hidden = types; });
  }

  function fillIndicators(list, current) {
    const sel = q('indicator');
    if (!sel || !list) return;
    sel.innerHTML = '';
    list.forEach((i) => { const o = document.createElement('option'); o.value = i.key; o.textContent = i.label; if (i.key === current) o.selected = true; sel.appendChild(o); });
  }

  async function load() {
    syncVisibility();
    const ticket = ++inFlight;
    note.textContent = 'Carregando…';
    let data;
    try {
      const r = await fetch(panel.dataset.url + '?' + params().toString(), { headers: { Accept: 'application/json' } });
      if (!r.ok) throw new Error(r.status);
      data = await r.json();
    } catch (e) { note.textContent = 'Não foi possível carregar o gráfico.'; return; }
    if (ticket !== inFlight) return;
    note.textContent = '';
    ['start', 'end'].forEach((n) => { const el = q(n); if (el && !el.value && data[n]) el.value = data[n]; });
    history.replaceState(null, '', '?' + params().toString());
    if (data.indicators) fillIndicators(data.indicators, data.indicator && data.indicator.key);
    draw(data);
  }

  function draw(data) {
    if (chart) { chart.destroy(); chart = null; }
    const has = !data.empty && data.series.some((s) => s.data.some((v) => v != null));
    box.hidden = !has; empty.hidden = has;
    if (!has) return;
    const kind = data.indicator.kind;
    const anyHl = data.series.some((s) => s.highlight);
    const multi = data.series.length > 1;
    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: data.series.map((s) => ({
          label: s.label + (s.highlight ? ' (importada agora)' : ''), data: s.data, backgroundColor: s.color,
          borderRadius: 2, maxBarThickness: 46, order: s.highlight ? 0 : 1, _s: s,
          borderColor: s.highlight ? '#073b73' : 'transparent', borderWidth: s.highlight ? 1.5 : 0,
        })),
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 250 },
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
        scales: {
          x: { stacked: !!data.stacked, grid: { display: false } },
          y: { stacked: !!data.stacked, beginAtZero: true, ticks: { callback: (v) => fmtAxis(kind, v) }, grid: { color: '#eceff3' } },
        },
        plugins: {
          legend: { display: multi, position: 'bottom', labels: { boxWidth: 12, boxHeight: 12, font: { weight: (c) => 'normal' } } },
          tooltip: {
            padding: 10, displayColors: true,
            callbacks: {
              title: (items) => { const m = data.months[items[0].dataIndex]; return items[0].chart.data.labels[items[0].dataIndex] + ' · ' + m; },
              label: (item) => item.dataset._s.label + ': ' + fmt(kind, item.raw),
              afterLabel: (item) => {
                const s = item.dataset._s, i = item.dataIndex, out = [];
                if (s.sublabel) out.push(s.sublabel);
                const v = s.variations[i];
                if (v && v.text !== '—') out.push('Variação vs. mês anterior: ' + v.text);
                (s.lines[i] || []).forEach((l) => { if (!l.startsWith(data.indicator.label + ':')) out.push(l); });
                return out;
              },
            },
          },
        },
      },
    });
    note.textContent = anyHl ? 'A barra em azul-escuro é a unidade da conta importada.' : '';
  }

  panel.addEventListener('change', (e) => {
    if (e.target.name === 'type_id') { const sel = q('indicator'); if (sel) sel.innerHTML = ''; }
    load();
  });
  load();
})();
