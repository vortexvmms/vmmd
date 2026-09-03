// VCMS PCS Multi-Location DPR - Stage 3 supervisor interface (fail-safe add-on).
// Loaded on dpr.html. It stays completely inert unless the selected site's
// project is configured as Multi-location DPR AND that mode is confirmed by the
// backend. On any error or Standard mode it does nothing, so the existing
// Standard DPR page is never affected. When active it hides the standard
// single-report body and mounts location blocks (today/tomorrow activities,
// actuals, resource requests) with offline drafts and an idempotent submit.
(function(){
  "use strict";
  if(typeof vmmsApi!=="function")return;
  var NL=String.fromCharCode(10);
  function $(id){return document.getElementById(id)}
  function ce(tag,cls,html){var e=document.createElement(tag);if(cls)e.className=cls;if(html!=null)e.innerHTML=html;return e}
  function esc(s){s=(s==null?"":String(s));return s.replace(/[&<>"']/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]})}
  function siteV(){try{if(typeof siteVal==="function")return siteVal()}catch(e){}return $("site")?$("site").value:""}
  function dateV(){try{if(typeof dateVal==="function")return dateVal()}catch(e){}return $("date")?$("date").value:""}
  function note(s){try{if(typeof toast==="function")return toast(s)}catch(e){}var t=$("pcs-note");if(t){t.textContent=s;t.style.display="block";setTimeout(function(){t.style.display="none"},2600)}}

  var PID=null, LOCS=[], PANEL=null, ACTIVE=false, DATE="", SITE="";

  function draftKey(locId){return "pcs_dpr_draft_"+SITE+"_"+DATE+"_"+locId}
  function saveDraft(locId,data){try{localStorage.setItem(draftKey(locId),JSON.stringify(data))}catch(e){}}
  function loadDraft(locId){try{return JSON.parse(localStorage.getItem(draftKey(locId))||"null")}catch(e){return null}}
  function clearDraft(locId){try{localStorage.removeItem(draftKey(locId))}catch(e){}}

  // Standard sections we hide when PCS mode is active. Restored if mode is off.
  function standardEls(){return [$("dpr-content"),$("dprbar")].filter(Boolean)}
  function hideStandard(){standardEls().forEach(function(e){if(e.dataset.pcsHidden!=="1"){e.dataset.pcsPrevDisplay=e.style.display;e.style.display="none";e.dataset.pcsHidden="1"}})}
  function showStandard(){standardEls().forEach(function(e){if(e.dataset.pcsHidden==="1"){e.style.display=e.dataset.pcsPrevDisplay||"";e.dataset.pcsHidden="0"}})}

  async function refresh(){
    var site=siteV(), date=dateV();
    if(!site||!date){deactivate();return}
    SITE=site;DATE=date;
    var mode="standard";
    try{var r=await vmmsApi("/api/v1/pcs/dpr-config?site_id="+encodeURIComponent(site));if(r.ok){var j=await r.json();PID=j.project_id;mode=j.dpr_mode||"standard"}}catch(e){mode="standard"}
    if(mode!=="multi_location"){deactivate();return}
    await activate();
  }

  function deactivate(){if(!ACTIVE)return;ACTIVE=false;showStandard();if(PANEL){PANEL.style.display="none"}}

  async function activate(){
    ACTIVE=true;hideStandard();
    if(!PANEL){PANEL=ce("div","pcs-panel");var host=$("dpr-main")||document.body;host.appendChild(PANEL);
      var st=ce("style",null,".pcs-panel{max-width:768px;margin:0 auto;padding:8px 4px 120px}.pcs-panel h2{font-size:18px;margin:6px 0}.pcs-loc{background:#fff;border:1px solid #e3e6ea;border-radius:12px;padding:12px;margin-bottom:14px}.pcs-loc h3{margin:0 0 8px;font-size:16px;color:#111827}.pcs-loc .sub{font-size:12px;color:#6b7280;margin-bottom:8px}.pcs-row{display:flex;gap:6px;margin-bottom:6px;flex-wrap:wrap}.pcs-in{flex:1;min-width:120px;border:1px solid #cfd5de;border-radius:8px;padding:9px;font:14px Arial}.pcs-in[type=number]{max-width:90px;flex:0 0 auto}.pcs-btn{border:0;border-radius:9px;padding:9px 12px;font-weight:800;cursor:pointer;background:#252b35;color:#fff}.pcs-btn.red{background:#c00000}.pcs-btn.lite{background:#fff;color:#9f1111;border:1px solid #e0b2b2}.pcs-btn.sm{padding:6px 9px;font-size:12px}.pcs-sech{font-weight:800;font-size:12px;text-transform:uppercase;color:#6b7280;margin:10px 0 4px}.pcs-x{background:#fee2e2;color:#991b1b;border:0;border-radius:8px;width:34px;cursor:pointer}.pcs-status{font-size:12px;font-weight:800;padding:3px 8px;border-radius:99px}.pcs-status.draft{background:#fff1c7;color:#95500b}.pcs-status.submitted{background:#dcfce7;color:#16713a}.pcs-hint{font-size:12px;color:#6b7280}");
      document.head.appendChild(st);
      var tn=ce("div","",'<div id="pcs-note" style="display:none;position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#111827;color:#fff;padding:10px 16px;border-radius:8px;z-index:9999"></div>');document.body.appendChild(tn);
    }
    PANEL.style.display="block";
    PANEL.innerHTML='<h2>PCS Multi-Location DPR</h2><div class="pcs-hint">One report per work location for '+esc(DATE)+'. Drafts save on your phone automatically; submit each location when ready.</div><div id="pcs-blocks">Loading locations...</div>';
    await loadBlocks();
  }

  async function loadBlocks(){
    LOCS=[];
    try{var r=await vmmsApi("/api/v1/pcs/locations?site_id="+encodeURIComponent(SITE));if(r.ok)LOCS=(await r.json()).filter(function(l){return l.status==="active"})}catch(e){}
    var wrap=$("pcs-blocks");if(!wrap)return;
    if(!LOCS.length){wrap.innerHTML='<div class="pcs-loc">No active work locations for this site. Ask your manager to add locations in the DPR Project Directory.</div>';return}
    wrap.innerHTML="";
    LOCS.forEach(function(l){wrap.appendChild(buildBlock(l))});
  }

  function buildBlock(loc){
    var d=loadDraft(loc.id)||{today:[],tomorrow:[],materials:[],plant:[],requests:[]};
    var box=ce("div","pcs-loc");
    box.innerHTML='<div style="display:flex;justify-content:space-between;align-items:center"><h3>'+esc(loc.name)+'</h3><span class="pcs-status draft" data-st>draft</span></div><div class="sub">'+esc(loc.code||"")+'</div>'+
      '<div class="pcs-row"><button class="pcs-btn lite sm" data-loadplan>Load manager plan</button><button class="pcs-btn lite sm" data-copyprev>Copy from date</button></div>'+
      '<div class="pcs-sech">Today activities (cumulative % as of today)</div><div data-today></div><button class="pcs-btn sm" data-addtoday>+ Activity</button>'+
      '<div class="pcs-sech">Tomorrow activities</div><div data-tom></div><button class="pcs-btn sm" data-addtom>+ Activity</button>'+
      '<div class="pcs-sech">Materials used</div><div data-mat></div><button class="pcs-btn sm" data-addmat>+ Material</button>'+
      '<div class="pcs-sech">Plant / equipment used</div><div data-plant></div><button class="pcs-btn sm" data-addplant>+ Plant</button>'+
      '<div class="pcs-sech">Requirements for upcoming work</div><div data-req></div><button class="pcs-btn sm" data-addreq>+ Request</button>'+
      '<div class="pcs-row" style="margin-top:12px"><button class="pcs-btn red" data-submit style="flex:1">Submit '+esc(loc.name)+'</button></div>';
    var state=d;
    function persist(){saveDraft(loc.id,state)}
    function renderList(host,arr,cols,kind){
      host.innerHTML="";
      arr.forEach(function(item,idx){
        var row=ce("div","pcs-row");
        cols.forEach(function(col){
          var inp=ce("input","pcs-in");inp.placeholder=col.ph;if(col.type)inp.type=col.type;inp.value=item[col.k]==null?"":item[col.k];
          inp.addEventListener("input",function(){item[col.k]=(col.type==="number"?(inp.value===""?null:Number(inp.value)):inp.value);persist()});
          row.appendChild(inp);
        });
        var x=ce("button","pcs-x",'x');x.addEventListener("click",function(){arr.splice(idx,1);persist();renderList(host,arr,cols,kind)});
        row.appendChild(x);host.appendChild(row);
      });
    }
    var todayCols=[{k:"description",ph:"Activity description"},{k:"percent_complete",ph:"%",type:"number"}];
    var tomCols=[{k:"description",ph:"Tomorrow activity"}];
    var matCols=[{k:"item_name",ph:"Material"},{k:"quantity",ph:"Qty",type:"number"},{k:"unit",ph:"Unit"}];
    var plantCols=[{k:"item_name",ph:"Plant/equipment"},{k:"quantity",ph:"Qty",type:"number"},{k:"usage_hours",ph:"Hrs",type:"number"}];
    var reqCols=[{k:"item_name",ph:"Item required"},{k:"quantity",ph:"Qty",type:"number"},{k:"required_by",ph:"By (YYYY-MM-DD)"}];
    function rAll(){renderList(box.querySelector("[data-today]"),state.today,todayCols);renderList(box.querySelector("[data-tom]"),state.tomorrow,tomCols);renderList(box.querySelector("[data-mat]"),state.materials,matCols);renderList(box.querySelector("[data-plant]"),state.plant,plantCols);renderList(box.querySelector("[data-req]"),state.requests,reqCols)}
    box.querySelector("[data-addtoday]").addEventListener("click",function(){state.today.push({description:"",percent_complete:null});persist();rAll()});
    box.querySelector("[data-addtom]").addEventListener("click",function(){state.tomorrow.push({description:""});persist();rAll()});
    box.querySelector("[data-addmat]").addEventListener("click",function(){state.materials.push({item_name:"",quantity:null,unit:""});persist();rAll()});
    box.querySelector("[data-addplant]").addEventListener("click",function(){state.plant.push({item_name:"",quantity:null,usage_hours:null});persist();rAll()});
    box.querySelector("[data-addreq]").addEventListener("click",function(){state.requests.push({item_name:"",quantity:null,required_by:""});persist();rAll()});
    box.querySelector("[data-loadplan]").addEventListener("click",async function(){await loadPlanInto(loc,state);rAll();note("Manager plan loaded")});
    box.querySelector("[data-copyprev]").addEventListener("click",async function(){var dt=prompt("Copy today activities from date (YYYY-MM-DD)");if(!dt)return;await copyPrevInto(loc,state,dt);rAll();note("Copied (unsaved)")});
    box.querySelector("[data-submit]").addEventListener("click",function(){submitBlock(loc,state,box)});
    rAll();
    return box;
  }

  async function loadPlanInto(loc,state){
    try{var r=await vmmsApi("/api/v1/pcs/plan?site_id="+encodeURIComponent(SITE)+"&plan_date="+encodeURIComponent(DATE));if(!r.ok)return;var j=await r.json();(j.activities||[]).forEach(function(a){if(a.location_id===loc.id){state.today.push({description:a.description,percent_complete:a.previous_completion,source_plan_activity_id:a.id,origin:"planned"})}})}catch(e){}
  }
  async function copyPrevInto(loc,state,dt){
    try{var r=await vmmsApi("/api/v1/pcs/report?site_id="+encodeURIComponent(SITE)+"&report_date="+encodeURIComponent(dt));if(!r.ok)return;var j=await r.json();var rep=j.report;if(!rep||!rep.pcs_location_reports)return;rep.pcs_location_reports.forEach(function(lr){if(lr.location_id===loc.id){(lr.pcs_location_activities||[]).filter(function(a){return a.kind==="today"}).forEach(function(a){state.today.push({description:a.description,percent_complete:a.percent_complete})})}})}catch(e){}
  }

  async function submitBlock(loc,state,box){
    var stEl=box.querySelector("[data-st]");
    for(var i=0;i<state.today.length;i++){var t=state.today[i];if(t.description&&(t.percent_complete!=null)&&(t.percent_complete<0||t.percent_complete>100)){return note("Percent must be 0-100")}}
    var btn=box.querySelector("[data-submit]");btn.disabled=true;var oldtxt=btn.textContent;btn.textContent="Submitting...";
    try{
      var pr=await vmmsApi("/api/v1/pcs/report/ensure",{method:"POST",body:JSON.stringify({site_id:SITE,report_date:DATE})});
      if(!pr.ok)throw new Error("Could not open the PCS report");var parent=await pr.json();
      var lrr=await vmmsApi("/api/v1/pcs/report/"+parent.id+"/location",{method:"POST",body:JSON.stringify({location_id:loc.id})});
      if(!lrr.ok)throw new Error("Could not start this location");var lr=await lrr.json();
      for(var a=0;a<state.today.length;a++){var it=state.today[a];if(!it.description)continue;await vmmsApi("/api/v1/pcs/location-report/"+lr.id+"/activity",{method:"POST",body:JSON.stringify({kind:"today",description:it.description,percent_complete:it.percent_complete,source_plan_activity_id:it.source_plan_activity_id||null,origin:it.origin||"manual",display_order:a})})}
      for(var b=0;b<state.tomorrow.length;b++){var tm=state.tomorrow[b];if(!tm.description)continue;await vmmsApi("/api/v1/pcs/location-report/"+lr.id+"/activity",{method:"POST",body:JSON.stringify({kind:"tomorrow",description:tm.description,origin:"manual",display_order:b})})}
      for(var m=0;m<state.materials.length;m++){var mm=state.materials[m];if(!mm.item_name)continue;await vmmsApi("/api/v1/pcs/location-report/"+lr.id+"/actual-material",{method:"POST",body:JSON.stringify({item_name:mm.item_name,quantity:mm.quantity,unit:mm.unit})})}
      for(var p=0;p<state.plant.length;p++){var pp=state.plant[p];if(!pp.item_name)continue;await vmmsApi("/api/v1/pcs/location-report/"+lr.id+"/actual-plant",{method:"POST",body:JSON.stringify({item_name:pp.item_name,quantity:pp.quantity,usage_hours:pp.usage_hours})})}
      for(var q=0;q<state.requests.length;q++){var rq=state.requests[q];if(!rq.item_name)continue;await vmmsApi("/api/v1/pcs/resource-request",{method:"POST",body:JSON.stringify({site_id:SITE,location_id:loc.id,location_report_id:lr.id,request_type:"material",item_name:rq.item_name,quantity:rq.quantity,required_by:rq.required_by||null})})}
      var sub=await vmmsApi("/api/v1/pcs/location-report/"+lr.id+"/submit",{method:"POST",body:JSON.stringify({record_version:lr.record_version||1})});
      if(!sub.ok){var e=await sub.json().catch(function(){return {}});throw new Error(e.detail||"Submit failed")}
      clearDraft(loc.id);stEl.textContent="submitted";stEl.className="pcs-status submitted";note(loc.name+" submitted and confirmed");
    }catch(err){note(err.message||"Could not submit - saved on phone, tap Submit to retry")}
    finally{btn.disabled=false;btn.textContent=oldtxt}
  }

  function hook(){var s=$("site"),d=$("date");if(s)s.addEventListener("change",refresh);if(d)d.addEventListener("change",refresh);setTimeout(refresh,600)}
  if(document.readyState!=="loading")hook();else document.addEventListener("DOMContentLoaded",hook);
})();
