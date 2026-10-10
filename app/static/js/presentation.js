// Apresentação do sistema: navegação por setas, teclado, pontos, capítulos, toque, tela cheia e zoom nas imagens.
(function () {
  'use strict';
  const slides = Array.from(document.querySelectorAll('.slide'));
  if (!slides.length) return;
  const $ = (id) => document.getElementById(id);
  const dots = $('dots'), counter = $('counter'), progress = $('progress'), prev = $('prev'), next = $('next');
  const chapterBtns = Array.from(document.querySelectorAll('.chapters button'));
  let cur = -1;

  slides.forEach((s, i) => {
    const b = document.createElement('button');
    b.type = 'button'; b.setAttribute('role', 'tab'); b.setAttribute('aria-label', 'Slide ' + (i + 1) + ': ' + (s.getAttribute('aria-label') || ''));
    b.addEventListener('click', () => go(i));
    dots.appendChild(b);
  });

  function go(i, fromHash) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    if (i === cur) return;
    slides.forEach((s, k) => { s.classList.toggle('on', k === i); s.classList.toggle('past', k < i); if (k === i) s.scrollTop = 0; });
    Array.from(dots.children).forEach((d, k) => { d.classList.toggle('on', k === i); d.setAttribute('aria-selected', k === i ? 'true' : 'false'); });
    const ch = slides[i].dataset.chapter;
    chapterBtns.forEach((b) => b.classList.toggle('on', b.dataset.chapter === ch));
    counter.textContent = (i + 1) + ' / ' + slides.length;
    progress.style.width = ((i + 1) / slides.length * 100) + '%';
    prev.disabled = i === 0; next.disabled = i === slides.length - 1;
    cur = i;
    const nextImg = slides[i + 1] && slides[i + 1].querySelector('img[loading=lazy]');   // adianta a próxima imagem
    if (nextImg) nextImg.loading = 'eager';
    if (!fromHash) { try { history.replaceState(null, '', '#' + (i + 1)); } catch (e) { /* sem hash: segue */ } }
  }

  chapterBtns.forEach((b) => b.addEventListener('click', () => {
    const k = slides.findIndex((s) => s.dataset.chapter === b.dataset.chapter);
    if (k >= 0) go(k);
  }));
  prev.addEventListener('click', () => go(cur - 1));
  next.addEventListener('click', () => go(cur + 1));
  const restart = $('restart'); if (restart) restart.addEventListener('click', () => go(0));

  // tela cheia
  const fs = $('fs');
  function toggleFs() {
    if (!document.fullscreenEnabled) return;
    if (document.fullscreenElement) document.exitFullscreen(); else $('deck').requestFullscreen().catch(() => {});
  }
  if (fs) { if (!document.fullscreenEnabled) fs.hidden = true; else fs.addEventListener('click', toggleFs); }

  // zoom nas imagens
  const zoom = $('zoom'), zimg = zoom.querySelector('img');
  function openZoom(img) { zimg.src = img.currentSrc || img.src; zimg.alt = img.alt; zoom.hidden = false; zoom.querySelector('button').focus(); }
  function closeZoom() { zoom.hidden = true; zimg.removeAttribute('src'); }
  document.querySelectorAll('img[data-zoom]').forEach((img) => {
    img.addEventListener('click', () => openZoom(img));
    img.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openZoom(img); } });
  });
  zoom.addEventListener('click', closeZoom);

  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (!zoom.hidden) { if (e.key === 'Escape') { e.preventDefault(); closeZoom(); } return; }
    switch (e.key) {
      case 'ArrowRight': case 'PageDown': case ' ': case 'Enter': if (e.target.closest('button, a, img')) { if (e.key === ' ' || e.key === 'Enter') return; } e.preventDefault(); go(cur + 1); break;
      case 'ArrowLeft': case 'PageUp': e.preventDefault(); go(cur - 1); break;
      case 'Home': e.preventDefault(); go(0); break;
      case 'End': e.preventDefault(); go(slides.length - 1); break;
      case 'f': case 'F': toggleFs(); break;
      case 'Escape': if (!document.fullscreenElement) window.location.href = '/'; break;
      default: break;
    }
  });

  // toque: arrastar para o lado troca de slide
  let x0 = null, y0 = null;
  document.addEventListener('touchstart', (e) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, { passive: true });
  document.addEventListener('touchend', (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
    x0 = y0 = null;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) go(cur + (dx < 0 ? 1 : -1));
  }, { passive: true });

  window.addEventListener('hashchange', () => { const n = parseInt(location.hash.slice(1), 10); if (n) go(n - 1, true); });
  const start = parseInt(location.hash.slice(1), 10);
  go(Number.isFinite(start) ? start - 1 : 0, true);
})();
