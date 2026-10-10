// PR approver choices and self-contained print signatures.
(function () {
  const names = new Map();
  const ADD = '__add_pr_name__';
  function clean(value) { return String(value || '').normalize('NFKC').trim().replace(/\s+/g, ' '); }
  function key(value) { return clean(value).toLocaleLowerCase('en'); }
  function canonical(value) {
    const name=clean(value), compact=key(name).replace(/ /g, '');
    if (compact==='ramasamyrameshkumar'||compact==='rameshkumar') return 'Ramasamy Ramesh Kumar';
    if (compact==='teozhengliang'||compact==='teozhenglian') return 'Teo Zheng Liang';
    return names.get(key(name)) || name;
  }
  function remember(value) { const name=canonical(value); if (name && name!==ADD) names.set(key(name),name); return name; }
  ['Ramasamy Ramesh Kumar','Teo Zheng Liang'].forEach(remember);
  function options(value) {
    value=remember(value);
    const escape = window.esc;
    return '<option value="">Select name…</option>' + [...names.values()].map(name =>
      `<option value="${escape(name)}" ${name === value ? 'selected' : ''}>${escape(name)}</option>`
    ).join('') + `<option value="${ADD}">Add name…</option>`;
  }
  function refreshChoices() {
    document.querySelectorAll('[data-pr-name]').forEach(select => {
      const value = canonical(select.value === ADD ? select.dataset.previous || '' : select.value);
      select.innerHTML = options(value);
      select.value = value;
    });
  }
  function choose(select) {
    if (select.value !== ADD) { select.dataset.previous = select.value; return true; }
    const raw = window.prompt('Enter the new approver name:');
    const name = canonical(raw);
    if (!name || name === ADD || name.length > 160) {
      select.value = canonical(select.dataset.previous);
      if (name.length > 160) window.alert('Use a name of 160 characters or fewer.');
      return false;
    }
    remember(name);
    select.dataset.previous = name;
    refreshChoices();
    select.value = name;
    return true;
  }
  function blobData(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error('Could not read your signature image.'));
      reader.readAsDataURL(blob);
    });
  }
  async function signature(raw) {
    if (!raw) return '';
    if (/^data:image\/(png|jpeg|webp);base64,/i.test(raw)) return raw;
    const response = await window.vmmsApi('/api/v1/pr/signature-image?url=' + encodeURIComponent(raw));
    if (!response.ok) throw new Error('Your saved signature could not be loaded. Upload your signature again before printing.');
    return blobData(await response.blob());
  }
  async function uploadSignature(file) {
    if (!file || !/^image\/(png|jpeg|webp)$/.test(file.type) || file.size > 2 * 1024 * 1024)
      throw new Error('Choose a PNG, JPEG or WebP signature smaller than 2 MB.');
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 1000 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const result = canvas.toDataURL('image/png');
    if (result.length > 3 * 1024 * 1024) throw new Error('Signature image is too large. Choose a smaller image.');
    localStorage.setItem('vcms_my_signature', result);
    return result;
  }
  window.VCMS_PR = { canonical, options, remember, refreshChoices, choose, signature, uploadSignature };
})();
