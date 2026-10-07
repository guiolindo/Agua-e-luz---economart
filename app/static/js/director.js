// Painel da diretoria: gráficos comparativos (dados vêm de #dir-data; sem JS inline).
(function () {
  if (typeof Chart === 'undefined') return;
  const D = JSON.parse(document.getElementById('dir-data').textContent);
  const rows = D.rows;
  const nfBRL0 = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
  const nfBRL3 = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const nfN = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });
  const GRID = '#eceff3', INK = '#5d6b7c', UP = '#c0504d', DOWN = '#2e8b57', NEUTRAL = '#7f8b9b', BLUE = '#1b4f8a';
  const PALETTE = ['#1b4f8a', '#f47920', '#4f9a94', '#8a6aa3', '#b08a3e', '#7a8f5a', '#7f8b9b', '#b0605f', '#3d5a80', '#9c6644', '#6b8e23', '#a05195'];
  Chart.defaults.font.family = 'Inter, "Segoe UI", system-ui, sans-serif'; Chart.defaults.color = INK;
  const arrow = (p) => p == null ? '—' : (p > 0 ? '↑ ' : p < 0 ? '↓ ' : '→ ') + nfN.format(Math.abs(p)) + '%';
  const $ = (id) => document.getElementById(id);
  const refLine = (value, color, label) => ({ id: 'ref' + label, afterDatasetsDraw(c) {
    const x = c.scales.x.getPixelForValue(value); if (!isFinite(x)) return;
    const { top, bottom } = c.chartArea, g = c.ctx; g.save(); g.strokeStyle = color; g.setLineDash([5, 4]); g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(x, top); g.lineTo(x, bottom); g.stroke(); g.setLineDash([]); g.fillStyle = color; g.font = '11px sans-serif'; g.fillText(label, x + 4, top + 11); g.restore(); } });
  const hbar = (id, labels, data, colors, fmtFn, extra = {}) => new Chart($(id), {
    type: 'bar', data: { labels, datasets: [{ data, backgroundColor: colors, borderRadius: 2, maxBarThickness: 22 }] },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, animation: false, ...extra.options,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (i) => fmtFn(i.raw, i.dataIndex) } }, ...(extra.plugins || {}) },
      scales: { x: { grid: { color: GRID }, ticks: { callback: (v) => (extra.tick || ((x) => x))(v) }, ...(extra.x || {}) }, y: { grid: { display: false } } } },
    plugins: extra.refs || [] });

  // 1) empresa por mês, empilhado por fornecedor + linha de variação
  new Chart($('c-month'), { data: { labels: D.labels, datasets: [
      ...D.by_type.map((t) => ({ type: 'bar', label: t.name, data: t.values, backgroundColor: t.color, stack: 's', yAxisID: 'y', maxBarThickness: 44 })),
      { type: 'line', label: 'Variação do total (%)', data: D.month_vars, borderColor: '#1c2430', backgroundColor: '#1c2430', borderWidth: 2, pointRadius: 3, spanGaps: true, yAxisID: 'y1' } ] },
    options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
      scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, beginAtZero: true, grid: { color: GRID }, ticks: { callback: (v) => nfBRL0.format(v) } },
                y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { callback: (v) => v + '%' } } },
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } }, tooltip: { callbacks: { label: (i) => i.dataset.yAxisID === 'y1' ? 'Variação: ' + arrow(i.raw) : i.dataset.label + ': ' + nfBRL0.format(i.raw) } } } } });

  // 2) ranking
  const top = rows.slice(0, 15);
  hbar('c-rank', top.map((r) => r.code), top.map((r) => r.total), top.map((r, i) => i === 0 ? BLUE : '#9aa5b4'),
       (v, i) => nfBRL0.format(v) + ' · ' + nfN.format(top[i].share) + '% da empresa', { tick: (v) => nfBRL0.format(v) });

  // 3) variação último mês vs anterior
  const mv = rows.filter((r) => r.var_last != null).sort((a, b) => b.var_last - a.var_last).slice(0, 20);
  hbar('c-var', mv.map((r) => r.code), mv.map((r) => r.var_last), mv.map((r) => r.var_last > 0 ? UP : r.var_last < 0 ? DOWN : NEUTRAL),
       (v, i) => arrow(v) + ' (' + nfBRL0.format(mv[i].before) + ' → ' + nfBRL0.format(mv[i].last) + ')', { tick: (v) => v + '%' });

  // 4) composição por fornecedor (100%)
  const typeIds = Object.keys(D.types);
  new Chart($('c-mix'), { type: 'bar', data: { labels: top.map((r) => r.code), datasets: typeIds.map((id) => ({
      label: D.types[id].name, backgroundColor: D.types[id].color, data: top.map((r) => r.total ? ((r.mix[id] || 0) / r.total) * 100 : 0) })) },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, animation: false,
      scales: { x: { stacked: true, max: 100, grid: { color: GRID }, ticks: { callback: (v) => v + '%' } }, y: { stacked: true, grid: { display: false } } },
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } }, tooltip: { callbacks: { label: (i) => i.dataset.label + ': ' + nfN.format(i.raw) + '%' } } } } });

  // 5) evolução das lojas (com seleção)
  const lineChart = new Chart($('c-line'), { type: 'line', data: { labels: D.labels, datasets: rows.map((r, i) => ({
      label: r.code, data: r.values, borderColor: PALETTE[i % PALETTE.length], backgroundColor: PALETTE[i % PALETTE.length], borderWidth: 2, pointRadius: 2.5, spanGaps: true, hidden: i >= 5 })) },
    options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'nearest', intersect: false },
      scales: { y: { beginAtZero: true, grid: { color: GRID }, ticks: { callback: (v) => nfBRL0.format(v) } }, x: { grid: { display: false } } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (i) => i.dataset.label + ': ' + nfBRL0.format(i.raw) } } } } });
  const pick = $('storepick');
  rows.forEach((r, i) => { const l = document.createElement('label'); l.className = 'chk';
    l.innerHTML = '<input type="checkbox"' + (i < 5 ? ' checked' : '') + '><span class="dot" style="background:' + PALETTE[i % PALETTE.length] + '"></span>' + r.code;
    l.querySelector('input').addEventListener('change', (e) => { lineChart.setDatasetVisibility(i, e.target.checked); lineChart.update('none'); }); pick.appendChild(l); });

  // 6) R$/kWh e 7) uso da demanda
  const ek = rows.filter((r) => r.rs_kwh).sort((a, b) => b.rs_kwh - a.rs_kwh);
  hbar('c-kwh', ek.map((r) => r.code), ek.map((r) => r.rs_kwh), ek.map((r) => D.avg_rs_kwh && r.rs_kwh > D.avg_rs_kwh ? UP : '#9aa5b4'),
       (v) => nfBRL3.format(v) + '/kWh', { tick: (v) => nfBRL3.format(v), refs: D.avg_rs_kwh ? [refLine(D.avg_rs_kwh, BLUE, 'média ' + nfBRL3.format(D.avg_rs_kwh))] : [] });
  const eu = rows.filter((r) => r.demand_use != null).sort((a, b) => b.demand_use - a.demand_use);
  hbar('c-util', eu.map((r) => r.code), eu.map((r) => r.demand_use), eu.map((r) => r.demand_use > 100 ? UP : r.demand_use < 70 ? '#c9a227' : '#5b9a6b'),
       (v, i) => nfN.format(v) + '% da demanda contratada' + (eu[i].demand_over ? ' · ' + eu[i].demand_over + ' conta(s) acima' : ''),
       { tick: (v) => v + '%', refs: [refLine(100, UP, '100%')], x: { suggestedMax: 110 } });

  // 8) comparar duas lojas
  const A = $('pair-a'), B = $('pair-b');
  rows.forEach((r, i) => { [A, B].forEach((s) => s.add(new Option(r.code + (r.name ? ' — ' + r.name : ''), i))); });
  A.value = 0; B.value = rows.length > 1 ? 1 : 0;
  const pairChart = new Chart($('c-pair'), { type: 'bar', data: { labels: D.labels, datasets: [
      { label: '', data: [], backgroundColor: '#1b4f8a', maxBarThickness: 26 }, { label: '', data: [], backgroundColor: '#f47920', maxBarThickness: 26 } ] },
    options: { responsive: true, maintainAspectRatio: false, animation: false, scales: { y: { beginAtZero: true, grid: { color: GRID }, ticks: { callback: (v) => nfBRL0.format(v) } }, x: { grid: { display: false } } },
      plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: (i) => i.dataset.label + ': ' + nfBRL0.format(i.raw) } } } } });
  function drawPair() {
    const a = rows[A.value], b = rows[B.value];
    pairChart.data.datasets[0].label = a.code; pairChart.data.datasets[0].data = a.values;
    pairChart.data.datasets[1].label = b.code; pairChart.data.datasets[1].data = b.values; pairChart.update('none');
    const cell = (v) => '<td class="num">' + (v == null ? '' : nfBRL0.format(v)) + '</td>';
    const diff = a.values.map((v, i) => (v == null || b.values[i] == null) ? null : v - b.values[i]);
    const pct = a.values.map((v, i) => (v == null || !b.values[i]) ? null : ((v - b.values[i]) / b.values[i]) * 100);
    const th = D.labels.map((l) => '<th class="num">' + l + '</th>').join('');
    $('pair-table').innerHTML = '<thead><tr><th><span class="sr">Loja</span></th>' + th + '<th class="num">Total</th></tr></thead><tbody>' +
      '<tr><td><strong>' + a.code + '</strong></td>' + a.values.map(cell).join('') + '<td class="num"><strong>' + nfBRL0.format(a.total) + '</strong></td></tr>' +
      '<tr><td><strong>' + b.code + '</strong></td>' + b.values.map(cell).join('') + '<td class="num"><strong>' + nfBRL0.format(b.total) + '</strong></td></tr>' +
      '<tr class="sub"><td>Diferença (R$)</td>' + diff.map(cell).join('') + '<td class="num">' + nfBRL0.format(a.total - b.total) + '</td></tr>' +
      '<tr class="sub"><td>Diferença (%)</td>' + pct.map((p) => '<td class="num">' + (p == null ? '' : arrow(p)) + '</td>').join('') + '<td class="num">' + (b.total ? arrow(((a.total - b.total) / b.total) * 100) : '') + '</td></tr></tbody>';
  }
  A.addEventListener('change', drawPair); B.addEventListener('change', drawPair); drawPair();
  window.addEventListener('beforeprint', () => Chart.instances && Object.values(Chart.instances).forEach((c) => c.resize()));
})();
