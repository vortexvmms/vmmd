(function () {
  const prefix = '/storage/v1/object/public/dpr-photos/';
  const formerHost = 'lqnbdemtgkermhaqfboh.supabase.co';
  const requests = new Map();

  function privateReference(value) {
    if (typeof value !== 'string') return false;
    if (value.startsWith('vcms-report-image:')) return true;
    try {
      const url = new URL(value);
      return url.protocol === 'https:' && url.pathname.startsWith(prefix) &&
        [formerHost, new URL(VMMS_CONFIG.SUPABASE_URL).host].includes(url.host);
    } catch (_) {
      return false;
    }
  }

  async function resolve(value) {
    if (!privateReference(value)) return value;
    if (!requests.has(value)) {
      const request = vmmsApi('/api/v1/report-images?ref=' + encodeURIComponent(value))
        .then(response => {
          if (!response.ok) throw new Error('Saved report image is unavailable');
          return response.blob();
        })
        .then(URL.createObjectURL)
        .catch(error => {
          requests.delete(value);
          throw error;
        });
      requests.set(value, request);
    }
    return requests.get(value);
  }

  async function fill(root) {
    const outcomes = await Promise.allSettled(
      Array.from(root.querySelectorAll('img[data-report-image]'), async img => {
        img.src = await resolve(img.dataset.reportImage);
      })
    );
    return outcomes.every(result => result.status === 'fulfilled');
  }

  async function upload(blob, path) {
    const response = await vmmsApi('/api/v1/report-images?path=' + encodeURIComponent(path), {
      method: 'PUT', body: blob, headers: {'Content-Type': blob.type || 'application/octet-stream'}
    });
    if (!response.ok) throw new Error('Report image upload failed');
    const result = await response.json();
    if (!result.reference) throw new Error('Report image reference is missing');
    return result.reference;
  }

  window.VCMS_REPORT_IMAGES = {privateReference, resolve, fill, upload};
})();
