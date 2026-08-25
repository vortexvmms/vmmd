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

    /* iPhone home-indicator / browser toolbar clearance for fixed action bars. */
    @media(max-width:899px){
      html,body{max-width:100%;overflow-x:hidden}
      *,*::before,*::after{box-sizing:border-box}
      body{padding-bottom:env(safe-area-inset-bottom,0px)}
      /* One consistent mobile page header. Desktop shell and Home are untouched. */
      body:not(.shell)>header{
        width:100%!important;
        max-width:none!important;
        padding:12px 16px!important;
        min-height:0!important;
        border-radius:0!important;
        overflow:visible!important;
      }
      /* Headers whose title/filters are wrapped in rows: reserve bell space only
         on the title row, never on the Date/Site controls underneath. */
      body:not(.shell)>header>div{
        width:100%!important;
        max-width:none!important;
        margin-left:0!important;
        margin-right:0!important;
      }
      body:not(.shell)>header>div:first-child{
        min-height:40px!important;
        display:flex!important;
        align-items:center!important;
        gap:10px!important;
        padding-right:48px!important;
      }
      body:not(.shell)>header>div:first-child>a:first-child{
        flex:0 0 12px!important;
        width:12px!important;
        margin:0!important;
        padding:0!important;
        text-align:left!important;
      }
      body:not(.shell)>header>div:first-child>div{min-width:0!important}
      body:not(.shell)>header h1{
        margin:0!important;
        font-size:18px!important;
        line-height:1.2!important;
        white-space:nowrap!important;
        overflow:hidden!important;
        text-overflow:ellipsis!important;
      }
      body:not(.shell)>header p{margin-top:2px!important;line-height:1.25!important}
      body:not(.shell)>header>div:first-child>a:not(:first-child){
        margin:0!important;
        min-height:38px!important;
        display:inline-flex!important;
        align-items:center!important;
        justify-content:center!important;
        white-space:nowrap!important;
      }
      body:not(.shell)>header input[type=date],body:not(.shell)>header select{
        min-width:0!important;
        height:44px!important;
        min-height:44px!important;
        max-height:44px!important;
        box-sizing:border-box!important;
        padding-top:0!important;
        padding-bottom:0!important;
        line-height:42px!important;
        margin:0!important;
      }
      /* iOS Safari gives date controls a larger native intrinsic height unless
         the internal date-edit field is constrained as well. */
      body:not(.shell)>header input[type=date]{
        -webkit-appearance:none!important;
        appearance:none!important;
        padding-left:12px!important;
        padding-right:12px!important;
        border-radius:8px!important;
      }
      body:not(.shell)>header input[type=date]::-webkit-date-and-time-value{
        min-height:0!important;
        height:42px!important;
        line-height:42px!important;
        padding:0!important;
        margin:0!important;
        text-align:center!important;
      }
      body:not(.shell)>header button,
      body:not(.shell)>header a.mobile-title-action{
        height:44px!important;
        min-height:44px!important;
        padding-top:0!important;
        padding-bottom:0!important;
        display:inline-flex!important;
        align-items:center!important;
        justify-content:center!important;
        line-height:1!important;
        border-radius:8px!important;
      }
      body.vmms-page-request>header>div:nth-child(2),
      body.vmms-page-attendance>header>div:nth-child(2),
      body.vmms-page-dpr>header>div:nth-child(2){
        display:grid!important;
        grid-template-columns:minmax(0,1fr) minmax(0,1fr)!important;
        gap:8px!important;
      }
      body.vmms-page-request>header>div:nth-child(2)>*,
      body.vmms-page-attendance>header>div:nth-child(2)>*,
      body.vmms-page-dpr>header>div:nth-child(2)>*{width:100%!important;min-width:0!important}
      body.vmms-page-dpr .mobile-title-action{margin:0!important;padding-left:12px!important;padding-right:12px!important;font-size:13px!important}

      /* Dashboard: date selection and export actions must never compete for one
         narrow row. The action pair receives its own balanced row. */
      body.vmms-page-dashboard .mobile-header-controls{
        display:grid!important;
        grid-template-columns:minmax(0,1fr) auto!important;
        gap:8px!important;
      }
      body.vmms-page-dashboard .mobile-header-controls>#date{width:100%!important}
      body.vmms-page-dashboard .mobile-header-actions{
        grid-column:1/-1!important;
        display:grid!important;
        grid-template-columns:1fr 1fr!important;
        gap:8px!important;
        width:100%!important;
      }
      body.vmms-page-dashboard .mobile-header-actions button{width:100%!important;margin:0!important}
      /* Classic single-row headers have the back link/title directly inside. */
      body:not(.shell)>header>a:first-child{flex:0 0 12px!important;width:12px!important;margin:0!important}
      body:not(.shell)>header>a:first-child~div,body:not(.shell)>header>a:first-child~h1{min-width:0!important}
      body:not(.shell)>header:has(>a:first-child){padding-right:64px!important}

      /* Request's helper/copy tools were a desktop row on phones, squeezing the
         instruction into a few words per line. Stack it cleanly on mobile. */
      body.vmms-page-request main>div:first-child{
        display:flex!important;
        flex-direction:column!important;
        align-items:stretch!important;
        gap:10px!important;
      }
      body.vmms-page-request main>div:first-child>p{width:100%!important;margin:0!important;line-height:1.45!important}
      body.vmms-page-request main>div:first-child>div{width:100%!important;justify-content:flex-start!important;flex-wrap:nowrap!important}
      body.vmms-page-request #copyfrom{flex:1 1 auto!important;min-width:0!important}
      body.vmms-page-request #copylast{flex:0 0 auto!important}
      body>div.fixed.bottom-0,#actionbar,#dprbar{padding-bottom:calc(12px + env(safe-area-inset-bottom,0px))!important}
      #vmms-home-fab{bottom:calc(18px + env(safe-area-inset-bottom,0px))!important}
      body.vmms-page-attendance #vmms-home-fab,body.vmms-page-dpr #vmms-home-fab,body.vmms-page-workers #vmms-home-fab{display:none!important}
      body.vmms-page-workers #list>*{content-visibility:auto;contain-intrinsic-size:auto 96px}
      body.vmms-page-users input[type=checkbox]{width:22px!important;height:22px!important}
      body.vmms-page-users select,body.vmms-page-users button,body.vmms-page-settings button{min-height:40px}
      body.vmms-page-pr-dashboard .pbtn{min-height:40px;display:inline-flex;align-items:center;justify-content:center}
      /* Let Safari skip painting worker cards far outside the viewport. */
      body.vmms-page-attendance #list>*,body.vmms-page-request #list>*,body.vmms-page-allocation #list>*{
        content-visibility:auto;contain-intrinsic-size:auto 92px
      }
    }

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
    @media (min-width:900px){ #vmms-home-fab{ display:none !important; } }
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
  // Mobile operational pages update large card lists after almost every tap.
  // Re-animating those lists costs layout/paint time and makes fast saves feel
  // slow, so staggered list animation is desktop-only. The single page-opening
  // fade remains available on mobile.
  if (window.matchMedia && window.matchMedia("(max-width: 899px)").matches) return;
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

