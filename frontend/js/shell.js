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
        manager:new Set(["home.html","todo.html","schedule.html","request.html","attendance.html","verify.html","dpr.html","dprlist.html","resource-summary.html","site-dashboard.html","pr-directory.html","pr-new.html","pr-dashboard.html","whatsapp.html","dashboard.html","reports.html","timesheet.html","worker-cards.html","training-matrix.html","settings.html","help.html"]),
        supervisor:new Set(["home.html","todo.html","schedule.html","request.html","attendance.html","dpr.html","dprlist.html","pr-new.html","whatsapp.html","dashboard.html","reports.html","worker-cards.html","training-matrix.html","settings.html","help.html"]),
        payroll:new Set(["home.html","todo.html","schedule.html","verify.html","reports.html","timesheet.html","manhours.html","settings.html","help.html"]),
      };
      var IC = {home:'<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',chk:'<circle cx="12" cy="12" r="8.5"/><path d="M8 12.5l2.5 2.5L16 9.5"/>',user:'<circle cx="9" cy="8" r="3"/><path d="M3.5 20c0-3 2.5-5 5.5-5s5.5 2 5.5 5"/>',bld:'<path d="M4 20V6l6-2 6 2v14M3 20h18"/>',cal:'<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 9.5h16M8.5 3v4M15.5 3v4"/>',clk:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',grid:'<rect x="3.5" y="4.5" width="17" height="15" rx="1.5"/><path d="M3.5 9h17M9 9v10.5M14.5 9v10.5"/>',doc:'<path d="M7 3.5h8l3.5 3.5V20.5H7z"/><path d="M9.5 12h5M9.5 15h5"/>',list:'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 12.5h8M8 16h5"/>',chart:'<path d="M5 20V11M10 20V5M15 20v-8M20 20v-5"/>',cart:'<path d="M6 6h13l-1.5 8H8z"/><circle cx="9" cy="19" r="1.3"/><circle cx="16" cy="19" r="1.3"/>',chat:'<path d="M20 12a8 8 0 01-11.6 7.1L4 20l.9-4.3A8 8 0 1120 12z"/>',shield:'<path d="M12 3.5l7 2.8v5.2c0 4.2-3 7-7 8.5-4-1.5-7-4.3-7-8.5V6.3z"/>',gear:'<circle cx="12" cy="12" r="3"/><path d="M12 4v2.5M12 17.5V20M4 12h2.5M17.5 12H20"/>',help:'<circle cx="12" cy="12" r="8.5"/><path d="M9.7 9.2a2.4 2.4 0 114.3 1.5c-.8.9-1.8 1.1-1.8 2.5"/><path d="M12 16.4h.01"/>'};
      var esc = window.esc || function(v){ return String(v==null?"":v); };

      function navFor(rl){
        var t = TIER[rl] || "full";
        if (t === "supervisor") return [
          {items:[["Home","home.html","home"],["To-do","todo.html","chk"]]},
          {grp:"Daily",items:[["Request manpower","request.html","cal"],["Attendance","attendance.html","chk"],["WhatsApp","whatsapp.html","chat"]]},
          {grp:"Planning",items:[["Project Schedule","schedule.html","cal"]]},
          {grp:"Site progress",items:[["Daily report","dpr.html","doc"],["DPR history","dprlist.html","list"],["Dashboard","dashboard.html","chart"],["Reports","reports.html","doc"]]},
          {grp:"Procurement",items:[["New PR","pr-new.html","cart"]]},
          {grp:"Admin",items:[["SIC Submission","worker-cards.html","doc"],["Training matrix","training-matrix.html","grid"]]},
          {grp:"More",items:[["Settings","settings.html","gear"],["How to use","help.html","help"]]} ];
        var full = [
          {items:[["Home","home.html","home"],["To-do","todo.html","chk"]]},
          {grp:"Manpower",items:[["Workers","workers.html","user"],["Sites","sites.html","bld"],["Allocation","allocation.html","cal"],["Attendance","attendance.html","chk"],["End-time","verify.html","clk"],["Timesheet","timesheet.html","grid"],["Dashboard","dashboard.html","chart"]]},
          {grp:"Planning",items:[["Project Schedule","schedule.html","cal"]]},
          {grp:"Site progress",items:[["Daily report","dpr.html","doc"],["DPR history","dprlist.html","list"],["Resource summary","resource-summary.html","grid"],["Site board","site-dashboard.html","chart"],["Reports","reports.html","doc"]]},
          {grp:"Procurement",items:[["PR directory","pr-directory.html","list"],["New PR","pr-new.html","cart"],["PR board","pr-dashboard.html","chart"]]},
          {grp:"Admin",items:[["SIC Submission","worker-cards.html","doc"],["Training matrix","training-matrix.html","grid"]]},
          {grp:"More",items:[["WhatsApp","whatsapp.html","chat"],["Users","users.html","shield"],["Settings","settings.html","gear"],["How to use","help.html","help"]]} ];
        var allow = ALLOW[t];
        var out = full.map(function(s){ return {grp:s.grp, items:s.items.filter(function(it){ return !allow || allow.has(it[1]); })}; }).filter(function(s){ return s.items.length; });
        // Managers (Site Manager / WSHC Lead) sometimes request manpower too.
        if (t === "manager") {
          var mp = out.filter(function(s){ return s.grp === "Manpower"; })[0];
          if (mp && !mp.items.some(function(it){ return it[1] === "request.html"; })) mp.items.unshift(["Request manpower","request.html","cal"]);
        }
        if (rl === "operation_manager" || rl === "general_manager") {
          out = out.map(function(s){ return {grp:s.grp, items:s.items.filter(function(it){ return it[1] !== "worker-cards.html" && it[1] !== "training-matrix.html"; })}; }).filter(function(s){ return s.items.length; });
        }
        return out;
      }
      var NAVITEMS = [];
      function railHTML(rl){
        var nav = navFor(rl); NAVITEMS = [];
        nav.forEach(function(s){ s.items.forEach(function(it){ NAVITEMS.push(it); }); });
        var saved={}; try{saved=JSON.parse(localStorage.getItem("vcms_nav_groups")||"{}");}catch(e){}
        return nav.map(function(s){
          var links=s.items.map(function(it){ var on=it[1]===file?" on":""; return '<a href="'+it[1]+'" class="'+on.trim()+'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'+(IC[it[2]]||IC.home)+"</svg>"+esc(it[0])+"</a>"; }).join("");
          if(!s.grp) return links;
          var key=s.grp.toLowerCase().replace(/[^a-z0-9]+/g,"-"), active=s.items.some(function(it){return it[1]===file;}), open=active||saved[key]===true;
          return '<button type="button" class="grp-toggle" data-group="'+key+'" aria-expanded="'+open+'"><span>'+esc(s.grp)+'</span><span class="chev">⌄</span></button><div class="grp-items'+(open?'':' is-closed')+'" data-items="'+key+'">'+links+'</div>';
        }).join("");
      }
      function bindRail(){var rn=document.getElementById("vcms-rn");if(!rn||rn.dataset.bound)return;rn.dataset.bound="1";rn.addEventListener("click",function(e){var b=e.target.closest(".grp-toggle");if(!b)return;var key=b.getAttribute("data-group"),box=rn.querySelector('.grp-items[data-items="'+key+'"]'),open=b.getAttribute("aria-expanded")!=="true";b.setAttribute("aria-expanded",String(open));if(box)box.classList.toggle("is-closed",!open);var saved={};try{saved=JSON.parse(localStorage.getItem("vcms_nav_groups")||"{}");}catch(x){}saved[key]=open;try{localStorage.setItem("vcms_nav_groups",JSON.stringify(saved));}catch(x){}});}

      var css =
        "@media(min-width:900px){body.vcms-shelled{margin-left:236px;padding-top:64px;}}" +
        "@media(max-width:899px){#vcms-brand,#vcms-rail{display:none!important;}}" +
        "#vcms-brand{position:fixed;top:0;left:0;right:0;height:64px;background:#C00000;color:#fff;display:flex;align-items:center;gap:12px;padding:0 64px 0 14px;z-index:50;font-family:Arial,system-ui,sans-serif;border-bottom:3px solid #17191D;box-shadow:0 5px 16px rgba(0,0,0,.18);box-sizing:border-box;}" +
        "#vcms-brand .logo{height:42px;background:#fff;border-radius:10px;padding:3px;flex:none;}" +
        "#vcms-brand .bt{font-size:23px;font-weight:800;letter-spacing:.02em;}" +
        "#vcms-brand .bc{position:static;transform:none;flex:1 1 auto;min-width:0;padding:0 16px;text-align:center;overflow:hidden;text-overflow:ellipsis;font-size:clamp(13px,1.05vw,17px);font-weight:800;color:#fff;white-space:nowrap;pointer-events:none;}@media(max-width:1260px){#vcms-brand .bc{display:none;}}" +
        "#vcms-brand .grow{display:none;}" +
        "#vcms-brand .sw{position:relative;}#vcms-brand .sw input{border:none;border-radius:10px;height:40px;box-sizing:border-box;padding:0 12px 0 32px;font-size:13px;width:180px;background:#fff;color:#111;}#vcms-brand .sw svg{position:absolute;left:10px;top:12px;width:15px;height:15px;color:#9CA3AF;}" +
        "#vcms-brand .res{position:absolute;top:44px;left:0;right:0;background:#fff;border:1px solid #E5E7EB;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.2);overflow:hidden;display:none;z-index:60;}#vcms-brand .res a{display:block;padding:9px 12px;font-size:13px;color:#334155;text-decoration:none;}#vcms-brand .res a:hover{background:#F3F4F6;}" +
        "#vcms-brand .gc{background:#fff;color:#111;border:1px solid #D9DDE3;border-radius:10px;height:42px;box-sizing:border-box;padding:0 8px 0 14px;display:flex;align-items:center;gap:10px;max-width:330px;}#vcms-brand .gc .g1{font-weight:800;font-size:14px;line-height:1.1;white-space:nowrap;}#vcms-brand .gc .g2{font-size:11px;color:#6B7280;white-space:nowrap;}#vcms-brand .gc .chip{background:#C00000;color:#fff;font-size:11px;font-weight:700;padding:3px 11px;border-radius:20px;white-space:nowrap;}" +
        "#vcms-brand select{border:1px solid #D9DDE3;border-radius:10px;height:42px;box-sizing:border-box;padding:0 10px;font-size:12px;font-weight:700;background:#fff;color:#111;}" +
        "#vcms-project-context{display:flex;align-items:center;gap:6px;color:#fff;font-size:11px;font-weight:700;}#vcms-project-context select{max-width:240px;}" +
        "#vcms-brand .lo{background:#17191D;color:#fff;border:1px solid #17191D;border-radius:10px;height:42px;box-sizing:border-box;padding:0 16px;font-weight:700;font-size:13px;cursor:pointer;flex:none;transition:transform .14s,box-shadow .14s;}#vcms-brand .lo:hover{transform:translateY(-1px);box-shadow:0 5px 12px rgba(0,0,0,.25);}" +
        "#vcms-rail{position:fixed;left:0;top:64px;bottom:0;width:236px;background:linear-gradient(180deg,#FFFFFF 0%,#F7F8FA 100%);border-right:1px solid #DDE1E6;box-shadow:5px 0 18px rgba(16,24,40,.035);display:flex;flex-direction:column;z-index:40;font-family:Arial,system-ui,sans-serif;}" +
        "#vcms-rail .rn{flex:1;overflow:auto;padding:8px 10px 16px;scrollbar-width:thin;scrollbar-color:#C9CED6 transparent;}#vcms-rail .rn::-webkit-scrollbar{width:5px;}#vcms-rail .rn::-webkit-scrollbar-thumb{background:#C9CED6;border-radius:9px;}" +
        "#vcms-rail .grp-toggle{width:100%;height:36px;margin:6px 0 2px;padding:0 9px;border:0;border-top:1px solid #E2E6EB;background:linear-gradient(90deg,#F1F3F6,#F8F9FA);color:#747F8F;display:flex;align-items:center;justify-content:space-between;border-radius:7px;cursor:pointer;font:800 10.5px Arial,sans-serif;letter-spacing:.09em;text-transform:uppercase;text-align:left;}#vcms-rail .grp-toggle:hover{color:#A91515;background:#ECEFF3;}#vcms-rail .grp-toggle .chev{font-size:15px;line-height:1;transition:transform .18s;}#vcms-rail .grp-toggle[aria-expanded=false] .chev{transform:rotate(-90deg);}#vcms-rail .grp-items{display:block;}#vcms-rail .grp-items.is-closed{display:none;}" +
        "#vcms-rail a{position:relative;display:flex;align-items:center;gap:10px;min-height:38px;padding:7px 10px;border-radius:9px;color:#344054;font-size:13.5px;text-decoration:none;margin:1px 0;transition:transform .16s,box-shadow .16s,background .16s,color .16s;}" +
        "#vcms-rail a:hover{background:#F2F4F7;transform:translateX(3px);box-shadow:0 3px 10px rgba(16,24,40,.06);}#vcms-rail a:hover svg{color:#C00000;transform:scale(1.05);}" +
        "#vcms-rail a.on{background:#FDECEC;color:#B42318;font-weight:700;box-shadow:0 2px 8px rgba(180,35,24,.08);}#vcms-rail a.on:before{content:'';position:absolute;left:-10px;top:7px;bottom:7px;width:4px;border-radius:0 4px 4px 0;background:#C00000;}#vcms-rail a svg{width:18px;height:18px;flex:none;color:#667085;transition:color .16s,transform .16s;}#vcms-rail a.on svg{color:#B42318;}" +
        "@media(min-width:900px){body.vcms-shelled .vcms-pagebar{background:#fff!important;color:#1F2328!important;box-shadow:0 1px 0 #E5E7EB!important;position:sticky!important;top:64px!important;z-index:19;padding:0!important;height:auto!important;}" +
        "body.vcms-shelled .vcms-pagebar>div:first-child{min-height:76px!important;box-sizing:border-box!important;padding:14px 24px!important;margin:0!important;max-width:none!important;width:100%!important;display:flex!important;align-items:center!important;}" +
        "body.vcms-shelled .vcms-pagebar>div:nth-child(n+2){min-height:54px!important;box-sizing:border-box!important;padding:8px 24px!important;margin:0!important;max-width:none!important;width:100%!important;background:#F4F5F7!important;border-top:1px solid #E5E7EB!important;display:flex!important;align-items:center!important;}" +
        "body.vcms-shelled .vcms-pagebar a,body.vcms-shelled .vcms-pagebar h1,body.vcms-shelled .vcms-pagebar p,body.vcms-shelled .vcms-pagebar span:not(.chip){color:#1F2328!important;}" +
        "body.vcms-shelled .vcms-pagebar .text-red-100{color:#6B7280!important;}}";
      var st = document.createElement("style"); st.id = "vcms-rail-css"; st.textContent = css; document.head.appendChild(st);

      var _hr = new Date().getHours(), _gt = _hr<12?"Good morning":(_hr<17?"Good afternoon":"Good evening");
      var brand = document.createElement("header");
      brand.id = "vcms-brand";
      brand.innerHTML =
        '<img class="logo" src="'+LOGO+'" onerror="this.style.display=\'none\'">' +
        '<div class="bt">VCMS</div>' +
        '<div class="bc">Vortex Construction Management System</div>' +
        '<div class="grow"></div>' +
        '<div class="gc"><div><div class="g1">'+esc(_gt)+'</div><div class="g2">'+esc(me&&me.name?me.name:"")+'</div></div><span class="chip">'+esc(ROLE_LABELS[role]||role)+'</span></div>' +
        (role==="admin"?'<select id="vcms-rswitch"></select>':"") +
        '<button class="lo" onclick="vmmsLogout()">Log Out</button>';
      document.body.insertBefore(brand, document.body.firstChild);
      if (window.vcmsProjectContext) window.vcmsProjectContext.mount(brand);

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
      bindRail();

      // The shared brand header has just been inserted as the first header.
      // Select the page's original header explicitly, not the newly inserted one.
      var ph = Array.prototype.find.call(document.querySelectorAll("header"), function(h){ return h !== brand; });
      if (ph && ph !== brand) ph.classList.add("vcms-pagebar");
      document.body.classList.add("vcms-shelled");
    } catch (e) {}
  });
})();
