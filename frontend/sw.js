// VMMS service worker — Phase 1 (minimal). Full offline caching comes later.
self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => self.clients.claim());
self.addEventListener('fetch', () => {}); // network-first for now
