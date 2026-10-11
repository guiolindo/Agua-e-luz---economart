// Apresentação do sistema: navegação (setas, teclado, pontos, capítulos, toque), cortina entre capítulos, passar sozinho,
// tela cheia, zoom nas imagens, comparador antes/depois, contadores e inclinação 3D das telas.
(function () {
  'use strict';
  const all = Array.from(document.querySelectorAll('.slide'));
  if (!all.length) return;
  let slides = all;                                   // slides do modo atual (completo ou resumo)
  const $ = (id) => document.getElementById(id);
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const dots = $('dots'), counter = $('counter'), progress = $('progress'), prev = $('prev'), next = $('next'), wipe = $('wipe'), play = $('play');
  const chapterBtns = Array.from(document.querySelectorAll('.chapters button'));
  const modeBtn = $('mode');
  const pad = (n) => String(n).padStart(2, '0');
  let cur = -1, locked = false, timer = null, autoplay = false, summary = false;

  function buildDots() {
    dots.textContent = '';
    slides.forEach((s, i) => {
      const b = document.createElement('button');
      b.type = 'button'; b.setAttribute('aria-label', 'Slide ' + (i + 1) + ': ' + (s.getAttribute('aria-label') || ''));
      b.addEventListener('click', () => go(i));
      dots.appendChild(b);
    });
    chapterBtns.forEach((b) => { b.hidden = !slides.some((s) => s.dataset.chapter === b.dataset.chapter); });
  }
  buildDots();

  // ---- ao entrar no slide: contadores e comparador
  function animate(ms, step, done) {
    const t0 = performance.now();
    (function frame(t) {
      const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
      step(e);
      if (k < 1) requestAnimationFrame(frame); else if (done) done();
    })(t0);
  }
  function onEnter(slide) {
    const kind = slide.dataset.enter;
    if (kind === 'count') {
      slide.querySelectorAll('[data-count]').forEach((el) => {
        const to = +el.dataset.count;
        if (reduced) { el.textContent = to; return; }
        el.textContent = '0';
        setTimeout(() => animate(1500, (e) => { el.textContent = String(Math.round(to * e)); }), 700);
      });
    }
    if (kind === 'cmp') {
      setCmp(reduced ? 50 : 100);
      if (!reduced) setTimeout(() => animate(1900, (e) => setCmp(100 - 50 * e)), 1100);
    }
  }

  // ---- ir para o slide i (com cortina quando muda o capítulo)
  function show(i, fromHash) {
    const dir = i > cur ? 1 : -1;
    all.forEach((s) => { const k = slides.indexOf(s); s.classList.toggle('on', k === i); s.classList.toggle('past', k !== -1 && k < i); if (k === i) s.scrollTop = 0; });
    Array.from(dots.children).forEach((d, k) => { d.classList.toggle('on', k === i); if (k === i) d.setAttribute('aria-current', 'true'); else d.removeAttribute('aria-current'); });
    const ch = slides[i].dataset.chapter;
    chapterBtns.forEach((b) => { const on = b.dataset.chapter === ch; b.classList.toggle('on', on); if (on) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current'); });
    counter.textContent = pad(i + 1) + ' / ' + pad(slides.length);
    progress.style.width = ((i + 1) / slides.length * 100) + '%';
    prev.disabled = i === 0; next.disabled = i === slides.length - 1;
    cur = i;
    onEnter(slides[i]);
    [1, 2].forEach((d) => { const im = slides[i + d] && slides[i + d].querySelector('img[loading=lazy]'); if (im) im.loading = 'eager'; });   // adianta as próximas telas
    if (!fromHash) { try { history.replaceState(null, '', '#' + (summary ? 'r' : '') + (i + 1)); } catch (e) { /* sem hash: segue */ } }
    if (autoplay) arm();
    return dir;
  }
  function go(i, fromHash) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    if (i === cur || locked) return;
    const changesChapter = cur >= 0 && slides[i].dataset.chapter !== slides[cur].dataset.chapter;
    if (changesChapter && !reduced && !fromHash) {
      locked = true; wipe.classList.remove('run'); void wipe.offsetWidth; wipe.classList.add('run');
      setTimeout(() => show(i, fromHash), 430);
      setTimeout(() => { locked = false; wipe.classList.remove('run'); }, 950);
    } else show(i, fromHash);
  }

  // ---- passar sozinho
  function arm() { clearTimeout(timer); timer = setTimeout(() => { if (cur >= slides.length - 1) setAuto(false); else go(cur + 1); }, 9000); }
  function setAuto(on) { autoplay = on; play.setAttribute('aria-pressed', on ? 'true' : 'false'); if (on) arm(); else clearTimeout(timer); }
  play.addEventListener('click', () => setAuto(!autoplay));

  // ---- resumo (8 slides) × completo
  function setMode(on, keep, fromHash) {
    const here = cur >= 0 ? slides[cur] : null;
    summary = on; slides = on ? all.filter((s) => s.hasAttribute('data-sum')) : all;
    modeBtn.setAttribute('aria-pressed', on ? 'true' : 'false'); modeBtn.textContent = on ? 'Completo' : 'Resumo';
    modeBtn.title = on ? 'Voltar à apresentação completa (R)' : 'Alternar entre resumo (8 slides, cerca de 1 min) e completo (R)';
    buildDots(); cur = -1; locked = false;
    let i = keep && here ? slides.indexOf(here) : 0;
    if (i < 0) i = Math.max(0, slides.findIndex((s) => all.indexOf(s) > all.indexOf(here)));   // o slide atual não está no resumo: vai ao próximo que está
    show(i, !!fromHash);
  }
  modeBtn.addEventListener('click', () => setMode(!summary, true));

  chapterBtns.forEach((b) => b.addEventListener('click', () => { const k = slides.findIndex((s) => s.dataset.chapter === b.dataset.chapter); if (k >= 0) go(k); }));
  prev.addEventListener('click', () => go(cur - 1));
  next.addEventListener('click', () => go(cur + 1));
  const restart = $('restart'); if (restart) restart.addEventListener('click', () => go(0));

  // ---- tela cheia
  const fs = $('fs');
  function toggleFs() { if (!document.fullscreenEnabled) return; if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(() => {}); }
  if (fs) { if (!document.fullscreenEnabled) fs.hidden = true; else fs.addEventListener('click', toggleFs); }

  // ---- zoom nas imagens
  const zoom = $('zoom'), zimg = zoom.querySelector('img');
  let opener = null;
  function openZoom(img) { opener = img; zimg.src = img.currentSrc || img.src; zimg.alt = img.alt; zoom.hidden = false; zoom.querySelector('button').focus(); }
  function closeZoom() { zoom.hidden = true; zimg.removeAttribute('src'); if (opener) { opener.focus(); opener = null; } }
  document.querySelectorAll('img[data-zoom]').forEach((img) => {
    img.addEventListener('click', () => openZoom(img));
    img.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); openZoom(img); } });
  });
  zoom.addEventListener('click', closeZoom);

  // ---- comparador antes / depois
  const cmp = $('cmp');
  function setCmp(p) { if (!cmp) return; p = Math.max(0, Math.min(100, p)); cmp.style.setProperty('--p', p + '%'); cmp.setAttribute('aria-valuenow', String(Math.round(p))); }
  if (cmp) {
    const fromX = (e) => { const r = cmp.getBoundingClientRect(); setCmp((e.clientX - r.left) / r.width * 100); };
    cmp.addEventListener('pointerdown', (e) => { cmp.setPointerCapture(e.pointerId); fromX(e); cmp.dataset.drag = '1'; });
    cmp.addEventListener('pointermove', (e) => { if (cmp.dataset.drag) fromX(e); });
    const stop = () => { delete cmp.dataset.drag; };
    cmp.addEventListener('pointerup', stop); cmp.addEventListener('pointercancel', stop);
  }

  // ---- inclinação 3D das telas (só com mouse)
  if (!reduced && window.matchMedia('(hover: hover)').matches) {
    document.querySelectorAll('.dev').forEach((dev) => {
      const tilt = dev.querySelector('.tilt');
      dev.addEventListener('mousemove', (e) => {
        const r = dev.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
        tilt.style.setProperty('--ry', (x * 7).toFixed(2) + 'deg'); tilt.style.setProperty('--rx', (-y * 5).toFixed(2) + 'deg');
      });
      dev.addEventListener('mouseleave', () => { tilt.style.setProperty('--ry', '0deg'); tilt.style.setProperty('--rx', '0deg'); });
    });
  }

  // ---- teclado
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (!zoom.hidden) {
      if (e.key === 'Escape') { e.preventDefault(); closeZoom(); }
      else if (e.key === 'Tab') { e.preventDefault(); zoom.querySelector('button').focus(); }     // foco preso no diálogo (só há o botão Fechar)
      return;
    }
    if (e.target === cmp && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); setCmp(+cmp.getAttribute('aria-valuenow') + (e.key === 'ArrowRight' ? 5 : -5)); return; }
    const onControl = !!e.target.closest('button, a, img');
    switch (e.key) {
      case 'ArrowRight': case 'PageDown': e.preventDefault(); go(cur + 1); break;
      case ' ': case 'Enter': if (onControl) return; e.preventDefault(); go(cur + 1); break;
      case 'ArrowLeft': case 'PageUp': e.preventDefault(); go(cur - 1); break;
      case 'Home': e.preventDefault(); go(0); break;
      case 'End': e.preventDefault(); go(slides.length - 1); break;
      case 'f': case 'F': toggleFs(); break;
      case 'p': case 'P': setAuto(!autoplay); break;
      case 'r': case 'R': setMode(!summary, true); break;
      case 'Escape': if (!document.fullscreenElement) window.location.href = '/'; break;
      default: break;
    }
  });

  // ---- toque: arrastar para o lado troca de slide (o comparador tem o próprio gesto)
  let x0 = null, y0 = null;
  document.addEventListener('touchstart', (e) => { x0 = e.target.closest('#cmp') ? null : e.touches[0].clientX; y0 = e.touches[0].clientY; }, { passive: true });
  document.addEventListener('touchend', (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
    x0 = y0 = null;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) go(cur + (dx < 0 ? 1 : -1));
  }, { passive: true });

  const parseHash = () => { const m = /^#(r?)(\d+)$/.exec(location.hash); return m ? { r: !!m[1], n: parseInt(m[2], 10) } : null; };
  window.addEventListener('hashchange', () => { const h = parseHash(); if (!h) return; if (h.r !== summary) setMode(h.r, false, true); go(h.n - 1, true); });
  const h0 = parseHash();
  if (h0 && h0.r) setMode(true, false, true);
  go(h0 ? h0.n - 1 : 0, true);
})();
