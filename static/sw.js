/* Akıllı Sınıf — Service Worker
 * Strateji:
 *   - Statik dosyalar (CSS, ikon, JS) → cache-first
 *   - HTML sayfalar → network-first (offline fallback)
 *   - API çağrıları → network only (kuralı bozma)
 */

const CACHE_VERSION = 'akilli-sinif-v1';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const PAGES_CACHE  = `${CACHE_VERSION}-pages`;

const PRECACHE_URLS = [
  '/',
  '/static/style.css',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/favicon.png',
];

// ── Kurulum: temel dosyaları cache'le ─────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) =>
      cache.addAll(PRECACHE_URLS).catch(() => {})
    ).then(() => self.skipWaiting())
  );
});

// ── Aktivasyon: eski versiyonları temizle ─────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => !k.startsWith(CACHE_VERSION))
            .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch yakalama ────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // API → network only (cache'lemiyoruz, taze veri lazım)
  if (url.pathname.startsWith('/api/')) {
    return; // browser default fetch
  }

  // Statik kaynaklar → cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) return cached;
        return fetch(req).then((resp) => {
          if (resp.ok) {
            const copy = resp.clone();
            caches.open(STATIC_CACHE).then((c) => c.put(req, copy));
          }
          return resp;
        }).catch(() => cached);
      })
    );
    return;
  }

  // HTML sayfalar → network-first (offline'da cache'ten)
  if (req.headers.get('accept')?.includes('text/html') ||
      url.pathname === '/' ||
      !url.pathname.includes('.')) {
    event.respondWith(
      fetch(req).then((resp) => {
        if (resp.ok) {
          const copy = resp.clone();
          caches.open(PAGES_CACHE).then((c) => c.put(req, copy));
        }
        return resp;
      }).catch(() =>
        caches.match(req).then((cached) =>
          cached || caches.match('/').then((root) =>
            root || new Response(
              '<!doctype html><html lang="tr"><meta charset="utf-8">' +
              '<meta name="viewport" content="width=device-width,initial-scale=1">' +
              '<title>Çevrimdışı</title>' +
              '<body style="background:#080c14;color:#e2e8f0;font-family:system-ui;' +
              'min-height:100vh;display:flex;align-items:center;justify-content:center;text-align:center;padding:20px">' +
              '<div><div style="font-size:3rem">📡</div>' +
              '<h2 style="margin:8px 0">Çevrimdışı</h2>' +
              '<p style="color:#6b7280;font-size:.85rem">İnternet bağlantısı yok. ' +
              'Sınıf sunucusuna ulaşılamıyor.</p>' +
              '<button onclick="location.reload()" style="margin-top:12px;background:#38bdf8;' +
              'color:#021;padding:10px 18px;border:none;border-radius:8px;font-weight:700;cursor:pointer">' +
              'Yeniden Dene</button></div></body></html>',
              { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
            )
          )
        )
      )
    );
  }
});
