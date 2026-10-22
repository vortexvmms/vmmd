(function () {
  'use strict';
  let worker = null, image = null, busy = false, sourceURL = null;
  const dialog = document.createElement('dialog'); dialog.id = 'photo-editor';
  dialog.innerHTML = `<h2>Worker profile photo</h2><p id="photo-worker"></p>
    <p>Choose a clear face photo. Adjust the crop, then save.</p>
    <label>Upload photo <input id="photo-file" type="file" accept="image/jpeg,image/png,image/webp"></label>
    <label>Take photo <input id="photo-camera" type="file" accept="image/*" capture="user"></label>
    <canvas id="photo-canvas" width="480" height="480" aria-label="Photo crop preview"></canvas>
    <label>Zoom <input id="photo-zoom" type="range" min="1" max="3" step="0.05" value="1"></label>
    <label>Horizontal position <input id="photo-x" type="range" min="0" max="1" step="0.01" value="0.5"></label>
    <label>Vertical position <input id="photo-y" type="range" min="0" max="1" step="0.01" value="0.5"></label>
    <p id="photo-error" role="status" aria-live="polite"></p>
    <div class="photo-actions"><button id="photo-close">Close</button><button id="photo-remove">Remove photo</button><button id="photo-save" disabled>Save photo</button></div>`;
  document.body.append(dialog);
  const el = id => document.getElementById(id);
  const canvas = el('photo-canvas'), ctx = canvas.getContext('2d');
  function draw() {
    ctx.clearRect(0, 0, 480, 480);
    if (!image) return;
    const size = Math.min(image.naturalWidth, image.naturalHeight) / Number(el('photo-zoom').value);
    ctx.drawImage(image, (image.naturalWidth-size)*Number(el('photo-x').value), (image.naturalHeight-size)*Number(el('photo-y').value), size, size, 0, 0, 480, 480);
  }
  function lock(on) { busy = on; dialog.querySelectorAll('button,input').forEach(e => e.disabled = on); el('photo-save').disabled = on || !image; }
  async function choose(event) {
    const file = event.target.files[0]; if (!file) return;
    image = null; draw(); el('photo-save').disabled = true; el('photo-error').textContent = '';
    if (file.size > 20 * 1024 * 1024) { el('photo-error').textContent = 'Choose a photo under 20 MB.'; return; }
    if (sourceURL) URL.revokeObjectURL(sourceURL);
    sourceURL = URL.createObjectURL(file);
    const next = new Image();
    next.onload = () => { image = next; ['photo-zoom','photo-x','photo-y'].forEach((id,i)=>el(id).value=i?'0.5':'1'); draw(); el('photo-save').disabled = false; };
    next.onerror = () => { el('photo-error').textContent = 'Cannot read this photo. Choose JPG, PNG or WebP.'; };
    next.src = sourceURL;
  }
  el('photo-file').onchange = choose; el('photo-camera').onchange = choose;
  ['photo-zoom','photo-x','photo-y'].forEach(id=>el(id).oninput=draw);
  el('photo-close').onclick = () => { if (!busy) dialog.close(); };
  dialog.addEventListener('cancel', e => { if (busy) e.preventDefault(); });
  async function save(remove) {
    if (busy || !worker || (!remove && !image)) return;
    if (remove && !confirm('Remove the profile photo for '+worker.name+'?')) return;
    lock(true); el('photo-error').textContent = 'Saving…';
    try {
      const blob = remove ? null : await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',0.85));
      if (!remove && !blob) throw Error('Could not prepare photo. Choose it again.');
      const r = await vmmsApi('/api/v1/worker-photos/'+encodeURIComponent(worker.id), {method:remove?'DELETE':'POST', ...(blob?{body:blob,headers:{'Content-Type':'image/jpeg'}}:{})});
      const data = await r.json(); if (!r.ok) throw Error(data.detail || 'Could not save photo');
      vmmsClearRefCache('/api/v1/workers'); await load(); dialog.close(); toast(remove?'Profile photo removed':'Profile photo saved');
    } catch(e) { el('photo-error').textContent = e.message; } finally { lock(false); }
  }
  el('photo-save').onclick=()=>save(false); el('photo-remove').onclick=()=>save(true);
  window.openWorkerPhoto = async function(w) {
    if (busy) return; worker = w; image = null; draw();
    el('photo-worker').textContent = w.worker_code+' · '+w.name;
    el('photo-error').textContent = ''; el('photo-file').value = ''; el('photo-camera').value = '';
    el('photo-remove').hidden = !w.photo_path; el('photo-save').disabled = true;
    dialog.showModal();
    if (w.photo_path) {
      const url=await WorkerPhotos.photo(w.id,w.photo_path);
      if (url && worker===w && dialog.open && !image) { const im=new Image(); im.onload=()=>{if(worker===w&&!image){image=im;draw();}}; im.src=url; }
    }
  };
})();
