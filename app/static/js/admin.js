// Gráficos do painel do administrador (Chart.js, sem JS inline). Cada <canvas data-viz='{...}'> traz rótulos e séries.
// Regras: cor fixa por papel (IA = azul, à mão = laranja), um eixo só, barras de até 24px com a ponta arredondada
// (só a ponta de cima da pilha), 2px de respiro branco entre segmentos, grade fina, legenda quando há 2+ séries.
(function () {
  'use strict';
  if (!window.Chart) return;
  const COLORS = { ia: '#2e6bb0', mao: '#d9661a' };
  const MAIN = '#2e6bb0', INK = '#52514e', GRID = '#e8e8e4';
  const nf = new Intl.NumberFormat('pt-BR');
  Chart.defaults.font.family = 'Inter, "Segoe UI", system-ui, sans-serif';
  Chart.defaults.color = INK;

  document.querySelectorAll('canvas[data-viz]').forEach((cv) => {
    const cfg = JSON.parse(cv.dataset.viz);
    const horizontal = !!cfg.horizontal, multi = cfg.series.length > 1;
    // ponta arredondada só no último segmento com valor (a "ponta" da barra); a base fica reta
    const tip = (ctx) => {
      const i = ctx.dataIndex, sets = ctx.chart.data.datasets;
      let top = -1;
      sets.forEach((s, k) => { if (ctx.chart.isDatasetVisible(k) && s.data[i]) top = k; });
      if (ctx.datasetIndex !== top) return 0;
      return horizontal ? { topRight: 4, bottomRight: 4 } : { topLeft: 4, topRight: 4 };
    };
    const datasets = cfg.series.map((s) => ({
      label: s.label, data: s.data, backgroundColor: COLORS[s.key] || MAIN,
      borderRadius: tip, borderSkipped: false, maxBarThickness: 24,
      borderColor: '#fff', borderWidth: multi ? (horizontal ? { left: 0, right: 2, top: 0, bottom: 0 } : { top: 2, left: 0, right: 0, bottom: 0 }) : 0,
    }));
    const valueAxis = { stacked: multi, beginAtZero: true, grid: { color: GRID, drawTicks: false }, border: { display: false },
      ticks: { precision: 0, padding: 6, callback: (v) => nf.format(v) } };
    const catAxis = { stacked: multi, grid: { display: false }, border: { color: GRID },
      ticks: { autoSkip: !horizontal, maxRotation: 0, padding: 4 } };
    const chart = new Chart(cv, {
      type: 'bar',
      data: { labels: cfg.labels, datasets },
      options: {
        indexAxis: horizontal ? 'y' : 'x', responsive: true, maintainAspectRatio: false, animation: { duration: 400 },
        interaction: { mode: 'index', axis: horizontal ? 'y' : 'x', intersect: false },
        scales: horizontal ? { x: valueAxis, y: catAxis } : { x: catAxis, y: valueAxis },
        plugins: {
          legend: { display: multi, position: 'bottom', labels: { usePointStyle: true, pointStyle: 'rectRounded', boxWidth: 10, padding: 14 } },
          tooltip: {
            backgroundColor: '#10243f', padding: 10, cornerRadius: 6, boxPadding: 4,
            callbacks: {
              title: (items) => (cfg.titles ? cfg.titles[items[0].dataIndex] : items[0].label),
              label: (it) => ' ' + it.dataset.label + ': ' + nf.format(it.raw),
              footer: (items) => (multi ? 'Total: ' + nf.format(items.reduce((a, it) => a + (it.raw || 0), 0)) : ''),
            },
          },
        },
        onHover: (e, els) => { if (cfg.links) e.native.target.style.cursor = els.length && cfg.links[els[0].index] ? 'pointer' : 'default'; },
        onClick: (e, els) => { if (cfg.links && els.length && cfg.links[els[0].index]) window.location.href = cfg.links[els[0].index]; },
      },
    });
    window.addEventListener('beforeprint', () => chart.resize());
  });
})();
