/* Service worker — o checklist precisa abrir sem rede, dentro do aviao.
   Estrategia: cache primeiro para o proprio aplicativo, com atualizacao em
   segundo plano.

   Ao mudar qualquer arquivo, suba o numero em DOIS lugares: no CACHE aqui e
   no `?v=` dos <script>/<link> do index.html. E o `?v=` que faz o navegador
   buscar o arquivo novo em vez de servir o antigo da propria memoria. */
'use strict';

const CACHE = 'sling-tsi-v6';

const SHELL = [
  '.',
  'index.html',
  'style.css?v=6',
  'app.js?v=6',
  'wb.js?v=6',
  'wb_screen.js?v=6',
  'manifest.webmanifest',
  'data/Checklists-PB.json',
  'data/perfis_wb.json',
  'assets/sling_tsi.png',
  'assets/icon-192.png',
  'assets/icon-512.png',
  'assets/icon-maskable-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    // um `addAll` falha inteiro se um unico arquivo faltar, e ai o app fica
    // sem cache nenhum: aqui cada arquivo e guardado por conta propria
    const resultados = await Promise.allSettled(
      SHELL.map((url) => cache.add(new Request(url, { cache: 'reload' })))
    );
    const falhas = SHELL.filter((_url, i) => resultados[i].status === 'rejected');
    if (falhas.length) console.warn('[sw] fora do cache:', falhas);
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names.filter((name) => name !== CACHE).map((name) => caches.delete(name))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;   // RedeMet, AISweb...

  // abrir o app sem rede (atalho na tela de inicio, aba restaurada) cai aqui:
  // qualquer endereco de navegacao responde com a pagina guardada
  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        return await fetch(request);
      } catch (err) {
        return (await caches.match(request))
          || (await caches.match('index.html'))
          || (await caches.match('.'))
          || new Response('Aplicativo indisponivel sem rede.', {
            status: 503, headers: { 'Content-Type': 'text/plain' },
          });
      }
    })());
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);
      // offline responde do cache; online atualiza a copia para a proxima vez
      return cached || network;
    })
  );
});
