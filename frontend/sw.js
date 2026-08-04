// VCMS service worker — minimal (network-first) + Web Push handlers.
self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => self.clients.claim());
self.addEventListener('fetch', () => {}); // network-first for now

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
