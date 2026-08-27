// VCMS theme-ext — paints the saved custom-theme token bundle on EVERY page.
// Fully additive and gated: if no custom theme is saved, nothing is changed and
// no data-vcms-theme attribute is set, so untouched pages render exactly as before.
// Base 6 colours are still handled by core theme.js; this only adds the extra tokens.
(function () {
  "use strict";
  try {
    // Consuming CSS is scoped under html[data-vcms-theme=on] so it is inert until a
    // theme is actually applied. Non-matching selectors simply do nothing.
    if (!document.getElementById("vcms-theme-ext-css")) {
      var css = "@media screen{" +
        "html[data-vcms-theme=on] .vcms-btn{border-radius:var(--vcms-btn-radius,10px)}" +
        "html[data-vcms-theme=on] .vcms-control{border-radius:var(--vcms-input-radius,10px)}" +
        "html[data-vcms-theme=on] .settings-card,html[data-vcms-theme=on] .panel,html[data-vcms-theme=on] .vcms-section-card{border-radius:var(--vcms-card-radius,14px)}" +
        "html[data-vcms-theme=on] body{font-family:var(--vcms-font)}" +
        "html[data-vcms-theme=on] table thead th{background:var(--vcms-thead-bg);color:var(--vcms-thead-ink)}" +
        "html[data-vcms-theme=on] table tbody tr:nth-child(2n){background:var(--vcms-row-alt)}" +
        "html[data-vcms-theme=on] .side,html[data-vcms-theme=on] .app-rail,html[data-vcms-theme=on] nav.side,html[data-vcms-theme=on] #sidenav{background:var(--vcms-sidebar-bg)}" +
        "@media(prefers-reduced-motion:reduce){html[data-vcms-theme=on] *{animation:none!important;transition:none!important}}" +
        "}";
      var st = document.createElement("style"); st.id = "vcms-theme-ext-css"; st.textContent = css;
      (document.head || document.documentElement).appendChild(st);
    }

    var b = null;
    try { b = JSON.parse(localStorage.getItem("vcms_theme_bundle_v1") || "null"); } catch (_) {}
    if (!b || !b.themes || !b.active) return;
    var t = b.themes[b.active]; if (!t || !t.colors) return;

    var C = t.colors, S = t.shapes || {}, T = t.type || {}, A = t.anim || {}, rs = document.documentElement.style;
    function H(v) { return /^#[0-9A-Fa-f]{6}$/.test(v); }
    function ci(v, lo, hi) { v = parseInt(v, 10); if (isNaN(v)) return lo; return Math.max(lo, Math.min(hi, v)); }
    function Rgb(x) { x = x.slice(1); return [0, 2, 4].map(function (i) { return parseInt(x.substr(i, 2), 16); }); }
    function Mix(h, tg, w) { var a = Rgb(h), bb = Rgb(tg); return "#" + a.map(function (v, i) { return Math.round(v + (bb[i] - v) * w).toString(16).padStart(2, "0"); }).join(""); }
    function s(k, v) { if (v) rs.setProperty(k, v); }

    ["ink", "muted", "line", "surface", "page", "secondary", "accent"].forEach(function (k) { if (H(C[k])) s("--vcms-" + k, C[k]); });
    if (H(C.success)) { s("--vcms-success", C.success); s("--vcms-success-soft", Mix(C.success, "#FFFFFF", 0.88)); }
    if (H(C.warning)) { s("--vcms-warning", C.warning); s("--vcms-warning-soft", Mix(C.warning, "#FFFFFF", 0.88)); }
    if (H(C.danger)) { s("--vcms-danger", C.danger); s("--vcms-danger-soft", Mix(C.danger, "#FFFFFF", 0.90)); }
    if (H(C.info)) { s("--vcms-info", C.info); s("--vcms-info-soft", Mix(C.info, "#FFFFFF", 0.90)); }
    if (H(C.heading)) s("--vcms-heading", C.heading);
    if (H(C.sidebar)) s("--vcms-sidebar-bg", C.sidebar);
    if (H(C.sidebarInk)) s("--vcms-sidebar-ink", C.sidebarInk);
    if (H(C.thead)) s("--vcms-thead-bg", C.thead);
    if (H(C.theadInk)) s("--vcms-thead-ink", C.theadInk);
    if (H(C.rowAlt)) s("--vcms-row-alt", C.rowAlt);
    if (H(C.brand) && H(C.sidebar)) s("--vcms-sidebar-active", Mix(C.brand, C.sidebar, 0.35));

    s("--vcms-card-radius", ci(S.cardRadius, 0, 28) + "px");
    s("--vcms-btn-radius", ci(S.btnRadius, 0, 22) + "px");
    s("--vcms-input-radius", ci(S.inputRadius, 0, 22) + "px");
    s("--vcms-modal-radius", ci(S.modalRadius, 0, 28) + "px");
    s("--vcms-border-w", ci(S.borderW, 0, 3) + "px");
    s("--vcms-radius", ci(S.cardRadius, 0, 28) + "px");
    var D = ({ compact: ["42px", "12px"], standard: ["46px", "16px"], spacious: ["52px", "22px"] })[S.density || "standard"] || ["46px", "16px"];
    s("--vcms-control-h", D[0]); s("--vcms-pad", D[1]);
    var F = ({ system: "system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif", arial: "Arial,Helvetica,sans-serif", arialnarrow: "'Arial Narrow',Arial,sans-serif", inter: "Inter,system-ui,Arial,sans-serif", georgia: "Georgia,'Times New Roman',serif", mono: "ui-monospace,Menlo,monospace" })[T.font];
    if (F) s("--vcms-font", F);
    s("--vcms-fs-h", ci(T.fsH, 16, 26) + "px");
    var AL = { none: 0, subtle: 0.6, standard: 1, smooth: 1.35 };
    s("--vcms-anim", (A.level in AL) ? AL[A.level] : 1);
    s("--vcms-tspeed", ci(A.tspeed, 120, 400) + "ms");
    document.documentElement.setAttribute("data-anim", A.level || "standard");

    document.documentElement.setAttribute("data-vcms-theme", "on");
  } catch (e) { /* never break a page over theming */ }
})();
