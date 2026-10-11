// Служебный скрипт «Флигеля»: приложение открывается без интернета (последняя шахматка, «Сегодня», уборка —
// только для чтения). Ответы API кладутся в кэш браузера на этом устройстве и стираются при выходе из аккаунта.
const SHELL = 'fligel-shell-v2';
const API = 'fligel-api-v1';
// Модули интерфейса (static/admin/*.js) должны быть здесь все — это проверяет тест
const SHELL_FILES = ['/app/', '/static/admin/app.js', '/static/admin/auth.js', '/static/admin/board.js', '/static/admin/booking.js', '/static/admin/bookings.js', '/static/admin/channels.js', '/static/admin/cleaning.js', '/static/admin/core.js', '/static/admin/finance.js', '/static/admin/guests.js', '/static/admin/help.js', '/static/admin/notifications.js', '/static/admin/owner.js', '/static/admin/profile.js', '/static/admin/rates.js', '/static/admin/reviews.js', '/static/admin/reports.js', '/static/admin/settings.js', '/static/admin/tasks.js', '/static/admin/today.js', '/static/admin/ui.js', '/static/admin/app.css', '/manifest.webmanifest', '/static/icons/icon.svg'];
// Только экраны для чтения; всё остальное (изменения, отчёты, экспорт) всегда идёт напрямую на сервер
const API_READABLE = /^\/api\/(board|today|me|housekeeping|properties\/[0-9a-f-]+|bookings|notifications|badges|landlord\/(board|report|properties))(\?.*)?$/;

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => Promise.all(SHELL_FILES.map((u) => c.add(u).catch(() => {})))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => ![SHELL, API].includes(k)).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('message', (e) => { if (e.data === 'clear') caches.delete(API); });

async function networkFirst(req, cacheName, stamp) {
  const cache = await caches.open(cacheName);
  try {
    const res = await fetch(req);
    if (res.ok) {
      if (stamp) {
        const body = await res.clone().blob();
        const headers = new Headers(res.headers);
        headers.set('X-Cached-At', String(Date.now()));
        await cache.put(req, new Response(body, { status: res.status, headers }));
      } else {
        await cache.put(req, res.clone());
      }
    }
    return res;
  } catch (err) {
    const hit = await cache.match(req);
    if (!hit) throw err;
    if (!stamp) return hit;
    const headers = new Headers(hit.headers);
    headers.set('X-From-Cache', '1');
    return new Response(await hit.blob(), { status: hit.status, headers });
  }
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/')) {
    if (API_READABLE.test(url.pathname + url.search)) e.respondWith(networkFirst(req, API, true));
    return;
  }
  if (url.pathname === '/app/' || url.pathname.startsWith('/static/') || url.pathname === '/manifest.webmanifest') e.respondWith(networkFirst(req, SHELL, false));
});
