// ---- HTML escaper (XSS hardening) ----
// Wrap any user-entered value (worker/site/supervisor names, codes, notes)
// before putting it into innerHTML, so a name containing markup can't run.
window.esc = function (v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
};

// VMMS configuration
window.VMMS_CONFIG = {
  BACKEND_URL: "https://vmms-backend-7j1v.onrender.com",
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
                  ".pdfing{box-shadow:none!important;border:none!important}";
  (document.head || document.documentElement).appendChild(s);
})();
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
    }
    function fail() { done(); alert("Could not build the PDF. Please try Print / PDF instead."); }
    var margin = opts.landscape ? 6 : 8;
    var orient = opts.landscape ? "landscape" : "portrait";

    // "Fit to one page": capture once, then scale the whole image onto a single A4 page.
    if (opts.onePage && window.html2canvas && window.jspdf) {
      // let the browser paint the print-only header before capture
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
