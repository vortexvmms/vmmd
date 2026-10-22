/* Shared portraits: lazy authenticated fetches, in-memory URLs and initials fallback. */
(function () {
  'use strict';
  const cache = new Map();
  const escape = v => window.esc(v);
  function markup(worker) {
    const name = worker.worker_name || worker.name || '';
    const initials = name.trim().split(/\s+/).slice(0, 2).map(n => n[0] || '').join('').toUpperCase() || '?';
    const id = worker.worker_id || worker.id || '';
    return `<button type="button" class="worker-portrait" data-worker="${escape(id)}" data-photo="${escape(worker.photo_path || '')}" aria-label="View photo of ${escape(name)}"><span>${escape(initials)}</span></button>`;
  }
  async function photo(id, version) {
    const key = id + ':' + version;
    if (!cache.has(key)) {
      const request = vmmsApi('/api/v1/worker-photos/' + encodeURIComponent(id)).then(async r => {
        if (!r.ok || !r.headers.get('Content-Type')?.startsWith('image/')) throw Error('No photo');
        return URL.createObjectURL(await r.blob());
      }).catch(() => { cache.delete(key); return null; });
      cache.set(key, request);
    }
    return cache.get(key);
  }
  const observer = new IntersectionObserver(entries => entries.forEach(async entry => {
    if (!entry.isIntersecting) return;
    const el = entry.target; observer.unobserve(el);
    if (!el.dataset.photo || !el.dataset.worker) return;
    const url = await photo(el.dataset.worker, el.dataset.photo);
    if (!url || !el.isConnected) return;
    const im = new Image(); im.alt = ''; im.src = url; im.decoding = 'async'; el.append(im);
    el.onclick = event => {
      event.stopPropagation();
      let dialog = document.getElementById('portrait-viewer');
      if (!dialog) {
        dialog = document.createElement('dialog'); dialog.id = 'portrait-viewer';
        dialog.innerHTML = '<form method="dialog"><button aria-label="Close photo">Close ×</button></form><img alt="Worker profile photo">';
        document.body.append(dialog);
      }
      dialog.querySelector('img').src = url; dialog.showModal();
    };
  }), {rootMargin: '160px'});
  function hydrate(root = document) {
    root.querySelectorAll('.worker-portrait').forEach(el => {
      if (!el.dataset.observed) { el.dataset.observed = '1'; observer.observe(el); }
    });
  }
  window.WorkerPhotos = {markup, hydrate, photo};
})();
