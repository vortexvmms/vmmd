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

