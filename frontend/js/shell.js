/* VCMS shared desktop application shell.
   One header, one navigation rail and one collapse model are used by every
   signed-in desktop page, including Home. Phone layouts remain page-native. */
(function () {
  "use strict";
  if (window.__VCMS_SHELL_LOADING__) return;
  window.__VCMS_SHELL_LOADING__ = true;
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn, { once: true }); }
  function safeText(value) { return String(value == null ? "" : value); }
  function fileName() { return (location.pathname.split("/").pop() || "home.html").toLowerCase(); }
  function greeting() { var h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; }
  ready(async function () {
    try {
      var file = fileName();
      if (file === "login.html" || file === "index.html" || file === "") return;
      if (window.matchMedia && window.matchMedia("(max-width:899px)").matches) return;
      if (document.getElementById("vcms-app-header")) return;
      if (typeof getSession !== "function" || !getSession()) return;
      var me = null;
      try { var response = await vmmsApi("/api/v1/me"); if (response.ok) me = await response.json(); } catch (_) {}
      if (!me) return;
      var role = me.role || "admin";
      var ROLE_LABELS = {admin:"Administrator",general_manager:"General Manager",operation_manager:"Operation Manager",hr_assistant:"HR Assistant",main_sup:"Site Manager",wshc_lead:"WSHC Lead",site_sup:"Site Supervisor",safety_sup:"Safety Supervisor",wshc:"WSHC",logistics_sup:"Logistics Supervisor",payroll:"Payroll"};
      var TIER = {admin:"full",general_manager:"full",operation_manager:"full",hr_assistant:"full",main_sup:"manager",wshc_lead:"manager",site_sup:"supervisor",safety_sup:"supervisor",wshc:"supervisor",logistics_sup:"supervisor",payroll:"payroll"};
      var ALLOW = {
        full:null,
        manager:new Set(["home.html","todo.html","request.html","attendance.html","verify.html","dpr.html","dprlist.html","dpr-projects.html","camera.html","camera-settings.html","camera-photos.html","resource-summary.html","site-dashboard.html","pr-directory.html","pr-new.html","pr-dashboard.html","whatsapp.html","dashboard.html","timesheet.html","settings.html","help.html"]),
        supervisor:new Set(["home.html","todo.html","request.html","attendance.html","dpr.html","dprlist.html","camera.html","camera-photos.html","pr-new.html","whatsapp.html","dashboard.html","settings.html","help.html"]),
        payroll:new Set(["home.html","todo.html","verify.html","timesheet.html","manhours.html","settings.html","help.html"])
      };
      var ICONS = {
        home:'<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',check:'<circle cx="12" cy="12" r="8.5"/><path d="M8 12.5l2.5 2.5L16 9.5"/>',
        user:'<circle cx="9" cy="8" r="3"/><path d="M3.5 20c0-3 2.5-5 5.5-5s5.5 2 5.5 5"/>',building:'<path d="M4 20V6l6-2 6 2v14M3 20h18"/>',
        calendar:'<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 9.5h16M8.5 3v4M15.5 3v4"/>',clock:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
        grid:'<rect x="3.5" y="4.5" width="17" height="15" rx="1.5"/><path d="M3.5 9h17M9 9v10.5M14.5 9v10.5"/>',document:'<path d="M7 3.5h8l3.5 3.5V20.5H7z"/><path d="M9.5 12h5M9.5 15h5"/>',
        list:'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 12.5h8M8 16h5"/>',chart:'<path d="M5 20V11M10 20V5M15 20v-8M20 20v-5"/>',
        cart:'<path d="M6 6h13l-1.5 8H8z"/><circle cx="9" cy="19" r="1.3"/><circle cx="16" cy="19" r="1.3"/>',chat:'<path d="M20 12a8 8 0 01-11.6 7.1L4 20l.9-4.3A8 8 0 1120 12z"/>',
        shield:'<path d="M12 3.5l7 2.8v5.2c0 4.2-3 7-7 8.5-4-1.5-7-4.3-7-8.5V6.3z"/>',gear:'<circle cx="12" cy="12" r="3"/><path d="M12 4v2.5M12 17.5V20M4 12h2.5M17.5 12H20"/>',
        help:'<circle cx="12" cy="12" r="8.5"/><path d="M9.7 9.2a2.4 2.4 0 114.3 1.5c-.8.9-1.8 1.1-1.8 2.5"/><path d="M12 16.4h.01"/>'
      };
      function navFor(viewRole) {
        var tier = TIER[viewRole] || "full";
        if (tier === "supervisor") return [
          {items:[["Home","home.html","home"],["To-do","todo.html","check"]]},
          {group:"Daily",items:[["Request manpower","request.html","calendar"],["Attendance","attendance.html","check"],["WhatsApp","whatsapp.html","chat"]]},
          {group:"Site progress",items:[["VCMS Camera","camera.html","chart"],["Daily report","dpr.html","document"],["DPR history","dprlist.html","list"],["Dashboard","dashboard.html","chart"]]},
          {group:"Procurement",items:[["New PR","pr-new.html","cart"]]},
          {group:"More",items:[["Settings","settings.html","gear"],["How to use","help.html","help"]]}
        ];
        var sections = [
          {items:[["Home","home.html","home"],["To-do","todo.html","check"]]},
          {group:"Manpower",items:[["Workers","workers.html","user"],["Sites","sites.html","building"],["Allocation","allocation.html","calendar"],["Attendance","attendance.html","check"],["End-time","verify.html","clock"],["Timesheet","timesheet.html","grid"],["Dashboard","dashboard.html","chart"]]},
          {group:"Site progress",items:[["VCMS Camera","camera.html","chart"],["Project directory","dpr-projects.html","building"],["Daily report","dpr.html","document"],["DPR history","dprlist.html","list"],["Resource summary","resource-summary.html","grid"],["Site board","site-dashboard.html","chart"]]},
          {group:"Procurement",items:[["PR directory","pr-directory.html","list"],["New PR","pr-new.html","cart"],["PR board","pr-dashboard.html","chart"]]},
          {group:"More",items:[["WhatsApp","whatsapp.html","chat"],["Settings","settings.html","gear"],["How to use","help.html","help"]]}
        ];
        if (viewRole === "admin") {
          sections.splice(2,0,{group:"Planning",items:[["Programme","planning.html","calendar"]]});
          sections.splice(sections.length-1,0,{group:"Admin",items:[["Users","users.html","shield"],["Audit log","audit-log.html","list"]]});
        }
        var allowed = ALLOW[tier];
        sections = sections.map(function (section) { return {group:section.group,items:section.items.filter(function (item) { return !allowed || allowed.has(item[1]); })}; }).filter(function (section) { return section.items.length; });
        if (viewRole === "admin" || tier === "manager") {
          var manpower = sections.find(function (section) { return section.group === "Manpower"; });
          if (manpower && !manpower.items.some(function (item) { return item[1] === "request.html"; })) manpower.items.unshift(["Request manpower","request.html","calendar"]);
        }
        return sections;
      }
      var appHeader = document.createElement("header");
      appHeader.id = "vcms-app-header";
      appHeader.innerHTML = '<a class="vcms-app-brand" href="home.html" aria-label="VCMS Home"><img src="https://www.vortex.sg/images/Vortex-Logo_Type.png" alt="Vortex" onerror="this.style.display=\'none\'"><strong>VCMS</strong></a><div class="vcms-app-title">Vortex Construction Management System</div><div class="vcms-user-card"><div><strong id="vcms-greeting"></strong><small id="vcms-user-name"></small></div><span id="vcms-role-chip"></span></div>' + (role === "admin" ? '<select id="vcms-view-role" aria-label="Acting role"></select>' : "") + '<button class="vcms-app-logout" type="button">Log Out</button>';
      document.body.insertBefore(appHeader, document.body.firstChild);
      document.getElementById("vcms-greeting").textContent = greeting();
      document.getElementById("vcms-user-name").textContent = safeText(me.name);
      document.getElementById("vcms-role-chip").textContent = ROLE_LABELS[role] || role;
      appHeader.querySelector(".vcms-app-logout").addEventListener("click", function () { vmmsLogout(); });
      var rail = document.createElement("aside");
      rail.id = "vcms-app-rail";
      rail.innerHTML = '<div class="vcms-rail-tools"><button id="vcms-rail-toggle" type="button" aria-label="Collapse sidebar" title="Collapse sidebar">‹</button></div><nav id="vcms-app-nav"></nav>';
      document.body.appendChild(rail);
      var navNode = document.getElementById("vcms-app-nav");
      function renderNav(viewRole) {
        var saved = {}; try { saved = JSON.parse(localStorage.getItem("vcms_nav_groups") || "{}"); } catch (_) {}
        navNode.innerHTML = navFor(viewRole).map(function (section) {
          var links = section.items.map(function (item) {
            var active = item[1] === file;
            return '<a href="'+item[1]+'" class="'+(active?"on":"")+'" title="'+safeText(item[0]).replace(/"/g,"&quot;")+'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'+(ICONS[item[2]]||ICONS.home)+'</svg><span class="vcms-nav-label">'+safeText(item[0])+'</span></a>';
          }).join("");
          if (!section.group) return links;
          var key = section.group.toLowerCase().replace(/[^a-z0-9]+/g,"-");
          var activeGroup = section.items.some(function (item) { return item[1] === file; });
          var open = activeGroup || saved[key] === true;
          return '<button type="button" class="vcms-group-toggle" data-group="'+key+'" aria-expanded="'+open+'"><span>'+safeText(section.group)+'</span><span class="vcms-chevron">⌄</span></button><div class="vcms-group-items'+(open?"":" is-closed")+'" data-items="'+key+'">'+links+'</div>';
        }).join("");
      }
      navNode.addEventListener("click",function (event) {
        var button = event.target.closest(".vcms-group-toggle"); if (!button) return;
        var key = button.getAttribute("data-group");
        var items = navNode.querySelector('.vcms-group-items[data-items="'+key+'"]');
        var open = button.getAttribute("aria-expanded") !== "true";
        button.setAttribute("aria-expanded",String(open)); if (items) items.classList.toggle("is-closed",!open);
        var saved = {}; try { saved = JSON.parse(localStorage.getItem("vcms_nav_groups") || "{}"); } catch (_) {}
        saved[key] = open; try { localStorage.setItem("vcms_nav_groups",JSON.stringify(saved)); } catch (_) {}
      });
      var viewRole = role; try { if (role === "admin") viewRole = localStorage.getItem("vmms_view_role") || "admin"; } catch (_) {}
      var roleSelect = document.getElementById("vcms-view-role");
      if (roleSelect) {
        Object.keys(ROLE_LABELS).forEach(function (key) { var option=document.createElement("option"); option.value=key; option.textContent="Acting as: "+ROLE_LABELS[key]; roleSelect.appendChild(option); });
        roleSelect.value = viewRole;
        roleSelect.addEventListener("change",function () { viewRole=roleSelect.value; try { localStorage.setItem("vmms_view_role",viewRole); } catch (_) {} renderNav(viewRole); window.dispatchEvent(new CustomEvent("vcms:view-role-change",{detail:{role:viewRole}})); });
      }
      renderNav(viewRole);
      var toggle = document.getElementById("vcms-rail-toggle");
      function setMini(mini) { document.body.classList.toggle("vcms-rail-mini",mini); toggle.setAttribute("aria-label",mini?"Expand sidebar":"Collapse sidebar"); toggle.setAttribute("title",mini?"Expand sidebar":"Collapse sidebar"); try { localStorage.setItem("vcms_side_mini",mini?"1":"0"); } catch (_) {} }
      try { setMini(localStorage.getItem("vcms_side_mini") === "1"); } catch (_) { setMini(false); }
      toggle.addEventListener("click",function () { setMini(!document.body.classList.contains("vcms-rail-mini")); });
      var nativeHeader = Array.prototype.find.call(document.querySelectorAll("body>header"),function (node) { return node !== appHeader; });
      if (nativeHeader && file !== "home.html" && file !== "home2.html") nativeHeader.classList.add("vcms-pagebar");
      document.body.classList.add("vcms-shelled");
      if (file === "home.html") document.body.classList.add("vcms-shared-home");
      window.VCMSShell = {renderNav:renderNav,setMini:setMini,getViewRole:function(){return viewRole;}};
      window.dispatchEvent(new CustomEvent("vcms:shell-ready",{detail:{me:me,viewRole:viewRole}}));
    } catch (error) { console.warn("VCMS shared shell could not start",error); }
  });
})();
