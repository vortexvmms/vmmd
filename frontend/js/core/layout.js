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

