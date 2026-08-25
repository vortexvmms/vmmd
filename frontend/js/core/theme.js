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
    ':root[data-theme="dark"] .soon-note,:root[data-theme="dark"] .sect.soon .sect-h .t{color:#6b7280 !important;}';
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

