// VCMS service worker
// Strategy: network-first for app files (HTML/JS/CSS/JSON) fetched with
// cache:'no-store' so a fresh deploy ALWAYS shows up on next load (no more
// stale pages from the browser HTTP cache). Falls back to a cached copy when
// offline. Images/icons are cache-first for speed. API calls to the backend
// and Supabase (cross-origin) are never touched — they go straight to network.

const CACHE = 'vcms-v11-ios-date-height';
const APP_SHELL = [
  './','home.html','attendance.html','request.html','whatsapp.html','dpr.html',
  'css/app.css','js/config.js?v=20260813-7','js/auth.js?v=20260813-7','js/shell.js?v=20260813-7','icons/icon-192.png'
];

self.addEventListener('install', (e) => {
  e.waitUntil((async()=>{
    const c=await caches.open(CACHE);
    await Promise.all(APP_SHELL.map(u=>c.add(u).catch(()=>null)));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', (e) => {
  if (e.data && e.data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  let url;
  try { url = new URL(req.url); } catch (_) { return; }

  // Only manage same-origin GET requests. Everything else (POST, and all
  // cross-origin calls like the FastAPI backend or Supabase) passes through
  // to the network untouched and is never cached.
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;

  const isAppFile =
    req.mode === 'navigate' || /\.(html|js|css|json)$/i.test(url.pathname);

  if (isAppFile) {
    // Network-first, bypassing the browser HTTP cache so deploys are instant.
    e.respondWith((async () => {
      try {
        const fresh = await fetch(req, { cache: 'no-store' });
        if (fresh && fresh.ok) {
          const cache = await caches.open(CACHE);
          cache.put(req, fresh.clone());
        }
        return fresh;
      } catch (err) {
        const cached = await caches.match(req);
        if (cached) return cached;
        if (req.mode === 'navigate') {
          const home = (await caches.match('home.html')) || (await caches.match('./'));
          if (home) return home;
        }
        throw err;
      }
    })());
    return;
  }

  // Static assets (images, icons, fonts): cache-first, refresh in background.
  e.respondWith((async () => {
    const cached = await caches.match(req);
    if (cached) {
      fetch(req)
        .then((res) => { if (res && res.ok) caches.open(CACHE).then((c) => c.put(req, res.clone())); })
        .catch(() => {});
      return cached;
    }
    const res = await fetch(req);
    if (res && res.ok) {
      const cache = await caches.open(CACHE);
      cache.put(req, res.clone());
    }
    return res;
  })());
});

// ---- Web Push (unchanged) ----
// Show a notification when a push arrives (works even when the app is closed).
self.addEventListener('push', function (e) {
  let d = { title: 'VCMS', body: '', url: 'home.html' };
  try { if (e.data) d = Object.assign(d, e.data.json()); } catch (_) {}
  e.waitUntil(self.registration.showNotification(d.title || 'VCMS', {
    body: d.body || '',
    icon: 'icons/icon-192.png',
    badge: 'icons/icon-192.png',
    data: { url: d.url || 'home.html' },
    tag: d.tag || undefined,
    renotify: !!d.tag
  }));
});

// Focus/open the app when the notification is tapped.
self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  var target = (e.notification.data && e.notification.data.url) || 'home.html';
  var url = new URL(target, self.registration.scope).href;
  e.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      var c = list[i];
      if ('focus' in c) { try { c.navigate(url); } catch (_) {} return c.focus(); }
    }
    if (clients.openWindow) return clients.openWindow(url);
  }));
});
