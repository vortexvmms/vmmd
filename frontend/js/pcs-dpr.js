// VCMS PCS Multi-Location DPR - Stage 3 supervisor interface (fail-safe add-on).
// Loaded on dpr.html. It stays completely inert unless the selected site's
// project is configured as Multi-location DPR AND that mode is confirmed by the
// backend. On any error or Standard mode it does nothing, so the existing
// Standard DPR page is never affected. In PCS mode ONLY the ordinary
// "Description of works" editor is replaced; project particulars, manpower,
// resources, photos, sign-off and the normal VCMS exports remain available.
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

  var PID=null, LOCS=[], PANEL=null, ACTIVE=false, DATE="", SITE="", REPORT=null, BLOCKS=[];

  function draftKey(locId){return "pcs_dpr_draft_"+SITE+"_"+DATE+"_"+locId}
  function saveDraft(locId,data){try{localStorage.setItem(draftKey(locId),JSON.stringify(data))}catch(e){}}
  function loadDraft(locId){try{return JSON.parse(localStorage.getItem(draftKey(locId))||"null")}catch(e){return null}}
  function clearDraft(locId){try{localStorage.removeItem(draftKey(locId))}catch(e){}}

  // PCS replaces only Description of works. Everything else in the established
  // DPR (including Activity photos and exports) deliberately remains untouched.
  function standardEls(){return [$("standard-description-panel")].filter(Boolean)}
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

  function deactivate(){if(!ACTIVE)return;ACTIVE=false;document.body.classList.remove("pcs-mode");showStandard();var host=$("pcs-description-host");if(host)host.style.display="none";if(PANEL){PANEL.style.display="none"}BLOCKS=[];if(typeof updateDprReadiness==="function")updateDprReadiness()}

  async function activate(){
    ACTIVE=true;document.body.classList.add("pcs-mode");hideStandard();
    var oldDraft=$("vmms-draft-banner");if(oldDraft)oldDraft.remove();
    if(!PANEL){PANEL=ce("div","pcs-panel");var host=$("pcs-description-host")||$("dpr-main")||document.body;host.appendChild(PANEL);host.style.display="block";
      var st=ce("style",null,".pcs-panel{margin-top:12px}.pcs-panel h2{font-size:18px;margin:6px 0}.pcs-loc{background:#fff;border:1px solid #e3e6ea;border-radius:12px;margin-bottom:12px;overflow:hidden}.pcs-loc-head{display:flex;align-items:center;gap:8px;width:100%;padding:12px;border:0;background:#f8fafc;text-align:left;cursor:pointer}.pcs-loc-head h3{margin:0;font-size:16px;color:#111827;flex:1}.pcs-loc-body{padding:0 12px 12px}.pcs-loc.collapsed .pcs-loc-body{display:none}.pcs-chevron{font-size:18px;transition:transform .2s}.pcs-loc.collapsed .pcs-chevron{transform:rotate(-90deg)}.pcs-loc .sub{font-size:12px;color:#6b7280;margin:0 0 8px}.pcs-row{display:flex;gap:6px;margin-bottom:6px;flex-wrap:wrap}.pcs-in{flex:1;min-width:120px;border:1px solid #cfd5de;border-radius:8px;padding:9px;font:14px Arial}.pcs-in[type=number]{max-width:90px;flex:0 0 auto}.pcs-btn{border:0;border-radius:9px;min-height:40px;padding:9px 12px;font-weight:800;cursor:pointer;background:#252b35;color:#fff}.pcs-btn:disabled{opacity:.6}.pcs-btn.red{background:#c00000}.pcs-btn.lite{background:#fff;color:#9f1111;border:1px solid #e0b2b2}.pcs-btn.sm{padding:6px 9px;font-size:12px}.pcs-sech{font-weight:800;font-size:12px;text-transform:uppercase;color:#6b7280;margin:10px 0 4px}.pcs-x{background:#fee2e2;color:#991b1b;border:0;border-radius:8px;width:40px;min-height:40px;cursor:pointer}.pcs-status{font-size:12px;font-weight:800;padding:3px 8px;border-radius:99px}.pcs-status.draft{background:#fff1c7;color:#95500b}.pcs-status.submitted{background:#dcfce7;color:#16713a}.pcs-status.pending{background:#dbeafe;color:#1d4ed8}.pcs-hint{font-size:12px;color:#6b7280;margin-bottom:10px}.pcs-sync{font-size:11px;color:#64748b;margin:5px 0 8px}@media(max-width:600px){.pcs-row>.pcs-in{min-width:calc(60% - 8px)}.pcs-in[type=number]{min-width:72px}.pcs-loc{margin-left:-4px;margin-right:-4px}}");
      document.head.appendChild(st);
      var tn=ce("div","",'<div id="pcs-note" style="display:none;position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#111827;color:#fff;padding:10px 16px;border-radius:8px;z-index:9999"></div>');document.body.appendChild(tn);
    }
    PANEL.style.display="block";
    var ph=$("pcs-description-host");if(ph)ph.style.display="block";
    PANEL.innerHTML='<h2>Work locations & activities</h2><div class="pcs-hint">Complete each location below. Project particulars, manpower, photos and sign-off continue in the normal DPR sections.</div><div id="pcs-blocks">Loading locations...</div>';
    await loadBlocks();
  }

  async function loadBlocks(){
    LOCS=[];REPORT=null;BLOCKS=[];
    try{var r=await vmmsApi("/api/v1/pcs/locations?site_id="+encodeURIComponent(SITE));if(r.ok)LOCS=(await r.json()).filter(function(l){return l.status==="active"})}catch(e){}
    try{var rr=await vmmsApi("/api/v1/pcs/report?site_id="+encodeURIComponent(SITE)+"&report_date="+encodeURIComponent(DATE));if(rr.ok)REPORT=(await rr.json()).report||null}catch(e){}
    var wrap=$("pcs-blocks");if(!wrap)return;
    if(!LOCS.length){wrap.innerHTML='<div class="pcs-loc">No active work locations for this site. Ask your manager to add locations in the DPR Project Directory.</div>';return}
    wrap.innerHTML="";
    LOCS.forEach(function(l){var saved=REPORT&&REPORT.pcs_location_reports?(REPORT.pcs_location_reports.find(function(x){return x.location_id===l.id})||null):null;wrap.appendChild(buildBlock(l,saved))});
    updatePcsReadiness();
  }

  function serverState(saved){var acts=(saved&&saved.pcs_location_activities)||[];return {today:acts.filter(function(x){return x.kind==="today"}).map(function(x){return {description:x.description,percent_complete:x.percent_complete,source_plan_activity_id:x.source_plan_activity_id,origin:x.origin}}),tomorrow:acts.filter(function(x){return x.kind==="tomorrow"}).map(function(x){return {description:x.description}}),materials:((saved&&saved.pcs_actual_materials)||[]).map(function(x){return {item_name:x.item_name,quantity:x.quantity,unit:x.unit}}),plant:((saved&&saved.pcs_actual_plant)||[]).map(function(x){return {item_name:x.item_name,quantity:x.quantity,usage_hours:x.usage_hours}}),requests:[]}}
  function buildBlock(loc,saved){
    var submitted=!!(saved&&saved.status==="submitted");if(submitted)clearDraft(loc.id);var d=submitted?serverState(saved):(loadDraft(loc.id)||serverState(saved));
    var box=ce("div","pcs-loc");
    box.innerHTML='<button type="button" class="pcs-loc-head" data-toggle><span class="pcs-chevron">⌄</span><h3>'+esc(loc.name)+'</h3><span class="pcs-status '+(submitted?'submitted':'draft')+'" data-st>'+(submitted?'submitted':'draft')+'</span></button><div class="pcs-loc-body"><div class="sub">'+esc(loc.code||"")+'</div><div class="pcs-sync" data-sync>'+(saved&&saved.updated_at?'Last synced '+esc(new Date(saved.updated_at).toLocaleString('en-SG')):'Saved automatically on this device')+'</div>'+
      '<div class="pcs-row"><button class="pcs-btn lite sm" data-loadplan>Load manager plan</button><button class="pcs-btn lite sm" data-copyprev>Copy from date</button></div>'+
      '<div class="pcs-sech">Today activities (cumulative % as of today)</div><div data-today></div><button class="pcs-btn sm" data-addtoday>+ Activity</button>'+
      '<div class="pcs-sech">Tomorrow activities</div><div data-tom></div><button class="pcs-btn sm" data-addtom>+ Activity</button>'+
      '<div class="pcs-sech">Materials used</div><div data-mat></div><button class="pcs-btn sm" data-addmat>+ Material</button>'+
      '<div class="pcs-sech">Plant / equipment used</div><div data-plant></div><button class="pcs-btn sm" data-addplant>+ Plant</button>'+
      '<div class="pcs-sech">Requirements for upcoming work</div><div data-req></div><button class="pcs-btn sm" data-addreq>+ Request</button>'+
      '<div class="pcs-row" style="margin-top:12px"><button class="pcs-btn red" data-submit style="flex:1">'+(submitted?'Submitted':'Submit '+esc(loc.name))+'</button></div></div>';
    var state=d;
    var meta={loc:loc,state:state,box:box,submitted:submitted};BLOCKS.push(meta);
    function persist(){saveDraft(loc.id,state);submitted=false;meta.submitted=false;var se=box.querySelector('[data-st]');se.textContent='draft';se.className='pcs-status draft';var sy=box.querySelector('[data-sync]');if(sy)sy.textContent='Saved on this device · waiting to submit';var sb=box.querySelector('[data-submit]');if(sb){sb.disabled=false;sb.textContent='Submit '+loc.name}syncLegacyDescription();updatePcsReadiness()}
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
    box.querySelector("[data-toggle]").addEventListener("click",function(){box.classList.toggle("collapsed")});
    box.querySelector("[data-submit]").disabled=submitted;
    box.querySelector("[data-submit]").addEventListener("click",function(){submitBlock(loc,state,box,meta)});
    rAll();
    if(submitted){box.classList.add("collapsed");box.querySelectorAll(".pcs-loc-body input,.pcs-loc-body button").forEach(function(e){e.disabled=true})}
    return box;
  }

  async function loadPlanInto(loc,state){
    try{var r=await vmmsApi("/api/v1/pcs/plan?site_id="+encodeURIComponent(SITE)+"&plan_date="+encodeURIComponent(DATE));if(!r.ok)return;var j=await r.json();(j.activities||[]).forEach(function(a){if(a.location_id===loc.id){state.today.push({description:a.description,percent_complete:a.previous_completion,source_plan_activity_id:a.id,origin:"planned"})}})}catch(e){}
  }
  async function copyPrevInto(loc,state,dt){
    try{var r=await vmmsApi("/api/v1/pcs/report?site_id="+encodeURIComponent(SITE)+"&report_date="+encodeURIComponent(dt));if(!r.ok)return;var j=await r.json();var rep=j.report;if(!rep||!rep.pcs_location_reports)return;rep.pcs_location_reports.forEach(function(lr){if(lr.location_id===loc.id){(lr.pcs_location_activities||[]).filter(function(a){return a.kind==="today"}).forEach(function(a){state.today.push({description:a.description,percent_complete:a.percent_complete})})}})}catch(e){}
  }

  async function must(r,message){if(!r.ok){var e=await r.json().catch(function(){return {}});throw new Error(e.detail||message)}return r}
  async function submitBlock(loc,state,box,meta){
    if(meta&&meta.busy)return;
    var stEl=box.querySelector("[data-st]");
    var usable=state.today.filter(function(x){return (x.description||"").trim()});
    if(!usable.length)return note("Add at least one Today activity for "+loc.name);
    for(var i=0;i<state.today.length;i++){var t=state.today[i];if(t.description&&(t.percent_complete!=null)&&(t.percent_complete<0||t.percent_complete>100)){return note("Percent must be 0-100")}}
    var btn=box.querySelector("[data-submit]");btn.disabled=true;var oldtxt=btn.textContent;btn.textContent="Submitting...";if(meta)meta.busy=true;stEl.textContent="syncing";stEl.className="pcs-status pending";
    try{
      var pr=await vmmsApi("/api/v1/pcs/report/ensure",{method:"POST",body:JSON.stringify({site_id:SITE,report_date:DATE})});
      await must(pr,"Could not open the PCS report");var parent=await pr.json();
      var lrr=await vmmsApi("/api/v1/pcs/report/"+parent.id+"/location",{method:"POST",body:JSON.stringify({location_id:loc.id})});
      await must(lrr,"Could not start this location");var lr=await lrr.json();
      if(lr.status==="submitted"){clearDraft(loc.id);if(meta){meta.submitted=true;meta.busy=false}stEl.textContent="submitted";stEl.className="pcs-status submitted";btn.textContent="Submitted";updatePcsReadiness();return}
      var reset=await vmmsApi("/api/v1/pcs/location-report/"+lr.id+"/reset-draft",{method:"POST",body:JSON.stringify({record_version:lr.record_version||1})});await must(reset,"Could not safely retry this location");
      for(var a=0;a<state.today.length;a++){var it=state.today[a];if(!it.description)continue;await must(await vmmsApi("/api/v1/pcs/location-report/"+lr.id+"/activity",{method:"POST",body:JSON.stringify({kind:"today",description:it.description,percent_complete:it.percent_complete,source_plan_activity_id:it.source_plan_activity_id||null,origin:it.origin||"manual",display_order:a})}),"Could not save a Today activity")}
      for(var b=0;b<state.tomorrow.length;b++){var tm=state.tomorrow[b];if(!tm.description)continue;await must(await vmmsApi("/api/v1/pcs/location-report/"+lr.id+"/activity",{method:"POST",body:JSON.stringify({kind:"tomorrow",description:tm.description,origin:"manual",display_order:b})}),"Could not save a Tomorrow activity")}
      for(var m=0;m<state.materials.length;m++){var mm=state.materials[m];if(!mm.item_name)continue;await must(await vmmsApi("/api/v1/pcs/location-report/"+lr.id+"/actual-material",{method:"POST",body:JSON.stringify({item_name:mm.item_name,quantity:mm.quantity,unit:mm.unit})}),"Could not save a material")}
      for(var p=0;p<state.plant.length;p++){var pp=state.plant[p];if(!pp.item_name)continue;await must(await vmmsApi("/api/v1/pcs/location-report/"+lr.id+"/actual-plant",{method:"POST",body:JSON.stringify({item_name:pp.item_name,quantity:pp.quantity,usage_hours:pp.usage_hours})}),"Could not save plant/equipment")}
      for(var q=0;q<state.requests.length;q++){var rq=state.requests[q];if(!rq.item_name)continue;await must(await vmmsApi("/api/v1/pcs/resource-request",{method:"POST",body:JSON.stringify({site_id:SITE,location_id:loc.id,location_report_id:lr.id,request_type:"material",item_name:rq.item_name,quantity:rq.quantity,required_by:rq.required_by||null})}),"Could not save a request")}
      var sub=await vmmsApi("/api/v1/pcs/location-report/"+lr.id+"/submit",{method:"POST",body:JSON.stringify({record_version:lr.record_version||1})});
      await must(sub,"Submit failed");state._pendingSubmit=false;clearDraft(loc.id);if(meta)meta.submitted=true;stEl.textContent="submitted";stEl.className="pcs-status submitted";var sy=box.querySelector('[data-sync]');if(sy)sy.textContent='Synced '+new Date().toLocaleString('en-SG');btn.textContent="Submitted";box.classList.add("collapsed");note(loc.name+" submitted and confirmed");
    }catch(err){state._pendingSubmit=true;saveDraft(loc.id,state);stEl.textContent=navigator.onLine?"retry needed":"queued offline";stEl.className="pcs-status pending";var sy2=box.querySelector('[data-sync]');if(sy2)sy2.textContent='Safe on this device · will retry when connection returns';note(err.message||"Could not submit - saved on phone, tap Submit to retry")}
    finally{if(meta)meta.busy=false;if(!(meta&&meta.submitted)){btn.disabled=false;btn.textContent=oldtxt}updatePcsReadiness()}
  }

  function syncLegacyDescription(){
    var out=[];BLOCKS.forEach(function(b){var rows=(b.state.today||[]).filter(function(x){return (x.description||'').trim()});if(!rows.length)return;out.push(b.loc.name);rows.forEach(function(x,i){out.push((i+1)+') '+x.description+(x.percent_complete==null?'':' — '+x.percent_complete+'%'))})});
    var f=$("f-desc");if(f)f.value=out.join(NL);
  }
  function updatePcsReadiness(){
    if(!ACTIVE)return;syncLegacyDescription();
    function has(id){var e=$(id);return !!(e&&String(e.value||'').trim())}
    var locationReady=BLOCKS.filter(function(b){return b.submitted}).length;
    var locationContent=BLOCKS.filter(function(b){return (b.state.today||[]).some(function(x){return (x.description||'').trim()&&x.percent_complete!=null&&x.percent_complete>=0&&x.percent_complete<=100})}).length;
    var sig=$("sigimg"),checks=[
      [has("f-project")&&has("f-item"),"Project particulars"],
      [BLOCKS.length>0&&locationContent===BLOCKS.length,"Location activities ("+locationContent+"/"+BLOCKS.length+")"],
      [BLOCKS.length>0&&locationReady===BLOCKS.length,"Locations submitted ("+locationReady+"/"+BLOCKS.length+")"],
      [document.querySelectorAll("#mp tr").length>0,"Manpower"],
      [document.querySelectorAll("#photos .photo").length>0,"Activity photos"],
      [has("f-prep"),"Prepared by"],
      [!!(sig&&sig.src&&!sig.classList.contains("hidden")),"Signature"]
    ];
    var done=checks.filter(function(x){return x[0]}).length,pct=Math.round(done/checks.length*100),pc=$("dpr-percent"),fill=$("dpr-meter-fill"),box=$("dpr-checks"),ds=$("dpr-draftstate");
    if(pc)pc.textContent=pct+"% complete";if(fill)fill.style.width=pct+"%";if(ds)ds.textContent=locationReady===BLOCKS.length&&BLOCKS.length?"PCS locations ready":"PCS draft";
    if(box)box.innerHTML=checks.map(function(x){return '<div class="dpr-check"><span>'+esc(x[1])+'</span><b class="'+(x[0]?'dpr-ok':'dpr-miss')+'">'+(x[0]?'Ready':'Missing')+'</b></div>'}).join('');
    var miss=$("dpr-missing-wrap");if(miss)miss.style.display="none";
  }
  async function flushPending(){if(!ACTIVE||!navigator.onLine)return;for(var i=0;i<BLOCKS.length;i++){var b=BLOCKS[i];if(b.state._pendingSubmit&&!b.submitted&&!b.busy)await submitBlock(b.loc,b.state,b.box,b)}}

  window.vcmsPcsDpr={isActive:function(){return ACTIVE},updateReadiness:updatePcsReadiness};
  window.addEventListener("online",function(){setTimeout(flushPending,500)});

  function hook(){var s=$("site"),d=$("date");if(s)s.addEventListener("change",refresh);if(d)d.addEventListener("change",refresh);var main=$("dpr-main");if(main){main.addEventListener("input",function(){if(ACTIVE)updatePcsReadiness()});main.addEventListener("change",function(){if(ACTIVE)updatePcsReadiness()})}/* Reference data can arrive slowly on 4G/cold start. Recheck without requiring the supervisor to change the site manually. */[600,1600,3500].forEach(function(ms){setTimeout(refresh,ms)})}
  if(document.readyState!=="loading")hook();else document.addEventListener("DOMContentLoaded",hook);
})();
