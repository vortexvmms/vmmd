// ---- Global floating "Home" button (every page except home / login) ----
// The small back arrow in the header is hard to tap on a phone, so we add a
// big, thumb-friendly circular Home button fixed at the bottom-right corner.
(function () {
  var page = (location.pathname.split("/").pop() || "").toLowerCase();
  var skip = ["", "home.html", "index.html", "login.html"];
  if (skip.indexOf(page) !== -1) return;

  function add() {
    if (document.getElementById("vmms-home-fab")) return;
    /* Do not cover a page's own mobile save/add controls. The header back
       arrow remains the route back to Home on these workflow pages. */
    if (document.querySelector("body > div.fixed.bottom-0, #actionbar, #dprbar, #fab, #fab-bulk")) return;
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

/* Notifications and Web Push were retired in August 2026. */

// Consistent premium KPI interaction on desktop dashboards. Mobile is unchanged.
(function(){
  var s=document.createElement('style');
  s.id='vmms-kpi-motion';
  s.textContent='@media(min-width:900px){.kpi,.stat{transition:transform .18s cubic-bezier(.2,.8,.2,1),box-shadow .18s ease,border-color .18s ease!important;will-change:transform}.kpi:hover,.stat:hover{transform:translateY(-5px) scale(1.012)!important;box-shadow:0 14px 30px rgba(16,24,40,.15)!important;border-color:rgba(185,28,28,.38)!important}.kpi:active,.stat:active{transform:translateY(-2px) scale(1.005)!important}}@media(prefers-reduced-motion:reduce){.kpi,.stat{transition:none!important}.kpi:hover,.stat:hover{transform:none!important}}';
  document.head.appendChild(s);
})();
