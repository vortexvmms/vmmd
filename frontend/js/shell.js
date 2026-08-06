/* VCMS app shell — injects a left navigation rail on desktop for every signed-in
   page. Non-destructive: it doesn't touch the page's own header/content, it just
   fixes a sidebar on the left and shifts the body right on wide screens. Pages that
   already carry the shell (the home page) are skipped. Mobile is left unchanged. */
(function () {
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  ready(async function () {
    try {
      var file = (location.pathname.split("/").pop() || "").toLowerCase();
      if (file === "login.html" || file === "index.html" || file === "") return;
      if (document.body.classList.contains("shell")) return;        // home already has the shell
      if (document.getElementById("vcms-rail")) return;
      if (typeof getSession !== "function" || !getSession()) return; // signed-in pages only

      var me = null;
      try { var r = await vmmsApi("/api/v1/me"); if (r.ok) me = await r.json(); } catch (e) {}
      var role = (me && me.role) || "admin";

      var TIER = { admin:"full", general_manager:"full", operation_manager:"full", hr_assistant:"full",
        main_sup:"manager", wshc_lead:"manager", site_sup:"supervisor", safety_sup:"supervisor",
        wshc:"supervisor", logistics_sup:"supervisor", payroll:"payroll" };
      var ALLOW = {
        full: null,
        manager: new Set(["home.html","request.html","attendance.html","verify.html","dpr.html","dprlist.html","resource-summary.html","site-dashboard.html","pr-directory.html","pr-new.html","pr-dashboard.html","whatsapp.html","dashboard.html","reports.html","timesheet.html","settings.html","help.html"]),
        supervisor: new Set(["home.html","request.html","attendance.html","dpr.html","dprlist.html","pr-new.html","whatsapp.html","dashboard.html","reports.html","settings.html","help.html"]),
        payroll: new Set(["home.html","verify.html","reports.html","timesheet.html","manhours.html","settings.html","help.html"]),
      };
      var allow = ALLOW[TIER[role] || "full"];
      var ok = function (href) { return !allow || allow.has(href); };

      var NAV = [
        { items: [["Home","home.html","home"]] },
        { grp:"Manpower", items:[["Workers","workers.html","user"],["Sites","sites.html","bld"],["Allocation","allocation.html","cal"],["Attendance","attendance.html","chk"],["End-time","verify.html","clk"],["Timesheet","timesheet.html","grid"],["Dashboard","dashboard.html","chart"]] },
        { grp:"Site progress", items:[["Daily report","dpr.html","doc"],["DPR history","dprlist.html","list"],["Resource summary","resource-summary.html","grid"],["Site board","site-dashboard.html","chart"],["Reports","reports.html","doc"]] },
        { grp:"Procurement", items:[["PR directory","pr-directory.html","list"],["New PR","pr-new.html","cart"],["PR board","pr-dashboard.html","chart"]] },
        { grp:"More", items:[["WhatsApp","whatsapp.html","chat"],["Users","users.html","shield"],["Settings","settings.html","gear"],["How to use","help.html","help"]] },
      ];
      var IC = {
        home:'<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>', user:'<circle cx="9" cy="8" r="3"/><path d="M3.5 20c0-3 2.5-5 5.5-5s5.5 2 5.5 5"/>',
        bld:'<path d="M4 20V6l6-2 6 2v14M3 20h18"/>', cal:'<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 9.5h16M8.5 3v4M15.5 3v4"/>',
        chk:'<circle cx="12" cy="12" r="8.5"/><path d="M8 12.5l2.5 2.5L16 9.5"/>', clk:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
        grid:'<rect x="3.5" y="4.5" width="17" height="15" rx="1.5"/><path d="M3.5 9h17M9 9v10.5M14.5 9v10.5"/>', doc:'<path d="M7 3.5h8l3.5 3.5V20.5H7z"/><path d="M9.5 12h5M9.5 15h5"/>',
        list:'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 12.5h8M8 16h5"/>', chart:'<path d="M5 20V11M10 20V5M15 20v-8M20 20v-5"/>',
        cart:'<path d="M6 6h13l-1.5 8H8z"/><circle cx="9" cy="19" r="1.3"/><circle cx="16" cy="19" r="1.3"/>', chat:'<path d="M20 12a8 8 0 01-11.6 7.1L4 20l.9-4.3A8 8 0 1120 12z"/>',
        shield:'<path d="M12 3.5l7 2.8v5.2c0 4.2-3 7-7 8.5-4-1.5-7-4.3-7-8.5V6.3z"/>', gear:'<circle cx="12" cy="12" r="3"/><path d="M12 4v2.5M12 17.5V20M4 12h2.5M17.5 12H20"/>',
        help:'<circle cx="12" cy="12" r="8.5"/><path d="M9.7 9.2a2.4 2.4 0 114.3 1.5c-.8.9-1.8 1.1-1.8 2.5"/><path d="M12 16.4h.01"/>',
      };
      var esc = window.esc || function (v) { return String(v == null ? "" : v); };

      var css =
        "#vcms-rail{position:fixed;left:0;top:0;height:100vh;width:210px;background:#fff;border-right:1px solid #E7E5E1;display:flex;flex-direction:column;z-index:40;font-family:Arial,system-ui,sans-serif;}" +
        "#vcms-rail .rb{display:flex;align-items:center;gap:9px;padding:13px 14px 11px;}" +
        "#vcms-rail .rb .lg{width:34px;height:34px;border-radius:9px;background:#C00000;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:16px;overflow:hidden;flex:none;}" +
        "#vcms-rail .rb .lg img{width:100%;height:100%;object-fit:contain;background:#fff;}" +
        "#vcms-rail .rb .t{font-weight:800;font-size:16px;line-height:1;}#vcms-rail .rb .s{font-size:10px;color:#6B7280;line-height:1.2;margin-top:2px;}" +
        "#vcms-rail .rn{flex:1;overflow:auto;padding:4px 8px 16px;}" +
        "#vcms-rail .grp{font-size:10.5px;font-weight:700;color:#9A968E;letter-spacing:.06em;text-transform:uppercase;padding:12px 8px 5px;}" +
        "#vcms-rail a{display:flex;align-items:center;gap:10px;padding:8px 9px;border-radius:9px;color:#3A3D42;font-size:13.5px;text-decoration:none;margin:1px 0;transition:transform .14s,box-shadow .14s,background .14s;}" +
        "#vcms-rail a:hover{background:#fff;transform:translateX(3px);box-shadow:0 4px 12px rgba(0,0,0,.08);}" +
        "#vcms-rail a.on{background:#FDE8E8;color:#C00000;font-weight:700;}#vcms-rail a.on:hover{background:#FBDCDC;}" +
        "#vcms-rail a svg{width:18px;height:18px;flex:none;}" +
        "@media(min-width:900px){body.vcms-shelled{margin-left:210px;}}" +
        "@media(max-width:899px){#vcms-rail{display:none;}}";
      var st = document.createElement("style"); st.id = "vcms-rail-css"; st.textContent = css;
      document.head.appendChild(st);

      var navHTML = NAV.map(function (sec) {
        var items = sec.items.filter(function (it) { return ok(it[1]); });
        if (!items.length) return "";
        return (sec.grp ? '<div class="grp">' + sec.grp + "</div>" : "") +
          items.map(function (it) {
            var on = it[1] === file ? " on" : "";
            return '<a href="' + it[1] + '" class="' + on.trim() + '"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + (IC[it[2]] || IC.home) + "</svg>" + esc(it[0]) + "</a>";
          }).join("");
      }).join("");

      var rail = document.createElement("aside");
      rail.id = "vcms-rail";
      rail.innerHTML =
        '<a class="rb" href="home.html" style="text-decoration:none;color:inherit"><span class="lg"><img src="icons/icon-192.png" onerror="this.parentNode.textContent=\'V\'"></span>' +
        '<span><span class="t" style="display:block">VCMS</span><span class="s">Vortex Construction Management System</span></span></a>' +
        '<nav class="rn">' + navHTML + "</nav>";
      document.body.appendChild(rail);
      document.body.classList.add("vcms-shelled");
    } catch (e) { /* never break the page */ }
  });
})();
