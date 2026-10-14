/* Service worker da Economart Energia: só a tela "sem conexão".
   Nenhuma página com dados é guardada (as telas mostram contas e valores da empresa e são sempre buscadas no servidor).
   Quando a internet cai e a pessoa clica num link, aparece a tela offline, que volta sozinha quando a conexão volta. */
const VERSION = '__V__';
const CACHE = 'economart-offline-' + VERSION;
const OFFLINE = ['/offline', '/static/js/offline.js?v=' + VERSION, '/static/img/logo.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(OFFLINE.map((u) => new Request(u, { cache: 'reload' })))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k.startsWith('economart-') && k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;                                   // envios de formulário: o navegador cuida
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('/offline')));
    return;
  }
  if (OFFLINE.includes(url.pathname + url.search)) {                  // recursos da própria tela offline
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
  }
});
