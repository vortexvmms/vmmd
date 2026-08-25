// ---- Desktop workspace standardisation (mobile markup and navigation untouched) ----
// Each operational page receives a stable page class. This lets directory, admin
// and report screens use the available laptop/monitor width without changing the
// familiar phone workflow used by supervisors.
(function () {
  var slug = (location.pathname.split("/").pop() || "home.html").replace(/\.html$/i, "").replace(/[^a-z0-9-]/gi, "");
  function tag(){ if(document.body) document.body.classList.add("vmms-page-" + slug); }
  if(document.body) tag(); else document.addEventListener("DOMContentLoaded",tag);
  var s=document.createElement("style"); s.id="vmms-desktop-workspaces";
  s.textContent=`
  @media screen and (min-width:900px){
    body[class*="vmms-page-"] main{width:calc(100% - 40px);max-width:1480px;margin-left:auto;margin-right:auto}
    body.vmms-page-workers main,body.vmms-page-sites main,body.vmms-page-users main,
    body.vmms-page-whatsapp main,body.vmms-page-reports main,body.vmms-page-manhours main,
    body.vmms-page-dprlist main,body.vmms-page-pr-directory main,body.vmms-page-settings main{
      max-width:none!important;width:100%!important;padding:20px 24px 70px!important
    }
    body.vmms-page-sites #list{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px!important}
    body.vmms-page-sites #list>*{margin:0!important;min-width:0}
    body.vmms-page-users main>div,body.vmms-page-pr-directory main>div,body.vmms-page-dprlist main>div,
    body.vmms-page-reports main>div,body.vmms-page-manhours main>div,body.vmms-page-settings main>div{
      border-color:#dce1e8!important;box-shadow:0 7px 20px rgba(15,23,42,.07)!important
    }
    body.vmms-page-whatsapp main{max-width:1100px!important;margin-left:auto!important;margin-right:auto!important}
    body.vmms-page-whatsapp #msg{min-height:420px;font-size:14px;line-height:1.65}
    body.vmms-page-dprlist table,body.vmms-page-pr-directory table,
    body.vmms-page-reports table,body.vmms-page-manhours table{width:100%}
  }
  @media screen and (min-width:1500px){
    body[class*="vmms-page-"] main{max-width:none}
    body.vmms-page-workers #list,body.vmms-page-sites #list{grid-template-columns:repeat(4,minmax(0,1fr))}
  }`;
  (document.head||document.documentElement).appendChild(s);
})();

// ---- Stage 3: progressively standardise management and report pages ----
// The decorator only adds shared classes; IDs, inline handlers and page-specific
// classes remain untouched, so operational behaviour is unchanged.
(function () {
  var excluded={login:1,index:1,home:1,home2:1,request:1,attendance:1,allocation:1,whatsapp:1,camera:1};
  function apply(){
    var slug=(location.pathname.split("/").pop()||"home.html").replace(/\.html$/i,"");
    if(excluded[slug]||!document.body)return;
    document.body.classList.add("vcms-standard-page");
    var header=document.querySelector("body>header");
    if(header){
      header.classList.add("vcms-legacy-header");
      var title=header.querySelector("h1"); if(title)title.classList.add("vcms-legacy-title");
      var back=header.querySelector('a[href="home.html"]'); if(back){back.classList.add("vcms-page-header__back");back.setAttribute("aria-label","Back to home")}
    }
    document.querySelectorAll('main input:not([type]),main input[type="text"],main input[type="search"],main input[type="email"],main input[type="password"],main input[type="number"],main input[type="date"],main input[type="time"],main input[type="tel"],main input[type="url"],main select,main textarea').forEach(function(el){
      if(!el.classList.contains("vcms-control"))el.classList.add("vcms-control");
    });
    document.querySelectorAll("button").forEach(function(btn){
      if(btn.closest(".grp-items,.nav,.schedule-tabs")||btn.classList.contains("vcms-btn"))return;
      var c=btn.className||"";
      if(/bg-red-(600|700|800)|bg-green-(600|700)/.test(c))btn.classList.add("vcms-btn",/bg-green/.test(c)?"vcms-btn-success":"vcms-btn-primary");
      else if(/border-red-(600|700)|text-red-(600|700)/.test(c))btn.classList.add("vcms-btn","vcms-btn-tertiary");
    });
    document.querySelectorAll('#toast,[role="status"][class*="fixed"]').forEach(function(el){el.classList.add("vcms-toast")});
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",apply);else apply();
})();

// ---- Stage 4: accessibility and resilient interaction defaults ----
(function(){
  function apply(){
    document.querySelectorAll("button:not([type])").forEach(function(b){if(!b.closest("form"))b.type="button"});
    document.querySelectorAll("input,select,textarea").forEach(function(el){
      if(!el.getAttribute("aria-label")&&!el.getAttribute("aria-labelledby")){
        var label=el.closest("label"), text=label&&label.textContent.trim();
        if(text)el.setAttribute("aria-label",text.slice(0,100));
        else if(el.placeholder)el.setAttribute("aria-label",el.placeholder);
      }
    });
    var main=document.querySelector("main");if(main&&!main.id)main.id="main-content";
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",apply);else apply();
})();

// ---- Light global polish (safe, non-breaking): crisper type + nicer scrollbars ----
(function () {
  if (document.getElementById("vcms-polish")) return;
  var s = document.createElement("style"); s.id = "vcms-polish";
  s.textContent =
    "html{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;text-rendering:optimizeLegibility;}" +
    "@media(min-width:1024px){::-webkit-scrollbar{width:10px;height:10px}" +
    "::-webkit-scrollbar-thumb{background:#CBD5E1;border-radius:8px}" +
    "::-webkit-scrollbar-thumb:hover{background:#94A3B8}" +
    "body:not(.shell){background:#E4E7EC !important}" +
    // Use the empty desktop gutters: widen phone-width content containers to ~1024px.
    // Excludes bottom-sheet modals (rounded-t-2xl) and pages that already opted into a
    // wider desktop width (md:max-w-*). Login stays narrow (uses max-w-sm).
    "[class~=\"max-w-md\"]:not([class*=\"md:max-w\"]):not([class*=\"rounded-t-2xl\"])" +
    "{max-width:64rem !important;}}";
  (document.head || document.documentElement).appendChild(s);
})();

// ---- Load the app-shell nav rail on every signed-in page (self-skips login/home) ----
(function () {
  var sh = document.createElement("script"); sh.src = "js/shell.js?v=20260813-8"; sh.defer = true;
  (document.head || document.documentElement).appendChild(sh);
})();
