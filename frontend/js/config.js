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
