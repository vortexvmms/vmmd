// ---- Small text-form draft recovery (no photos, files, signatures or secrets) ----
// Media remains in the server/upload flow; only ordinary fields are retained.
(function(){
  var page=(location.pathname.split('/').pop()||'').toLowerCase();
  if(page!=='dpr.html'&&page!=='pr-new.html')return;
  var key='vcms_draft_'+page, timer=null, suppress=false;
  function fields(){return Array.prototype.slice.call(document.querySelectorAll('input[id]:not([type=file]):not([type=password]),select[id],textarea[id]'));}
  function save(){
    var data={t:Date.now(),v:{}}; fields().forEach(function(el){if(el.id)data.v[el.id]=el.type==='checkbox'?!!el.checked:el.value;});
    try{localStorage.setItem(key,JSON.stringify(data));}catch(_){}
  }
  function restore(){
    var d;try{d=JSON.parse(localStorage.getItem(key)||'null');}catch(_){return}
    if(!d||!d.v)return; fields().forEach(function(el){if(Object.prototype.hasOwnProperty.call(d.v,el.id)){if(el.type==='checkbox')el.checked=!!d.v[el.id];else el.value=d.v[el.id];}});
    suppress=true; document.dispatchEvent(new Event('input',{bubbles:true}));setTimeout(function(){suppress=false},0);
    var b=document.getElementById('vmms-draft-banner');if(b)b.remove();
  }
  window.vmmsClearPageDraft=function(){try{localStorage.removeItem(key);}catch(_){}var b=document.getElementById('vmms-draft-banner');if(b)b.remove();};
  function offer(){
    var d;try{d=JSON.parse(localStorage.getItem(key)||'null');}catch(_){return}
    if(!d||!d.t||Date.now()-d.t>24*3600000)return;
    var b=document.createElement('div');b.id='vmms-draft-banner';b.style.cssText='position:fixed;left:12px;right:12px;bottom:calc(78px + env(safe-area-inset-bottom,0px));z-index:9998;background:#202631;color:#fff;border-radius:12px;padding:11px 13px;box-shadow:0 8px 24px rgba(0,0,0,.22);font:600 13px system-ui;display:flex;align-items:center;gap:10px';
    b.innerHTML='<span style="flex:1">An unfinished text draft is available.</span><button id="vmms-draft-restore" style="background:#C00000;color:#fff;border:0;border-radius:8px;padding:8px 10px;font-weight:800">Restore</button><button id="vmms-draft-discard" style="background:transparent;color:#fff;border:0;padding:7px">Discard</button>';
    document.body.appendChild(b);b.querySelector('#vmms-draft-restore').onclick=restore;b.querySelector('#vmms-draft-discard').onclick=window.vmmsClearPageDraft;
  }
  document.addEventListener('input',function(e){if(suppress||!(e.target&&e.target.id))return;clearTimeout(timer);timer=setTimeout(save,500);},true);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){setTimeout(offer,1200)});else setTimeout(offer,1200);
})();

