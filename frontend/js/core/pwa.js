// ---- PWA updater: show at most once per release and reload only after the
// new worker controls the page. This prevents iPhone's repeated update loop. ----
(function(){
  if(!('serviceWorker' in navigator))return;
  var RELEASE='20260825-ui5', seenKey='vcms_update_seen_'+RELEASE, reloading=false;
  function reloadOnce(){
    if(reloading)return;reloading=true;
    try{localStorage.setItem(seenKey,'1')}catch(_){}
    var b=document.getElementById('vmms-update');if(b)b.remove();
    var u=new URL(location.href);u.searchParams.set('_vcms',RELEASE);location.replace(u.toString());
  }
  window.addEventListener('load',function(){
    navigator.serviceWorker.register('sw.js?v='+RELEASE,{updateViaCache:'none'}).then(function(reg){
      navigator.serviceWorker.addEventListener('controllerchange',function(){
        if(document.getElementById('vmms-update'))reloadOnce();
      });
      reg.update().catch(function(){});
      reg.addEventListener('updatefound',function(){var nw=reg.installing;if(!nw)return;nw.addEventListener('statechange',function(){
        var seen=false;try{seen=localStorage.getItem(seenKey)==='1'}catch(_){}
        if(nw.state==='installed'&&navigator.serviceWorker.controller&&!seen&&!document.getElementById('vmms-update')){
          var b=document.createElement('button');b.id='vmms-update';b.textContent='VCMS update ready — tap once';b.style.cssText='position:fixed;left:12px;right:12px;bottom:calc(14px + env(safe-area-inset-bottom,0px));z-index:10001;border:0;border-radius:11px;background:#202631;color:#fff;padding:12px;font:800 13px system-ui;box-shadow:0 8px 24px rgba(0,0,0,.25)';
          b.onclick=function(){b.disabled=true;b.textContent='Updating VCMS…';try{localStorage.setItem(seenKey,'1')}catch(_){}if(reg.waiting)reg.waiting.postMessage({type:'SKIP_WAITING'});setTimeout(reloadOnce,900)};document.body.appendChild(b);
        }
      })});
    }).catch(function(){});
  });
})();

