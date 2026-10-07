/* Account-free capability link. Token stays in the URL fragment and request header. */
(async()=>{
  const $=id=>document.getElementById(id),T=window.Tipper,token=location.hash.slice(1),base=VMMS_CONFIG.BACKEND_URL+'/api/v1/equipment/tipper';
  let setup,prepared,file,previewURL='',draft,driverID='';
  const status=s=>$('status').textContent=s;
  async function call(path,options={}) {
    const r=await fetch(base+path,{...options,headers:{'X-Tipper-Link':token,...(driverID?{'X-Tipper-Driver':driverID}:{}),...options.headers},cache:'no-store'});
    const data=await r.json().catch(()=>({})); if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Check the details and try again');return data;
  }
  async function history(){if(!setup?.driver)return;try{const rows=await call('/driver/status');$('submission-history').classList.remove('hidden');$('history-lines').innerHTML=rows.map(r=>'<p>'+T.esc(r.date)+' · '+[r.approved?r.approved+' Approved':'',r.pending?r.pending+' Pending Review':'',r.rejected?r.rejected+' Rejected':''].filter(Boolean).join(' · ')+'</p>').join('')||'<p class="hint">No submitted sheets yet.</p>';}catch(e){$('history-lines').textContent=e.message;}}
  $('refresh-history').onclick=history;setInterval(()=>{if(!document.hidden)history();},30000);
  function toggleMode(){const trip=$('mode').value==='trip';$('timing-fields').classList.toggle('hidden',trip);$('trip-fields').classList.toggle('hidden',!trip);for(const n of ['start_time','end_time'])$('confirm-form').elements[n].required=!trip;}
  function siteRules(){const selected=$('site').selectedOptions[0];return setup.sites.filter(r=>r.client_id===selected?.dataset.client&&r.site_name===selected?.dataset.site);}
  function modes(){const allowed=new Set(siteRules().map(r=>r.billing_mode));[...$('mode').options].forEach(o=>o.disabled=!allowed.has(o.value));if(!allowed.has($('mode').value))$('mode').value=[...allowed][0]||'';toggleMode();}
  $('site').onchange=modes;$('mode').onchange=toggleMode;
  $('camera').onclick=()=>$('camera-file').click();$('choose').onclick=()=>$('file').click();
  async function selected(f){if(!f)return;file=f;draft=null;$('review').classList.add('hidden');$('photo-checked').checked=false;status('Checking file…');try{
    prepared=await T.prepare(f);if(previewURL)URL.revokeObjectURL(previewURL);previewURL=URL.createObjectURL(prepared.blob);
    $('preview').classList.toggle('hidden',prepared.blob.type==='application/pdf');$('preview').src=previewURL;
    $('file-name').textContent=f.name+' · '+Math.round(prepared.blob.size/1024)+' KB';$('file-preview').classList.remove('hidden');
    $('quality').textContent=prepared.warnings.join('\n');$('quality').classList.toggle('hidden',!prepared.warnings.length);$('read').disabled=!!prepared.warnings.length;
    status(prepared.warnings.length?'Retake a clearer photo before upload.':'Check the full sheet preview, then read the details.');
  }catch(e){prepared=null;status(e.message);}}
  $('file').onchange=e=>selected(e.target.files[0]);$('camera-file').onchange=e=>selected(e.target.files[0]);
  $('read').onclick=async()=>{if(!prepared||!$('photo-checked').checked)return status('Check that the whole sheet is clear before continuing.');if(!$('site').value)return status('Select a client/site first.');$('read').disabled=true;try{
    status('Uploading and reading your sheet…');draft=await call('/driver/preview',{method:'POST',headers:{'Content-Type':prepared.blob.type,'X-File-Name':encodeURIComponent(file.name)},body:prepared.blob});
    if(draft.status!=='draft'){status('This file has already been submitted. Status: '+draft.status);return;}
    const f=$('confirm-form');f.reset();for(const [key,value]of Object.entries(draft.fields||{}))if(f.elements[key])f.elements[key].value=value??'';
    if(!f.elements.truck_no.value)f.elements.truck_no.value=setup.driver.truck_no||'';
    const wt=String(draft.fields.work_type||'').toLowerCase(),mode=wt.includes('trip')?'trip':wt.includes('night')?'night':wt.includes('day')?'day':null;
    if(mode&&siteRules().some(r=>r.billing_mode===mode))$('mode').value=mode;
    toggleMode();const quality=draft.quality_warnings||[],warnings=[...quality,...(draft.warnings||[])];
    $('ocr-warnings').textContent=warnings.join('\n');$('ocr-warnings').classList.toggle('hidden',!warnings.length);$('submit').disabled=!!quality.length;
    $('review').classList.remove('hidden');status(quality.length?'Photo needs a retake. Use Retake below.':'Check every extracted value against your sheet before submitting.');$('review').scrollIntoView({behavior:'smooth'});
  }catch(e){status(e.message);}finally{$('read').disabled=false;}};
  $('retake').onclick=()=>{$('review').classList.add('hidden');$('photo-checked').checked=false;$('camera-file').value='';$('file').value='';$('upload-card').scrollIntoView({behavior:'smooth'});status('Choose a clearer file or take another photo.');};
  $('confirm-form').onsubmit=async e=>{e.preventDefault();if(!draft)return;const form=e.target,data=Object.fromEntries(new FormData(form));
    const selected=$('site').selectedOptions[0],candidates=siteRules().filter(r=>r.billing_mode===$('mode').value&&r.effective_from<=data.trip_date).sort((a,b)=>b.effective_from.localeCompare(a.effective_from));
    if(!candidates.length)return status('No site rate rule exists for this work date. Contact your coordinator.');
    data.site_rule_id=candidates[0].id;data.checked=form.elements.checked.checked;data.quantity=Number(data.quantity||1);data.start_time=data.start_time||null;data.end_time=data.end_time||null;
    $('submit').disabled=true;try{await call('/driver/submissions/'+draft.id+'/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});$('review').classList.add('hidden');$('file-preview').classList.add('hidden');draft=null;prepared=null;status('Submitted successfully — pending coordinator review. The record uses the work date on your sheet.');await history();}catch(err){status(err.message);}finally{$('submit').disabled=false;}
  };
  async function loadSetup(){setup=await call('/driver/setup');if(setup.choose_driver){$('driver-choice').classList.remove('hidden');$('driver-select').innerHTML='<option value="">Choose your name</option>'+setup.drivers.map(d=>'<option value="'+T.esc(d.id)+'">'+T.esc(d.name)+'</option>').join('');$('driver-name').textContent='Driver upload portal';status('Choose your driver name to continue.');return;}$('driver-choice').classList.add('hidden');$('driver-name').textContent=setup.driver.name;const sites=new Map();for(const r of setup.sites)sites.set(r.client_id+'|'+r.site_name,r);
    $('site').innerHTML='<option value="">Choose client / site</option>'+[...sites].map(([key,r])=>'<option value="'+T.esc(key)+'" data-client="'+T.esc(r.client_id)+'" data-site="'+T.esc(r.site_name)+'">'+T.esc((r.client?.name||'Client')+' / '+r.site_name)+'</option>').join('');
    $('upload-card').classList.remove('hidden');await history();status('Welcome. Choose your site, then upload one complete trip sheet.');
  }
  $('driver-continue').onclick=async()=>{driverID=$('driver-select').value;if(!driverID)return status('Choose your driver name.');try{await loadSetup();}catch(e){status(e.message);}};
  try{await loadSetup();}catch(e){status(e.message);}
})();
