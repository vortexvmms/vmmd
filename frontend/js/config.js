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
