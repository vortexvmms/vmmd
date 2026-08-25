// ---- HTML escaper (XSS hardening) ----
// Wrap any user-entered value (worker/site/supervisor names, codes, notes)
// before putting it into innerHTML, so a name containing markup can't run.
window.esc = function (v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
};

