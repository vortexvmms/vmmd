// ---- HTML escaper (XSS hardening) ----
// Wrap any user-entered value (worker/site/supervisor names, codes, notes)
// before putting it into innerHTML, so a name containing markup can't run.
window.esc = function (v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
};

// ---- Display theme (Light / Sunlight / Dark) — shared by all pages ----
// Applied here (config.js loads in <head> on every page) so the whole app is
// themed with no page-by-page changes and no flash of the wrong colours.
// Header stays Vortex red in every theme (brand + high contrast already).
(function () {
  var THEMES = { light: 1, sun: 1, dark: 1 };
  var t = localStorage.getItem("vcms_theme");
  if (!THEMES[t]) t = "light";
  document.documentElement.setAttribute("data-theme", t);
  if (document.getElementById("vcms-theme-css")) return;
  var css =
    /* ===== SUNLIGHT: bright white, near-black bold text, bigger fonts ===== */
    ':root[data-theme="sun"]{font-size:17px;}' +
    ':root[data-theme="sun"] body,:root[data-theme="sun"] .bg-gray-100,:root[data-theme="sun"] .bg-gray-50,:root[data-theme="sun"] .grid-home{background:#ffffff !important;color:#000 !important;}' +
    ':root[data-theme="sun"] .bg-white,:root[data-theme="sun"] .panel{background:#ffffff !important;color:#000 !important;border:1.5px solid #111 !important;}' +
    ':root[data-theme="sun"] .text-gray-900,:root[data-theme="sun"] .text-gray-800,:root[data-theme="sun"] .text-gray-700,:root[data-theme="sun"] .text-gray-600,:root[data-theme="sun"] .text-gray-500,:root[data-theme="sun"] .text-gray-400{color:#000 !important;}' +
    ':root[data-theme="sun"] .border,:root[data-theme="sun"] .border-gray-100,:root[data-theme="sun"] .border-gray-200,:root[data-theme="sun"] .border-gray-300{border-color:#111 !important;}' +
    ':root[data-theme="sun"] .divide-gray-100>*+*{border-color:#111 !important;}' +
    ':root[data-theme="sun"] input,:root[data-theme="sun"] select,:root[data-theme="sun"] textarea{background:#fff !important;color:#000 !important;border-color:#111 !important;}' +
    ':root[data-theme="sun"] .app-lbl,:root[data-theme="sun"] .sect-h .t{color:#000 !important;font-weight:700 !important;}' +
    /* ===== DARK: for night / indoor ===== */
    ':root[data-theme="dark"] body,:root[data-theme="dark"] .bg-gray-100,:root[data-theme="dark"] .bg-gray-50,:root[data-theme="dark"] .grid-home{background:#0f1216 !important;color:#e5e7eb !important;}' +
    ':root[data-theme="dark"] .bg-white,:root[data-theme="dark"] .panel{background:#1b2028 !important;color:#e5e7eb !important;}' +
    ':root[data-theme="dark"] .text-gray-900,:root[data-theme="dark"] .text-gray-800,:root[data-theme="dark"] .text-gray-700{color:#e5e7eb !important;}' +
    ':root[data-theme="dark"] .text-gray-600,:root[data-theme="dark"] .text-gray-500,:root[data-theme="dark"] .text-gray-400{color:#9aa4b2 !important;}' +
    ':root[data-theme="dark"] .border,:root[data-theme="dark"] .border-gray-100,:root[data-theme="dark"] .border-gray-200,:root[data-theme="dark"] .border-gray-300{border-color:#2b323c !important;}' +
    ':root[data-theme="dark"] .divide-gray-100>*+*{border-color:#2b323c !important;}' +
    ':root[data-theme="dark"] input,:root[data-theme="dark"] select,:root[data-theme="dark"] textarea{background:#0f1216 !important;color:#e5e7eb !important;border-color:#3a4150 !important;}' +
    ':root[data-theme="dark"] .app-lbl{color:#cbd2dc !important;}' +
    ':root[data-theme="dark"] .sect-h .t{color:#e5e7eb !important;}' +
    ':root[data-theme="dark"] .soon-note,:root[data-theme="dark"] .sect.soon .sect-h .t{color:#6b7280 !important;}' +
    ':root[data-theme="dark"] .vmms-bell-panel,:root[data-theme="dark"] #vmms-bell-panel{background:#1b2028 !important;}';
  var s = document.createElement("style");
  s.id = "vcms-theme-css"; s.textContent = css;
  (document.head || document.documentElement).appendChild(s);
})();
window.vmmsGetTheme = function () { var t = localStorage.getItem("vcms_theme"); return (t === "sun" || t === "dark") ? t : "light"; };
window.vmmsSetTheme = function (t) {
  if (t !== "sun" && t !== "dark") t = "light";
  localStorage.setItem("vcms_theme", t);
  document.documentElement.setAttribute("data-theme", t);
};

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
    body.vmms-page-cards main,body.vmms-page-training-matrix main,body.vmms-page-worker-cards main,
    body.vmms-page-whatsapp main,body.vmms-page-reports main,body.vmms-page-manhours main,
    body.vmms-page-dprlist main,body.vmms-page-pr-directory main,body.vmms-page-settings main{
      max-width:none!important;width:100%!important;padding:20px 24px 70px!important
    }
    body.vmms-page-workers #list,body.vmms-page-sites #list{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px!important}
    body.vmms-page-workers #list>*,body.vmms-page-sites #list>*{margin:0!important;min-width:0}
    body.vmms-page-users main>div,body.vmms-page-pr-directory main>div,body.vmms-page-dprlist main>div,
    body.vmms-page-reports main>div,body.vmms-page-manhours main>div,body.vmms-page-settings main>div{
      border-color:#dce1e8!important;box-shadow:0 7px 20px rgba(15,23,42,.07)!important
    }
    body.vmms-page-whatsapp main{max-width:1100px!important;margin-left:auto!important;margin-right:auto!important}
    body.vmms-page-whatsapp #msg{min-height:420px;font-size:14px;line-height:1.65}
    body.vmms-page-training-matrix table,body.vmms-page-dprlist table,body.vmms-page-pr-directory table,
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
  var sh = document.createElement("script"); sh.src = "js/shell.js"; sh.defer = true;
  (document.head || document.documentElement).appendChild(sh);
})();

// ---- Role tiers (Rev 6) — shared by all pages ----
window.VMMS_TIER = {
  full: ["admin", "general_manager", "operation_manager", "hr_assistant"],
  manager: ["main_sup", "wshc_lead"],
  supervisor: ["site_sup", "safety_sup", "wshc", "logistics_sup"],
};
window.isFull = function (r) { return VMMS_TIER.full.indexOf(r) !== -1; };
window.isManager = function (r) { return VMMS_TIER.manager.indexOf(r) !== -1; };
window.isSupervisor = function (r) { return VMMS_TIER.supervisor.indexOf(r) !== -1; };
window.isCoordinator = function (r) { return isFull(r) || isManager(r); };  // can broadcast messages

// VCMS configuration
window.VMMS_CONFIG = {
  BACKEND_URL: "https://vmms-backend-sg.onrender.com",
  SUPABASE_URL: "https://lqnbdemtgkermhaqfboh.supabase.co",
  SUPABASE_PUBLISHABLE: "sb_publishable_GV2oQS2wP2ltMeg2Teh1Rw_qT3lLGno"
};

// ---- Brand colour grading (applies on every page) ----
// This file loads right after the Tailwind CDN, so overriding the "red"
// ramp here re-colours all bg-red-* / text-red-* utilities app-wide with
// no per-page edits. One unified brand red = #C00000.
if (window.tailwind) {
  tailwind.config = {
    theme: { extend: { colors: { red: {
      50:  "#FDECEC",
      100: "#F9D2D2",
      200: "#F1A3A3",
      300: "#E76F6F",
      400: "#D83C3C",
      500: "#CE1414",
      600: "#C00000",
      700: "#C00000",   // primary buttons + accents  → Vortex brand red
      800: "#A00000",   // hover / darker
      900: "#8A0000",   // deepest (e.g. logout)
      950: "#6E0000"
    } } } }
  };
}

// Header bars sit one shade darker than the brand buttons, for hierarchy.
// (Higher specificity than the utility class, so no !important needed.)
(function () {
  var s = document.createElement("style");
  s.textContent = "header.bg-red-700{background-color:#A00000}";
  document.head.appendChild(s);
})();

// ---- Modern Soft UI theme + subtle motion (applies app-wide) ----
// Everything is wrapped in @media screen so PRINT / PDF output is never
// touched (verification, timesheet & dashboard print layouts stay exact).
(function () {
  var css = `
  @media screen {
    :root{
      --vmms-red:#C00000; --vmms-page:#eef0f3; --vmms-card:#ffffff; --vmms-line:#e7e9ee;
      --vmms-radius:16px;
      --vmms-shadow:0 1px 2px rgba(16,24,40,.05), 0 8px 20px -12px rgba(16,24,40,.22);
      --vmms-shadow-lg:0 16px 34px -14px rgba(16,24,40,.28);
      --vmms-ease:cubic-bezier(.22,.61,.36,1);
    }
    body{ background:var(--vmms-page) !important; }
    main{ animation:vmms-fade-up .55s var(--vmms-ease) both; }

    header.bg-red-700{
      background:linear-gradient(135deg,#C00000 0%,#9c0000 55%,#8a0000 100%) !important;
      box-shadow:0 8px 22px -12px rgba(138,0,0,.65); border-bottom:none;
    }

    .rounded-xl.shadow-sm{
      border-radius:var(--vmms-radius); box-shadow:var(--vmms-shadow) !important;
      transition:transform .28s var(--vmms-ease), box-shadow .28s var(--vmms-ease),
                 background-color .28s ease, border-color .28s ease;
    }
    .bg-gray-100.rounded-xl{ background:var(--vmms-card); border-color:var(--vmms-line); }

    @media (hover:hover){
      a.rounded-xl.shadow-sm:hover, label.rounded-xl.shadow-sm:hover{
        transform:translateY(-2px); box-shadow:var(--vmms-shadow-lg) !important; }
    }
    a.rounded-xl.shadow-sm:active, label.rounded-xl.shadow-sm:active{ transform:scale(.985); }

    button{ transition:transform .2s var(--vmms-ease), box-shadow .24s var(--vmms-ease),
                         background-color .24s ease, opacity .24s ease; }
    button:not(:disabled):active{ transform:scale(.955); }
    button.bg-red-700{ box-shadow:0 8px 18px -10px rgba(192,0,0,.7); }

    input:focus,select:focus,textarea:focus{
      outline:none; border-color:var(--vmms-red) !important; box-shadow:0 0 0 3px rgba(192,0,0,.16); }

    /* tab buttons / pill toggles get a smooth colour swap */
    [id^="tab-"], [id^="t-"]{ transition:background-color .28s ease, color .28s ease, transform .18s var(--vmms-ease); }

    /* staggered tile entrance — applied by JS (vmms-reveal) to every card
       grid / list on every page, once per render batch (see config.js) */

    #vmms-home-fab{ transition:transform .2s var(--vmms-ease), box-shadow .24s ease;
                    animation:vmms-pop .42s var(--vmms-ease) both .12s; }
    #vmms-home-fab:active{ transform:scale(.9); }
  }
  @keyframes vmms-fade-up{ from{opacity:0; transform:translateY(12px)} to{opacity:1; transform:none} }
  @keyframes vmms-pop{ from{opacity:0; transform:scale(.8)} to{opacity:1; transform:scale(1)} }
  @media (prefers-reduced-motion: reduce){ *,*::before,*::after{ animation:none !important; transition:none !important; } }
  `;
  var s = document.createElement("style");
  s.id = "vmms-theme";
  s.textContent = css;
  (document.head || document.documentElement).appendChild(s);
})();

// ---- Staggered tile entrance on EVERY page (home-menu style) ----
// Animates the card tiles in any grid/list whenever they are rendered:
// on page load, tab switch, date change, dashboard tiles, etc.
// Throttled per-container so rapid re-renders (typing in a search box,
// ticking attendance) don't machine-gun the animation.
(function () {
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  var THROTTLE = 600;                 // ms — min gap between animating the same container
  var last = new WeakMap();

  function looksCard(el) {
    return el && el.nodeType === 1 &&
      (el.classList.contains("rounded-xl") || el.classList.contains("card") || el.tagName === "TR");
  }
  function reveal(container) {
    if (!container || container.nodeType !== 1) return;
    var now = Date.now();
    if (last.get(container) && now - last.get(container) < THROTTLE) return;   // throttle bursts
    var kids = container.children, any = false;
    for (var i = 0; i < kids.length; i++) {
      var el = kids[i];
      if (el.nodeType !== 1) continue;
      any = true;
      el.style.animation = "vmms-fade-up .45s var(--vmms-ease) both";
      el.style.animationDelay = (Math.min(i, 12) * 0.04) + "s";
    }
    if (any) last.set(container, now);
  }

  function init() {
    // catch anything already on the page
    ["menu", "list", "cards", "sites", "rows"].forEach(function (id) {
      var c = document.getElementById(id); if (c && c.children.length) reveal(c);
    });
    // …and everything rendered later
    var mo = new MutationObserver(function (muts) {
      var seen = [];
      for (var j = 0; j < muts.length; j++) {
        var m = muts[j], added = m.addedNodes;
        if (!added || !added.length) continue;
        for (var k = 0; k < added.length; k++) {
          if (looksCard(added[k]) && seen.indexOf(m.target) === -1) { seen.push(m.target); reveal(m.target); break; }
        }
      }
    });
    mo.observe(document.body, { childList: true, subtree: true });
  }
  if (document.body) init(); else document.addEventListener("DOMContentLoaded", init);
})();

// ---- Download-as-PDF helper (works on iPhone, where window.print() is blocked) ----
// Lazy-loads html2pdf.js on first use, then renders one DOM element to an A4 PDF.
// Usage: vmmsDownloadPdf("sheet", "VMMS_Timesheet_July_2026", { landscape: true })
(function () {
  // When capturing a whole page we mirror the print CSS: hide .no-print, show .print-only.
  var s = document.createElement("style");
  s.textContent = "body.vmms-pdf .no-print{display:none!important}" +
                  "body.vmms-pdf .print-only{display:block!important}" +
                  ".pdfing{box-shadow:none!important;border:none!important}" +
                  // During capture, kill entrance animations — html2canvas clones the
                  // page and restarts them from their invisible (opacity 0) start frame,
                  // which made animated tiles / rows come out blank in the PDF.
                  "body.vmms-pdf *,.pdfing,.pdfing *{animation:none!important;opacity:1!important;transform:none!important}";
  (document.head || document.documentElement).appendChild(s);
})();
// Load one or more <script>s in order, then call cb. Skips any already added.
function vmmsLoadScripts(urls, cb) {
  var i = 0;
  (function next() {
    if (i >= urls.length) { cb(); return; }
    var url = urls[i++];
    if (document.querySelector('script[data-vmms="' + url + '"]')) { next(); return; }
    var s = document.createElement("script");
    s.src = url; s.dataset.vmms = url;
    s.onload = next;
    s.onerror = function () { cb(); };   // proceed anyway; caller checks the globals
    document.head.appendChild(s);
  })();
}
window.vmmsDownloadPdf = function (elementId, filename, opts) {
  opts = opts || {};
  // elementId may be an id, or "body"/null for a full-page capture
  var full = !elementId || elementId === "body";
  var el = full ? document.body : document.getElementById(elementId);
  if (!el) { alert("Nothing to export yet."); return; }

  function run() {
    var prevBtn = document.activeElement;
    if (prevBtn && prevBtn.tagName === "BUTTON") { prevBtn.dataset._t = prevBtn.textContent; prevBtn.textContent = "Preparing PDF…"; prevBtn.disabled = true; }
    if (full) document.body.classList.add("vmms-pdf");
    el.classList.add("pdfing");
    function done() {
      el.classList.remove("pdfing");
      document.body.classList.remove("vmms-pdf");
      if (prevBtn && prevBtn.dataset._t) { prevBtn.textContent = prevBtn.dataset._t; prevBtn.disabled = false; }
      if (typeof opts.onDone === "function") { try { opts.onDone(); } catch (e) {} }
    }
    function fail() { done(); alert("Could not build the PDF. Please try Print / PDF instead."); }
    var margin = opts.landscape ? 6 : 8;
    var orient = opts.landscape ? "landscape" : "portrait";

    // "Fit to one page": capture once, then scale the whole image onto a single A4 page.
    function captureOnePage() {
      setTimeout(function () {
        window.html2canvas(el, { scale: 2, useCORS: true, backgroundColor: "#ffffff",
          windowWidth: Math.max(el.scrollWidth, document.documentElement.clientWidth) })
        .then(function (canvas) {
          var jsPDF = window.jspdf.jsPDF;
          var pdf = new jsPDF({ unit: "mm", format: "a4", orientation: orient });
          var pw = pdf.internal.pageSize.getWidth(), ph = pdf.internal.pageSize.getHeight();
          var availW = pw - 2 * margin, availH = ph - 2 * margin;
          var ratio = Math.min(availW / canvas.width, availH / canvas.height);
          var w = canvas.width * ratio, h = canvas.height * ratio;
          pdf.addImage(canvas.toDataURL("image/jpeg", 0.96), "JPEG", (pw - w) / 2, margin, w, h);
          pdf.save((filename || "VMMS_export") + ".pdf");
          done();
        }).catch(fail);
      }, 60);
    }
    // Guarantee ONE page: html2pdf's bundle doesn't always expose the standalone
    // libs, which made this silently fall through to the multi-page path. Load
    // them explicitly, then capture and scale onto a single A4 sheet.
    if (opts.onePage) {
      vmmsLoadScripts([
        "https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"
      ], function () {
        if (window.html2canvas && window.jspdf) captureOnePage();
        else fail();
      });
      return;
    }

    window.html2pdf().set({
      margin: margin,
      filename: (filename || "VMMS_export") + ".pdf",
      image: { type: "jpeg", quality: 0.96 },
      html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff",
                     windowWidth: Math.max(el.scrollWidth, document.documentElement.clientWidth) },
      jsPDF: { unit: "mm", format: "a4", orientation: orient },
      pagebreak: { mode: ["css", "legacy"] }
    }).from(el).save().then(done).catch(fail);
  }

  if (window.html2pdf) { run(); return; }
  var s = document.createElement("script");
  s.src = "https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js";
  s.onload = run;
  s.onerror = function () { alert("Could not load the PDF tool (no internet?). Please try Print / PDF."); };
  document.head.appendChild(s);
};

// ---- Global floating "Home" button (every page except home / login) ----
// The small back arrow in the header is hard to tap on a phone, so we add a
// big, thumb-friendly circular Home button fixed at the bottom-right corner.
(function () {
  var page = (location.pathname.split("/").pop() || "").toLowerCase();
  var skip = ["", "home.html", "index.html", "login.html"];
  if (skip.indexOf(page) !== -1) return;

  function add() {
    if (document.getElementById("vmms-home-fab")) return;
    var a = document.createElement("a");
    a.id = "vmms-home-fab";
    a.href = "home.html";
    a.setAttribute("aria-label", "Home");
    a.title = "Home";
    a.innerHTML =
      '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24"' +
      ' fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"' +
      ' stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>' +
      '<path d="M9.5 21v-6h5v6"/></svg>';
    a.style.cssText =
      "position:fixed;right:16px;bottom:calc(84px + env(safe-area-inset-bottom));" +
      "z-index:9999;width:52px;height:52px;border-radius:9999px;" +
      "background:#C00000;color:#fff;display:flex;align-items:center;" +
      "justify-content:center;box-shadow:0 4px 12px rgba(0,0,0,.28);" +
      "text-decoration:none;-webkit-tap-highlight-color:transparent;";
    // hide when printing
    a.classList.add("no-print");
    document.body.appendChild(a);
  }
  if (document.body) add();
  else document.addEventListener("DOMContentLoaded", add);
})();

/* ---- Notification bell (global, top-right) ---- */
(function () {
  function ready(fn){ if(document.readyState!=='loading') fn(); else document.addEventListener('DOMContentLoaded', fn); }
  ready(function () {
    if (typeof getSession !== 'function' || !getSession()) return;   // signed-in pages only
    if (typeof vmmsApi !== 'function') return;
    if (document.getElementById('vmms-bell')) return;
    var esc = window.esc || function(v){return String(v==null?'':v);};

    var btn = document.createElement('button');
    btn.id = 'vmms-bell'; btn.className = 'no-print'; btn.setAttribute('aria-label','Notifications');
    btn.style.cssText = 'position:fixed;top:9px;right:12px;z-index:10000;width:40px;height:40px;border-radius:9999px;background:#fff;color:#C00000;border:none;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.25);cursor:pointer;-webkit-tap-highlight-color:transparent;';
    btn.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg><span id="vmms-bell-badge" style="position:absolute;top:-3px;right:-3px;min-width:18px;height:18px;padding:0 4px;border-radius:9999px;background:#C00000;color:#fff;font:700 11px/18px system-ui,sans-serif;text-align:center;display:none;"></span>';

    var panel = document.createElement('div');
    panel.id = 'vmms-bell-panel'; panel.className = 'no-print';
    panel.style.cssText = 'position:fixed;top:56px;right:10px;z-index:10000;width:340px;max-width:92vw;max-height:72vh;overflow:auto;background:#fff;border:1px solid #e5e7eb;border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,.22);display:none;';
    panel.innerHTML = '<div style="position:sticky;top:0;background:#fff;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px 14px;border-bottom:1px solid #f0f0f0;"><span style="font:700 14px system-ui,sans-serif;color:#111;">Notifications</span><span><button id="vmms-bell-read" style="font:700 11px system-ui;color:#C00000;background:none;border:none;cursor:pointer;">Mark all read</button><button id="vmms-bell-clear" style="font:700 11px system-ui;color:#666;background:none;border:none;cursor:pointer;margin-left:10px;">Clear</button></span></div><div id="vmms-bell-list"></div>';

    document.body.appendChild(btn); document.body.appendChild(panel);

    function fmt(ts){ try{ var d=new Date(ts),diff=(Date.now()-d)/1000; if(diff<60)return 'just now'; if(diff<3600)return Math.floor(diff/60)+'m ago'; if(diff<86400)return Math.floor(diff/3600)+'h ago'; return d.toLocaleDateString('en-GB'); }catch(e){return '';} }
    function render(data){
      var items=(data&&data.items)||[], unread=(data&&data.unread)||0;
      var badge=document.getElementById('vmms-bell-badge');
      if(unread>0){ badge.textContent=unread>99?'99+':unread; badge.style.display='block'; } else badge.style.display='none';
      var list=document.getElementById('vmms-bell-list');
      if(!items.length){ list.innerHTML='<div style="padding:22px 14px;color:#9ca3af;font:500 13px system-ui;text-align:center;">No notifications</div>'; return; }
      list.innerHTML=items.map(function(n){
        var dot=n.read_at?'<span style="flex:none;width:8px;"></span>':'<span style="flex:none;width:8px;height:8px;border-radius:9999px;background:#C00000;margin-top:5px;"></span>';
        return '<div data-link="'+(n.link||'')+'" style="display:flex;gap:9px;padding:11px 14px;border-bottom:1px solid #f4f4f4;'+(n.link?'cursor:pointer;':'')+(n.read_at?'':'background:#fff7f7;')+'">'+dot+
          '<div style="min-width:0;"><p style="font:700 13px system-ui;color:#111;margin:0;">'+esc(n.title)+'</p>'+
          (n.body?'<p style="font:500 12px system-ui;color:#555;margin:2px 0 0;">'+esc(n.body)+'</p>':'')+
          '<p style="font:500 11px system-ui;color:#9ca3af;margin:3px 0 0;">'+fmt(n.created_at)+'</p></div></div>';
      }).join('');
      list.querySelectorAll('[data-link]').forEach(function(el){ var lnk=el.getAttribute('data-link'); if(lnk) el.addEventListener('click', function(){ window.location.href=lnk; }); });
    }
    async function load(){ try{ var r=await vmmsApi('/api/v1/notifications'); if(!r.ok) return; render(await r.json()); }catch(e){} }

    btn.addEventListener('click', function(){ var open=panel.style.display==='block'; panel.style.display=open?'none':'block'; if(!open) load(); });
    document.addEventListener('click', function(e){ if(panel.style.display==='block' && !panel.contains(e.target) && !btn.contains(e.target)) panel.style.display='none'; });
    document.getElementById('vmms-bell-read').addEventListener('click', async function(e){ e.stopPropagation(); try{ await vmmsApi('/api/v1/notifications/read_all',{method:'POST'}); }catch(_){} load(); });
    document.getElementById('vmms-bell-clear').addEventListener('click', async function(e){ e.stopPropagation(); if(!confirm('Clear all notifications?'))return; try{ await vmmsApi('/api/v1/notifications',{method:'DELETE'}); }catch(_){} load(); });

    load(); setInterval(load, 60000);
  });
})();

// ---- Web Push (phone notifications) ----
function _vmmsB64ToU8(b64) {
  var pad = '='.repeat((4 - b64.length % 4) % 4);
  var s = (b64 + pad).replace(/-/g, '+').replace(/_/g, '/');
  var raw = atob(s), arr = new Uint8Array(raw.length);
  for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}
window.vmmsPushSupported = function () {
  return ('serviceWorker' in navigator) && ('PushManager' in window) && ('Notification' in window);
};
window.vmmsPushStatus = async function () {
  if (!vmmsPushSupported()) return 'unsupported';
  if (Notification.permission === 'denied') return 'blocked';
  try {
    var reg = await navigator.serviceWorker.ready;
    var s = await reg.pushManager.getSubscription();
    return s ? 'on' : 'off';
  } catch (e) { return 'off'; }
};
// Call from a user click. Returns {ok:true} or {ok:false, reason:'...'}.
window.vmmsEnablePush = async function () {
  try {
    if (!vmmsPushSupported()) return { ok: false, reason: 'unsupported' };
    var perm = await Notification.requestPermission();
    if (perm !== 'granted') return { ok: false, reason: 'denied' };
    var reg = await navigator.serviceWorker.ready;
    var pk = await vmmsApi('/api/v1/push/pubkey');
    var cfg = pk.ok ? await pk.json() : {};
    if (!cfg.enabled || !cfg.public_key) return { ok: false, reason: 'server_off' };
    var sub = await reg.pushManager.getSubscription();
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: _vmmsB64ToU8(cfg.public_key) });
    var j = sub.toJSON();
    var r = await vmmsApi('/api/v1/push/subscribe', { method: 'POST', body: JSON.stringify({ endpoint: sub.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth, user_agent: navigator.userAgent }) });
    if (!r.ok) return { ok: false, reason: 'save_failed' };
    return { ok: true };
  } catch (e) { return { ok: false, reason: String(e && e.message || e) }; }
};
window.vmmsDisablePush = async function () {
  try {
    var reg = await navigator.serviceWorker.ready;
    var sub = await reg.pushManager.getSubscription();
    if (sub) { try { await vmmsApi('/api/v1/push/unsubscribe', { method: 'POST', body: JSON.stringify({ endpoint: sub.endpoint }) }); } catch (_) {} await sub.unsubscribe(); }
    return { ok: true };
  } catch (e) { return { ok: false }; }
};
window.vmmsTestPush = async function () { try { await vmmsApi('/api/v1/push/test', { method: 'POST' }); return true; } catch (e) { return false; } };

// Consistent premium KPI interaction on desktop dashboards. Mobile is unchanged.
(function(){
  var s=document.createElement('style');
  s.id='vmms-kpi-motion';
  s.textContent='@media(min-width:900px){.kpi,.stat{transition:transform .18s cubic-bezier(.2,.8,.2,1),box-shadow .18s ease,border-color .18s ease!important;will-change:transform}.kpi:hover,.stat:hover{transform:translateY(-5px) scale(1.012)!important;box-shadow:0 14px 30px rgba(16,24,40,.15)!important;border-color:rgba(185,28,28,.38)!important}.kpi:active,.stat:active{transform:translateY(-2px) scale(1.005)!important}}@media(prefers-reduced-motion:reduce){.kpi,.stat{transition:none!important}.kpi:hover,.stat:hover{transform:none!important}}';
  document.head.appendChild(s);
})();
