/* VCMS app shell — on desktop, adds the branded red top header + left nav rail to
   every signed-in page, and reskins the page's own header into a light toolbar so
   its buttons/back-link keep working. Non-destructive, wrapped in try/catch, and it
   skips login, index, and the home page (which carries its own shell). Mobile is
   left unchanged. */
(function () {
  function ready(fn){ if(document.readyState!=="loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  ready(async function () {
    try {
      var file = (location.pathname.split("/").pop() || "").toLowerCase();
      if (file === "login.html" || file === "index.html" || file === "") return;
      if (document.body.classList.contains("shell")) return;
      if (document.getElementById("vcms-rail")) return;
      if (typeof getSession !== "function" || !getSession()) return;

      var me = null;
      try { var r = await vmmsApi("/api/v1/me"); if (r.ok) me = await r.json(); } catch (e) {}
      var role = (me && me.role) || "admin";
      var LOGO = "https://www.vortex.sg/images/Vortex-Logo_Type.png";
      var ROLE_LABELS = {admin:"Administrator",general_manager:"General Manager",operation_manager:"Operation Manager",hr_assistant:"HR Assistant",main_sup:"Site Manager",wshc_lead:"WSHC Lead",site_sup:"Site Supervisor",safety_sup:"Safety Supervisor",wshc:"WSHC",logistics_sup:"Logistics Supervisor",payroll:"Payroll"};
      var TIER = {admin:"full",general_manager:"full",operation_manager:"full",hr_assistant:"full",main_sup:"manager",wshc_lead:"manager",site_sup:"supervisor",safety_sup:"supervisor",wshc:"supervisor",logistics_sup:"supervisor",payroll:"payroll"};
      var ALLOW = {
        full:null,
        manager:new Set(["home.html","todo.html","request.html","attendance.html","verify.html","dpr.html","dprlist.html","resource-summary.html","site-dashboard.html","pr-directory.html","pr-new.html","pr-dashboard.html","whatsapp.html","dashboard.html","reports.html","timesheet.html","settings.html","help.html"]),
        supervisor:new Set(["home.html","todo.html","request.html","attendance.html","dpr.html","dprlist.html","pr-new.html","whatsapp.html","dashboard.html","reports.html","settings.html","help.html"]),
        payroll:new Set(["home.html","todo.html","verify.html","reports.html","timesheet.html","manhours.html","settings.html","help.html"]),
      };
      var IC = {home:'<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',chk:'<circle cx="12" cy="12" r="8.5"/><path d="M8 12.5l2.5 2.5L16 9.5"/>',user:'<circle cx="9" cy="8" r="3"/><path d="M3.5 20c0-3 2.5-5 5.5-5s5.5 2 5.5 5"/>',bld:'<path d="M4 20V6l6-2 6 2v14M3 20h18"/>',cal:'<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 9.5h16M8.5 3v4M15.5 3v4"/>',clk:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',grid:'<rect x="3.5" y="4.5" width="17" height="15" rx="1.5"/><path d="M3.5 9h17M9 9v10.5M14.5 9v10.5"/>',doc:'<path d="M7 3.5h8l3.5 3.5V20.5H7z"/><path d="M9.5 12h5M9.5 15h5"/>',list:'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 12.5h8M8 16h5"/>',chart:'<path d="M5 20V11M10 20V5M15 20v-8M20 20v-5"/>',cart:'<path d="M6 6h13l-1.5 8H8z"/><circle cx="9" cy="19" r="1.3"/><circle cx="16" cy="19" r="1.3"/>',chat:'<path d="M20 12a8 8 0 01-11.6 7.1L4 20l.9-4.3A8 8 0 1120 12z"/>',shield:'<path d="M12 3.5l7 2.8v5.2c0 4.2-3 7-7 8.5-4-1.5-7-4.3-7-8.5V6.3z"/>',gear:'<circle cx="12" cy="12" r="3"/><path d="M12 4v2.5M12 17.5V20M4 12h2.5M17.5 12H20"/>',help:'<circle cx="12" cy="12" r="8.5"/><path d="M9.7 9.2a2.4 2.4 0 114.3 1.5c-.8.9-1.8 1.1-1.8 2.5"/><path d="M12 16.4h.01"/>'};
      var esc = window.esc || function(v){ return String(v==null?"":v); };

      function navFor(rl){
        var t = TIER[rl] || "full";
        if (t === "supervisor") return [
          {items:[["Home","home.html","home"],["To-do","todo.html","chk"]]},
          {grp:"Daily",items:[["Request manpower","request.html","cal"],["Attendance","attendance.html","chk"],["WhatsApp","whatsapp.html","chat"]]},
          {grp:"Site progress",items:[["Daily report","dpr.html","doc"],["DPR history","dprlist.html","list"],["Dashboard","dashboard.html","chart"],["Reports","reports.html","doc"]]},
          {grp:"Procurement",items:[["New PR","pr-new.html","cart"]]},
          {grp:"More",items:[["Settings","settings.html","gear"],["How to use","help.html","help"]]} ];
        var full = [
          {items:[["Home","home.html","home"],["To-do","todo.html","chk"]]},
          {grp:"Manpower",items:[["Workers","workers.html","user"],["Sites","sites.html","bld"],["Allocation","allocation.html","cal"],["Attendance","attendance.html","chk"],["End-time","verify.html","clk"],["Timesheet","timesheet.html","grid"],["Dashboard","dashboard.html","chart"]]},
          {grp:"Site progress",items:[["Daily report","dpr.html","doc"],["DPR history","dprlist.html","list"],["Resource summary","resource-summary.html","grid"],["Site board","site-dashboard.html","chart"],["Reports","reports.html","doc"]]},
          {grp:"Procurement",items:[["PR directory","pr-directory.html","list"],["New PR","pr-new.html","cart"],["PR board","pr-dashboard.html","chart"]]},
          {grp:"More",items:[["WhatsApp","whatsapp.html","chat"],["Users","users.html","shield"],["Settings","settings.html","gear"],["How to use","help.html","help"]]} ];
        var allow = ALLOW[t];
        return full.map(function(s){ return {grp:s.grp, items:s.items.filter(function(it){ return !allow || allow.has(it[1]); })}; }).filter(function(s){ return s.items.length; });
      }
      var NAVITEMS = [];
      function railHTML(rl){
        var nav = navFor(rl); NAVITEMS = [];
        nav.forEach(function(s){ s.items.forEach(function(it){ NAVITEMS.push(it); }); });
        return nav.map(function(s){ return (s.grp?'<div class="grp">'+s.grp+"</div>":"")+s.items.map(function(it){ var on=it[1]===file?" on":""; return '<a href="'+it[1]+'" class="'+on.trim()+'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'+(IC[it[2]]||IC.home)+"</svg>"+esc(it[0])+"</a>"; }).join(""); }).join("");
      }

      var css =
        "@media(min-width:900px){body.vcms-shelled{margin-left:236px;padding-top:60px;}}" +
        "@media(max-width:899px){#vcms-brand,#vcms-rail{display:none!important;}}" +
        "#vcms-brand{position:fixed;top:0;left:0;right:0;height:60px;background:#C00000;color:#fff;display:flex;align-items:center;gap:14px;padding:0 64px 0 14px;z-index:50;font-family:Arial,system-ui,sans-serif;}" +
        "#vcms-brand .logo{height:40px;background:#fff;border-radius:8px;padding:3px;flex:none;}" +
        "#vcms-brand .bt{font-size:22px;font-weight:800;}" +
        "#vcms-brand .bc{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font-size:17px;font-weight:800;color:#fff;white-space:nowrap;pointer-events:none;}@media(max-width:1300px){#vcms-brand .bc{display:none;}}" +
        "#vcms-brand .grow{flex:1;}" +
        "#vcms-brand .sw{position:relative;}#vcms-brand .sw input{border:none;border-radius:10px;height:40px;box-sizing:border-box;padding:0 12px 0 32px;font-size:13px;width:180px;background:#fff;color:#111;}#vcms-brand .sw svg{position:absolute;left:10px;top:12px;width:15px;height:15px;color:#9CA3AF;}" +
        "#vcms-brand .res{position:absolute;top:44px;left:0;right:0;background:#fff;border:1px solid #E5E7EB;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.2);overflow:hidden;display:none;z-index:60;}#vcms-brand .res a{display:block;padding:9px 12px;font-size:13px;color:#334155;text-decoration:none;}#vcms-brand .res a:hover{background:#F3F4F6;}" +
        "#vcms-brand .gc{background:#fff;color:#111;border-radius:10px;height:40px;box-sizing:border-box;padding:0 8px 0 14px;display:flex;align-items:center;gap:10px;max-width:330px;}#vcms-brand .gc .g1{font-weight:800;font-size:14px;line-height:1.1;white-space:nowrap;}#vcms-brand .gc .g2{font-size:11px;color:#6B7280;white-space:nowrap;}#vcms-brand .gc .chip{background:#C00000;color:#fff;font-size:11px;font-weight:700;padding:3px 11px;border-radius:20px;white-space:nowrap;}" +
        "#vcms-brand select{border:none;border-radius:10px;height:40px;box-sizing:border-box;padding:0 9px;font-size:12px;font-weight:700;background:#fff;color:#111;}" +
        "#vcms-brand .lo{background:#A50E0E;color:#fff;border:none;border-radius:10px;height:40px;box-sizing:border-box;padding:0 16px;font-weight:700;font-size:13px;cursor:pointer;flex:none;}" +
        "#vcms-rail{position:fixed;left:0;top:60px;bottom:0;width:236px;background:#fff;border-right:1px solid #E5E7EB;display:flex;flex-direction:column;z-index:40;font-family:Arial,system-ui,sans-serif;}" +
        "#vcms-rail .rn{flex:1;overflow:auto;padding:8px 10px 16px;}" +
        "#vcms-rail .grp{font-size:10.5px;font-weight:700;color:#9AA1AB;letter-spacing:.06em;text-transform:uppercase;padding:13px 8px 5px;}" +
        "#vcms-rail a{display:flex;align-items:center;gap:11px;padding:9px 10px;border-radius:10px;color:#3A3D42;font-size:14px;text-decoration:none;margin:1px 0;transition:transform .14s,box-shadow .14s,background .14s;}" +
        "#vcms-rail a:hover{background:#F6F7F9;transform:translateX(3px);box-shadow:0 4px 12px rgba(0,0,0,.07);}" +
        "#vcms-rail a.on{background:#FDE8E8;color:#C00000;font-weight:700;}#vcms-rail a svg{width:19px;height:19px;flex:none;}" +
        "@media(min-width:900px){body.vcms-shelled .vcms-pagebar{background:#fff!important;color:#1F2328!important;box-shadow:0 1px 0 #E5E7EB!important;position:sticky!important;top:60px!important;z-index:19;}" +
        "body.vcms-shelled .vcms-pagebar a,body.vcms-shelled .vcms-pagebar h1,body.vcms-shelled .vcms-pagebar p,body.vcms-shelled .vcms-pagebar span:not(.chip){color:#1F2328!important;}" +
        "body.vcms-shelled .vcms-pagebar .text-red-100{color:#6B7280!important;}}";
      var st = document.createElement("style"); st.id = "vcms-rail-css"; st.textContent = css; document.head.appendChild(st);

      var brand = document.createElement("header");
      brand.id = "vcms-brand";
      brand.innerHTML =
        '<img class="logo" src="'+LOGO+'" onerror="this.style.display=\'none\'">' +
        '<div class="bt">VCMS</div>' +
        '<div class="bc">Vortex Construction Management System</div>' +
        '<div class="grow"></div>' +
        '<div class="sw"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg><input id="vcms-search" placeholder="Search pages…" autocomplete="off"><div class="res" id="vcms-res"></div></div>' +
        '<div class="gc"><div><div class="g1">'+esc((me&&me.name?("Hi, "+(me.name.split(/\\s+/)[0])):"Signed in"))+'</div><div class="g2">'+esc(me&&me.name?me.name:"")+'</div></div><span class="chip">'+esc(ROLE_LABELS[role]||role)+'</span></div>' +
        (role==="admin"?'<select id="vcms-rswitch"></select>':"") +
        '<button class="lo" onclick="vmmsLogout()">Log Out</button>';
      document.body.insertBefore(brand, document.body.firstChild);

      var rail = document.createElement("aside");
      rail.id = "vcms-rail";
      rail.innerHTML = '<nav class="rn" id="vcms-rn"></nav>';
      document.body.appendChild(rail);

      var viewRole = role;
      if (role === "admin") {
        try { viewRole = localStorage.getItem("vmms_view_role") || "admin"; } catch(e){}
        var sw = document.getElementById("vcms-rswitch");
        sw.innerHTML = Object.keys(ROLE_LABELS).map(function(k){ return '<option value="'+k+'">Acting as: '+ROLE_LABELS[k]+"</option>"; }).join("");
        sw.value = viewRole;
        sw.addEventListener("change", function(){ try{ localStorage.setItem("vmms_view_role", sw.value); }catch(e){} document.getElementById("vcms-rn").innerHTML = railHTML(sw.value); });
      }
      document.getElementById("vcms-rn").innerHTML = railHTML(viewRole);

      var si = document.getElementById("vcms-search"), res = document.getElementById("vcms-res");
      si.addEventListener("input", function(){ var q=si.value.trim().toLowerCase(); if(!q){ res.style.display="none"; return; } var m=NAVITEMS.filter(function(it){ return it[0].toLowerCase().indexOf(q)!==-1; }).slice(0,8); res.innerHTML=m.map(function(it){ return '<a href="'+it[1]+'">'+esc(it[0])+"</a>"; }).join("")||'<a style="color:#9CA3AF">No match</a>'; res.style.display="block"; });
      si.addEventListener("keydown", function(e){ if(e.key==="Enter"){ var q=si.value.trim().toLowerCase(); var m=NAVITEMS.find(function(it){ return it[0].toLowerCase().indexOf(q)!==-1; }); if(m) location.href=m[1]; } });
      document.addEventListener("click", function(e){ if(!e.target.closest("#vcms-brand .sw")) res.style.display="none"; });

      var ph = document.querySelector("body > header") || document.querySelector("header");
      if (ph && ph !== brand) ph.classList.add("vcms-pagebar");
      document.body.classList.add("vcms-shelled");
    } catch (e) {}
  });
})();
