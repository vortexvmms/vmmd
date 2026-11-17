'use strict';
requireLogin();
const byId = id => document.getElementById(id);
const root = '/api/v1/store';
const mainStore = 'main';
const today = () => new Date().toLocaleDateString('sv-SE', {timeZone:'Asia/Singapore'});
const fmt = value => value ? value.split('-').reverse().join('/') : '—';
const nullableSite = value => value === mainStore ? null : value;
const readForm = form => Object.fromEntries(new FormData(form));
const shift = (day, days) => {
  const date = new Date(day + 'T00:00:00Z');
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
};
const categories = {
  Machinery:['Excavator','Lorry crane','Mini tipper','10-ft lorry','14-ft lorry','Mini van','Generator','Compaction equipment','Other'],
  Equipment:['Survey instrument','4-in-1 gas meter','Gas detector','Pump','Other'],
  Tool:['Corded power tool','Battery-operated tool','Hand tool','Battery / charger','Other'],
};
const reminderKinds = ['Monthly machinery maintenance','Survey instrument calibration','4-in-1 gas meter calibration',
  'Gas detector calibration','LTA vehicle inspection','Lorry crane LM renewal','Excavator LM renewal','Other service / renewal'];
let store = {locations:[], supervisors:[], stock:[], drivers:[], reminders:[]};
let panel = 'overview', logPage = 0, logParams, logGeneration = 0;
let assetDraft, moveDraft, reminderDraft, completionDraft, driverDraft;
const assetForm = byId('asset-form'), moveForm = byId('move-form'), logForm = byId('log-filter');
const reminderForm = byId('reminder-form'), completeForm = byId('complete-form'), driverForm = byId('driver-form');

async function request(path, method = 'GET', body, raw = false) {
  const options = {method};
  if (body !== undefined) options.body = raw ? body : JSON.stringify(body);
  if (raw) options.headers = {'Content-Type':body.type || 'application/octet-stream'};
  const response = await vmmsApi(root + path, options);
  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).detail; } catch (_) {}
    throw new Error(typeof detail === 'string' ? detail : 'The Store request could not be completed.');
  }
  return raw && method === 'GET' ? response.blob() : response.json();
}
function options(select, values, placeholder, value = '') {
  select.replaceChildren(new Option(placeholder, ''), ...values.map(row => new Option(row.name, row.id)));
  select.value = value;
}
const locations = () => store.can_move ? [{id:mainStore,name:'Main Store'}, ...store.locations] : store.locations;
const categoryOptions = values => values.map(name => ({id:name,name}));
function labelCell(row, label, content, meta) {
  const td = row.insertCell();
  const small = document.createElement('span');
  small.className = 'cell-label';
  small.textContent = label;
  td.append(small, content instanceof Node ? content : String(content ?? '—'));
  if (meta) {
    const sub = document.createElement('span');
    sub.className = 'cell-meta';
    sub.textContent = meta;
    td.append(sub);
  }
  return td;
}
function button(label, action, primary = false) {
  const element = document.createElement('button');
  element.type = 'button';
  element.textContent = label;
  if (primary) element.className = 'primary';
  element.addEventListener('click', action);
  return element;
}
function actions(...buttons) {
  const wrapper = document.createElement('div');
  wrapper.className = 'compact-actions';
  wrapper.append(...buttons.filter(Boolean));
  return wrapper;
}
function selectedStock() {
  const site = byId('store-location').value, category = byId('store-category').value;
  const search = byId('store-search').value.trim().toLowerCase();
  return store.stock.filter(item => (!site || (item.site_id ?? mainStore) === site)
    && (!category || item.category === category)
    && (!search || [item.name,item.code,item.model,item.brand,item.serial_number,item.registration_number,item.equipment_type]
      .some(value => String(value ?? '').toLowerCase().includes(search))));
}
function renderStock() {
  const tbody = byId('stock-rows');
  tbody.replaceChildren();
  const rows = selectedStock();
  byId('stock-count').textContent = rows.length ? rows.length + ' stock records' : 'No matching equipment.';
  const selected = byId('store-location').value;
  byId('confirm-stock').hidden = !locations().some(row => row.id === selected);
  for (const item of rows) {
    const row = tbody.insertRow();
    labelCell(row,'Asset code',item.code);
    labelCell(row,'Description',item.name,[item.category,item.equipment_type].filter(Boolean).join(' · '));
    labelCell(row,'Brand / model',[item.brand,item.model].filter(Boolean).join(' · ') || '—');
    labelCell(row,'Serial / vehicle',[item.serial_number,item.registration_number,item.lm_reference].filter(Boolean).join(' · ') || '—');
    labelCell(row,'Location',item.location);
    labelCell(row,'Qty',item.quantity);
    labelCell(row,'Condition',item.condition);
    labelCell(row,'Remarks',item.notes || '—');
    const dates=[['Purchased',item.purchase_date],['Maintenance',item.last_maintenance],['Calibration',item.last_calibration],['Repair',item.last_repair]];
    labelCell(row,'Service dates',dates.filter(([,date])=>date).map(([name,date])=>name+' '+fmt(date)).join(' · ') || '—');
    labelCell(row,'Updated',fmt(item.updated_at?.slice(0,10)));
    labelCell(row,'Action',actions(button('Edit',()=>openAsset(item)),button('Photos',()=>openPhotos('asset',item.id)),
      store.can_move && button('Move',()=>openMove(item),true)));
  }
}
function notice(message) { byId('store-notice').textContent = message; }
async function refresh() {
  store = await request('/register');
  const filter = byId('store-location');
  const historySite = logForm.elements.location;
  const stockLocations = [...new Map([...locations(), ...store.stock.map(item => ({
    id:item.site_id ?? mainStore, name:item.location,
  }))].map(item => [item.id,item])).values()];
  options(filter,stockLocations,'All locations',filter.value);
  options(historySite,stockLocations,'All locations',historySite.value);
  byId('add-asset').disabled = !locations().length;
  byId('add-reminder').disabled = !store.stock.length;
  byId('manage-drivers').hidden = !store.can_manage_drivers;
  renderStock();
  renderOverview();
}
function openAsset(item) {
  assetDraft = item || {id:crypto.randomUUID()};
  assetForm.reset();
  options(assetForm.elements.site,locations(),'Select location',item?.site_id ?? (item ? mainStore : ''));
  assetForm.elements.site.disabled = Boolean(item);
  assetForm.elements.quantity.disabled = Boolean(item);
  for (const name of ['code','name','category','brand','model','serial_number','registration_number','ownership',
    'lm_reference','meter_reading','condition','purchase_date','last_maintenance','last_calibration','last_repair','notes']) {
    if (item) assetForm.elements[name].value = item[name] ?? '';
  }
  if (item) assetForm.elements.quantity.value = item.quantity;
  fillTypes(item?.equipment_type);
  byId('asset-title').textContent = item ? 'Edit equipment' : 'Add equipment';
  byId('asset-error').textContent = '';
  byId('asset-dialog').showModal();
}
function fillTypes(value = '') {
  const items = categories[assetForm.elements.category.value] || [];
  const choices = value && !items.includes(value) ? [...items,value] : items;
  options(assetForm.elements.equipment_type,categoryOptions(choices),'Choose a type',value);
}
function openMove(item) {
  moveDraft = {id:crypto.randomUUID(), item};
  moveForm.reset();
  const source = item.site_id ?? mainStore;
  options(moveForm.elements.destination,locations().filter(row => row.id !== source),'Choose destination');
  options(moveForm.elements.received,store.supervisors,'Choose supervisor');
  options(moveForm.elements.requested,store.supervisors,'Optional');
  options(moveForm.elements.handed_over,store.drivers.map(driver=>({id:driver.name,name:driver.name})),'Optional');
  moveForm.elements.date.value = moveForm.elements.date.max = today();
  moveForm.elements.quantity.max = Math.min(item.quantity,9999);
  moveForm.elements.quantity.value = Math.min(item.quantity,9999);
  byId('move-context').textContent = item.name + ' · ' + item.location + ' · ' + item.quantity + ' available';
  byId('move-error').textContent = '';
  byId('move-dialog').showModal();
}
function submit(form, errorId, task) {
  form.closest('dialog').addEventListener('cancel',event=>{
    if(form.querySelector('[type=submit]').disabled) event.preventDefault();
  });
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const submitButton = form.querySelector('[type=submit]');
    if(submitButton.disabled) return;
    submitButton.disabled = true;
    byId(errorId).textContent = '';
    const closeButtons = [...form.querySelectorAll('[data-close]')];
    for (const control of closeButtons) control.disabled=true;
    try { await task(readForm(form)); }
    catch (error) { byId(errorId).textContent = error.message; }
    finally { submitButton.disabled=false;for(const control of closeButtons) control.disabled=false; }
  });
}
function refreshAfterSave(message) {
  notice(message);
  refresh().catch(error=>notice(message+' Refresh failed. '+error.message));
  loadRecent();
  if(panel==='movements') loadLog();
}
submit(assetForm,'asset-error',async fields=>{
  const {site,quantity,...asset} = fields;
  for(const name of ['purchase_date','last_maintenance','last_repair','last_calibration']) asset[name] ||= null;
  const exists = Boolean(assetDraft.code);
  asset.code=asset.code.trim() || 'EQ-'+assetDraft.id.slice(0,13).toUpperCase();
  const result = exists ? await request('/assets/'+assetDraft.id,'PUT',asset) : await request('/assets','POST',{
    id:assetDraft.id,site:nullableSite(site),quantity:Number(quantity),asset,
  });
  byId('asset-dialog').close();
  refreshAfterSave('Equipment saved.');
  if(!exists && store.photos_enabled) openPhotos('asset',result.id);
});
submit(moveForm,'move-error',async fields=>{
  const item = moveDraft.item;
  const result = await request('/movements','POST',{
    id:moveDraft.id,asset:item.id,from_site:item.site_id,to_site:nullableSite(fields.destination),
    quantity:Number(fields.quantity),date:fields.date,received:fields.received,
    requested:fields.requested || null,handed_over:fields.handed_over,notes:fields.notes,
  });
  byId('move-dialog').close();
  refreshAfterSave('Movement recorded.');
  if(store.photos_enabled) openPhotos('movement',result.id);
});
byId('confirm-stock').addEventListener('click',async ()=>{
  const control = byId('confirm-stock');
  const selected = byId('store-location').value;
  const rows = store.stock.filter(item => (item.site_id ?? mainStore) === selected);
  if(!window.confirm(rows.length?'Confirm the physical count for this location?':'Confirm this location has no equipment?')) return;
  control.disabled = true;
  try {
    const result = await request('/counts','POST',{id:crypto.randomUUID(),site:nullableSite(selected),
      quantities:Object.fromEntries(rows.map(item=>[item.id,item.quantity]))});
    notice('Physical count confirmed by '+result.verified_by+'.');
  } catch(error) { notice(error.message); }
  finally { control.disabled = false; }
});
byId('add-asset').addEventListener('click',()=>openAsset());
assetForm.elements.category.addEventListener('change',()=>fillTypes());
for(const name of ['store-location','store-category','store-search']) byId(name).addEventListener('input',renderStock);

function logFilters(){
  const fields = readForm(logForm);
  return {date_from:fields.start,date_to:fields.end,location:fields.location,movement_type:fields.type,search:fields.search};
}
async function logRequest(params,page=0) {
  return request('/movements?'+new URLSearchParams({...params,page}));
}
async function loadLog(){
  const generation = ++logGeneration;
  byId('movement-count').textContent = 'Loading movements…';
  byId('movement-rows').replaceChildren();
  byId('movement-metrics').replaceChildren();
  byId('previous-page').disabled = byId('next-page').disabled = true;
  try {
    const result = await logRequest(logParams,logPage);
    if(generation!==logGeneration) return;
    const tbody = byId('movement-rows');
    const totals = result.rows[0] || {};
    for (const [field,label] of Object.entries({movement_count:'Movements',units_moved:'Units moved',issues:'Store issues',returns:'Returns',transfers:'Site transfers'})) {
      const metric=document.createElement('div'), value=document.createElement('strong');
      value.textContent=totals[field] ?? 0;
      metric.append(label,value);
      byId('movement-metrics').append(metric);
    }
    for(const move of result.rows){
      const row = tbody.insertRow();
      labelCell(row,'Date',fmt(move.moved_on),move.type);
      labelCell(row,'Equipment',move.name,move.code);
      labelCell(row,'Route',move.from_name+' → '+move.to_name);
      labelCell(row,'Quantity',move.quantity);
      const handover= labelCell(row,'Handover',move.receiver_name,[move.handed_over,move.requester_name,move.notes].filter(Boolean).join(' · '));
      handover.append(button('Photos',()=>openPhotos('movement',move.id)));
    }
    byId('movement-count').textContent = result.rows.length ? 'Page '+(logPage+1) : 'No movements match these filters.';
    byId('previous-page').disabled = !logPage;
    byId('next-page').disabled = !result.has_more;
  } catch(error) { if(generation===logGeneration) byId('movement-count').textContent = error.message; }
}
function loadRecent(){
  logRequest({date_from:shift(today(),-30),date_to:today()}).then(({rows})=>summaryList('recent-movements',
    rows.slice(0,5).map(row=>[row.name,fmt(row.moved_on)+' · '+row.from_name+' → '+row.to_name]),'No movements in the last 30 days.'))
    .catch(error=>summaryList('recent-movements',[],error.message));
}
logForm.elements.end.value = today();
logForm.elements.start.value = shift(today(),-6);
logForm.addEventListener('submit',event=>{
  event.preventDefault();logParams=logFilters();logPage=0;loadLog();
});
byId('previous-page').addEventListener('click',()=>{if(logPage) logPage--;loadLog();});
byId('next-page').addEventListener('click',()=>{logPage++;loadLog();});
for(const key of ['overview','stock','movements']){
  byId(key+'-tab').addEventListener('click',()=>{
    panel=key;
    for(const name of ['overview','stock','movements']){
      byId(name+'-panel').hidden=name!==key;
      byId(name+'-tab').setAttribute('aria-pressed',String(name===key));
    }
    if(key==='movements'){
      logParams=logFilters();logPage=0;loadLog();
    }
  });
}

function summaryList(id, rows, empty){
  const list=byId(id);
  list.replaceChildren();
  for(const [name,detail] of rows.length ? rows : [[empty,'']]){
    const row=document.createElement('li');
    const caption=document.createElement('small');
    caption.textContent=detail;
    row.append(name,caption);
    list.append(row);
  }
}
const reminderStatus=byId('reminder-filter');
const thresholds={overdue:'Overdue',soon:'Due in 7 days',upcoming:'Due in 8–30 days',service:'Out for service'};
function matchesReminder(row,status,day=today()){
  if(status==='closed') return row.status==='Completed';
  if(row.status==='Completed') return false;
  if(status==='service') return row.status==='Out for service';
  if(status==='overdue') return row.due<day;
  if(status==='soon') return row.due>=day && row.due<=shift(day,7);
  if(status==='upcoming') return row.due>shift(day,7) && row.due<=shift(day,30);
  return true;
}
function renderOverview(){
  const rows=byId('my-reminders').checked ? store.reminders.filter(row=>row.assignee===store.actor_id) : store.reminders;
  const metrics=byId('store-metrics');
  metrics.replaceChildren();
  const day=today();
  for(const [key,label] of Object.entries(thresholds)){
    const metric=button(label,()=>{reminderStatus.value=reminderStatus.value===key?'':key;renderOverview();});
    metric.setAttribute('aria-pressed',String(reminderStatus.value===key));
    const total=document.createElement('strong');
    total.textContent=String(rows.filter(row=>matchesReminder(row,key,day)).length);
    metric.append(total);
    metrics.append(metric);
  }
  const tbody=byId('reminder-rows');
  tbody.replaceChildren();
  for(const item of rows.filter(row=>matchesReminder(row,reminderStatus.value,day))){
    const row=tbody.insertRow();
    const at=[...new Set(store.stock.filter(asset=>asset.id===item.asset_id).map(asset=>asset.location))];
    labelCell(row,'Equipment',item.asset_name,item.asset_code+' · '+at.join(', '));
    labelCell(row,'Required action',item.kind,item.reference);
    labelCell(row,'Due date',fmt(item.due));
    labelCell(row,'Responsible person',item.assignee_name || 'Unassigned');
    const noticeDays=/renewal|inspection/i.test(item.kind)?[30,14,7]:[14,7,1];
    const alert=noticeDays.some(days=>item.due===shift(day,days));
    const due=item.due<day?'Overdue':item.due===day?'Due today':alert?'Reminder today':item.due<=shift(day,7)?'Due soon':'';
    labelCell(row,'Status',item.status,item.status==='Completed'?'':due);
    labelCell(row,'Action',actions(button(item.status==='Completed'?'History':'Edit / history',()=>openReminder(item)),
      item.status!=='Completed' && button('Complete',()=>openCompletion(item),true)));
  }
  if(!tbody.rows.length) labelCell(tbody.insertRow(),'Reminders','No matching reminders.').colSpan=6;
  const inventory=new Map();
  for(const item of store.stock) inventory.set(item.location,(inventory.get(item.location) || 0)+item.quantity);
  summaryList('stock-by-location',[...inventory.entries()].map(([name,qty])=>[name,qty+' units']),'No equipment registered.');
}
function openReminder(item){
  reminderDraft=item || {id:crypto.randomUUID()};
  reminderForm.reset();
  const assets=[...new Map(store.stock.map(row=>[row.id,{id:row.id,name:row.code+' · '+row.name}])).values()];
  options(reminderForm.elements.asset,assets,'Choose equipment',item?.asset_id);
  options(reminderForm.elements.kind,categoryOptions(reminderKinds),'Choose action',item?.kind);
  options(reminderForm.elements.assignee,store.supervisors,'Unassigned',item?.assignee);
  for(const field of ['due','status','reference']) if(item) reminderForm.elements[field].value=item[field] ?? '';
  reminderForm.elements.asset.disabled=Boolean(item);
  byId('save-reminder').hidden=item?.status==='Completed';
  byId('reminder-error').textContent='';
  summaryList('reminder-history',(item?.history || []).map(row=>[fmt(row.done)+' · '+row.by,row.reference || '']),'No completion history.');
  byId('reminder-dialog').showModal();
}
function nextMonth(day){
  const date = new Date(day+'T00:00:00Z');
  const wanted=date.getUTCDate();
  date.setUTCDate(1);date.setUTCMonth(date.getUTCMonth()+1);
  const end=new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,0)).getUTCDate();
  date.setUTCDate(Math.min(end,wanted));
  return date.toISOString().slice(0,10);
}
function openCompletion(item){
  completionDraft={id:item.id,completion:crypto.randomUUID(),kind:item.kind};
  completeForm.reset();
  completeForm.elements.done.value=completeForm.elements.done.max=today();
  completeForm.elements.next.value=item.kind===reminderKinds[0]?nextMonth(today()):'';
  byId('complete-error').textContent='';
  byId('complete-dialog').showModal();
}
completeForm.elements.done.addEventListener('change',()=>{
  if(completionDraft?.kind===reminderKinds[0] && completeForm.elements.done.value){
    completeForm.elements.next.value=nextMonth(completeForm.elements.done.value);
  }
});
byId('add-reminder').addEventListener('click',()=>openReminder());
reminderStatus.addEventListener('change',renderOverview);
byId('my-reminders').addEventListener('change',renderOverview);
submit(reminderForm,'reminder-error',async fields=>{
  await request('/reminders','POST',{...fields,id:reminderDraft.id,asset:reminderDraft.asset_id || fields.asset,assignee:fields.assignee || null});
  byId('reminder-dialog').close();
  refreshAfterSave('Reminder saved.');
});
submit(completeForm,'complete-error',async fields=>{
  await request('/reminders/'+completionDraft.id+'/complete','POST',{...fields,completion:completionDraft.completion,next:fields.next || null});
  byId('complete-dialog').close();
  if(!fields.next) reminderStatus.value='closed';
  refreshAfterSave('Service completion recorded.');
});
function renderDrivers(){
  const list=byId('driver-list');
  list.replaceChildren();
  for(const driver of store.drivers){
    const row=document.createElement('li');
    row.append(driver.name,actions(button('Rename',()=>{driverDraft=driver;driverForm.elements.name.value=driver.name;driverForm.elements.name.focus();}),
      button('Archive',async ()=>{
        if(!window.confirm('Archive '+driver.name+' from the driver list?')) return;
        try{
          await request('/drivers','POST',{id:driver.id,name:driver.name,active:false});
          await refreshDrivers();
        }catch(error){byId('driver-error').textContent=error.message;}
      })));
    list.append(row);
  }
}
async function refreshDrivers(){
  const current=moveForm.elements.handed_over.value;
  await refresh();
  options(moveForm.elements.handed_over,store.drivers.map(row=>({id:row.name,name:row.name})),'Optional',current);
  renderDrivers();
}
byId('manage-drivers').addEventListener('click',()=>{
  driverDraft={id:crypto.randomUUID()};driverForm.reset();
  byId('driver-error').textContent='';
  renderDrivers();
  byId('driver-dialog').showModal();
});
submit(driverForm,'driver-error',async fields=>{
  await request('/drivers','POST',{id:driverDraft.id,name:fields.name,active:true});
  await refreshDrivers();
  driverForm.reset();driverDraft={id:crypto.randomUUID()};
});
for(const control of document.querySelectorAll('[data-close]')) control.addEventListener('click',()=>control.closest('dialog').close());

let photoTarget, photoURLs=[], photoQueue=[];
const photoDialog=byId('photo-dialog'), photoNotice=byId('photo-notice');
function photoQuery(target){return new URLSearchParams({[target.kind]:target.id}).toString();}
function resetPhotoURLs(){
  for(const url of photoURLs) URL.revokeObjectURL(url);
  photoURLs=[];
}
function openPhotos(kind,id){
  photoTarget={kind,id};
  photoQueue=[];
  resetPhotoURLs();
  byId('store-photos').replaceChildren();
  byId('photo-paste-label').hidden=true;
  byId('photo-upload').hidden=!store.photos_enabled || (kind==='movement' && !store.can_move);
  photoNotice.textContent='Loading photos…';
  photoDialog.showModal();
  loadPhotos(photoTarget);
}
async function loadPhotos(target){
  try{
    const list=await request('/photos?'+photoQuery(target));
    if(target!==photoTarget) return;
    resetPhotoURLs();
    const gallery=byId('store-photos');
    gallery.replaceChildren();
    photoNotice.textContent=list.length?'':'No photos attached.';
    for(const {id} of list){
      const blob=await request('/photos/'+id,'GET',undefined,true);
      if(target!==photoTarget) return;
      const url=URL.createObjectURL(blob);
      photoURLs.push(url);
      const image=document.createElement('img');
      image.src=url;image.alt='Equipment or handover photo';
      gallery.append(image);
    }
    if(photoQueue.length) photoNotice.textContent+=' '+photoQueue.length+' photo(s) awaiting retry.';
  }catch(error){if(target===photoTarget) photoNotice.textContent=error.message;}
}
async function preparePhoto(file){
  if(!file || file.size>30*1024*1024) throw new Error('Choose a photo up to 30 MB.');
  let bitmap;
  try { bitmap=await createImageBitmap(file); }
  catch (_) { throw new Error('This photo could not be opened. Choose a JPEG, PNG or WebP image.'); }
  try{
    const ratio=Math.min(1,1600/Math.max(bitmap.width,bitmap.height));
    const canvas=document.createElement('canvas');
    canvas.width=Math.max(1,Math.round(bitmap.width*ratio));
    canvas.height=Math.max(1,Math.round(bitmap.height*ratio));
    const context=canvas.getContext('2d',{alpha:false});
    context.fillStyle='#fff';context.fillRect(0,0,canvas.width,canvas.height);
    context.drawImage(bitmap,0,0,canvas.width,canvas.height);
    return await new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('Photo could not be converted.')),'image/jpeg',0.8));
  }finally{bitmap.close();}
}
let uploading=false;
async function uploadPhotos(files=[]){
  const target=photoTarget;
  if(uploading || !target || byId('photo-upload').hidden) return;
  uploading=true;
  try{
    byId('retry-photos').hidden=true;
    photoNotice.textContent='Saving photos…';
    for(const file of files){
      if(photoQueue.length>=4) break;
      const blob=await preparePhoto(file);
      if(target!==photoTarget) return;
      photoQueue.push({id:crypto.randomUUID(),blob});
    }
    while(photoQueue.length && target===photoTarget){
      const photo=photoQueue[0];
      await request('/photos/'+photo.id+'?'+photoQuery(target),'PUT',photo.blob,true);
      if(target!==photoTarget) return;
      photoQueue.shift();
    }
    if(target===photoTarget) await loadPhotos(target);
  }catch(error){
    if(target===photoTarget){
      photoNotice.textContent=error.message;
      byId('retry-photos').hidden=!photoQueue.length;
    }
  }finally{uploading=false;}
}
byId('retry-photos').addEventListener('click',()=>uploadPhotos());
photoDialog.addEventListener('close',()=>{photoTarget=null;resetPhotoURLs();byId('retry-photos').hidden=true;});
for(const [control,input] of [['photo-camera','store-camera-input'],['photo-files','store-file-input']]){
  byId(control).addEventListener('click',()=>byId(input).click());
  byId(input).addEventListener('change',event=>{uploadPhotos([...event.target.files]);event.target.value='';});
}
byId('photo-paste').addEventListener('click',async ()=>{
  try{
    const items=await navigator.clipboard.read();
    for(const item of items){
      const mime=item.types.find(type=>type.startsWith('image/'));
      if(mime){uploadPhotos([await item.getType(mime)]);return;}
    }
  }catch(_){}
  byId('photo-paste-label').hidden=false;
  byId('photo-paste-target').focus();
});
byId('photo-upload').addEventListener('paste',event=>{
  const files=[...event.clipboardData.files].filter(file=>file.type.startsWith('image/'));
  if(files.length){event.preventDefault();uploadPhotos(files);}
});
byId('photo-upload').addEventListener('dragover',event=>{event.preventDefault();event.currentTarget.classList.add('dragging');});
byId('photo-upload').addEventListener('dragleave',event=>event.currentTarget.classList.remove('dragging'));
byId('photo-upload').addEventListener('drop',event=>{
  event.preventDefault();event.currentTarget.classList.remove('dragging');uploadPhotos([...event.dataTransfer.files]);
});

async function completeLog(params){
  const rows=[];
  for(let page=0;page<=1000;page++){
    const result=await logRequest(params,page);
    rows.push(...result.rows);
    if(!result.has_more) return rows;
  }
  throw new Error('Narrow the date range to export this report.');
}
async function buildWhatsApp(){
  const date=byId('whatsapp-date').value;
  const preview=byId('whatsapp-message'), link=byId('whatsapp-link'), copy=byId('whatsapp-copy');
  copy.disabled=true;link.hidden=true;preview.value='';
  if(!date || date>today()) return;
  byId('whatsapp-notice').textContent='Preparing update…';
  try{
    const rows=await completeLog({date_from:date,date_to:date});
    if(byId('whatsapp-date').value!==date) return;
    const units=rows.reduce((sum,row)=>sum+row.quantity,0);
    const lines=['*VCMS | Daily Equipment Movement Update*',fmt(date),''];
    if(!rows.length) lines.push('No equipment movements recorded.');
    else {
      lines.push('Movements: '+rows.length+' | Units moved: '+units,'');
      for(const row of rows){
        lines.push(row.name+' ('+row.code+') × '+row.quantity,row.type+': '+row.from_name+' → '+row.to_name);
        const people=[row.requester_name && 'Requested: '+row.requester_name,row.handed_over && 'Handed over: '+row.handed_over,
          row.receiver_name && 'Received: '+row.receiver_name].filter(Boolean);
        if(people.length) lines.push(people.join(' | '));
        if(row.notes) lines.push('Remark: '+row.notes);
        lines.push('');
      }
    }
    if(byId('whatsapp-reminders').checked){
      lines.push('','*Service & Renewals*');
      const due=store.reminders.filter(row=>row.status!=='Completed' && row.due<=shift(date,7));
      if(!due.length) lines.push('No reminders overdue or due in the next 7 days.');
      for(const row of due) lines.push(row.asset_code+' · '+row.kind+' · '+fmt(row.due)+(row.due<date?' (overdue)':''));
    }
    preview.value=lines.join('\n').trim();
    link.href='https://wa.me/?text='+encodeURIComponent(preview.value);
    link.hidden=false;copy.disabled=false;byId('whatsapp-notice').textContent='';
  }catch(error){byId('whatsapp-notice').textContent=error.message;}
}
byId('whatsapp-open').addEventListener('click',()=>{
  byId('whatsapp-date').value=byId('whatsapp-date').max=today();
  byId('whatsapp-dialog').showModal();buildWhatsApp();
});
for(const name of ['whatsapp-date','whatsapp-reminders']) byId(name).addEventListener('change',buildWhatsApp);
byId('whatsapp-copy').addEventListener('click',async ()=>{
  const message=byId('whatsapp-message');
  try{await navigator.clipboard.writeText(message.value);byId('whatsapp-notice').textContent='Message copied.';}
  catch(_){message.focus();message.select();byId('whatsapp-notice').textContent='Message selected. Use your device’s Copy command.';}
});

function xmlText(value) {
  return String(value ?? '').replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFE\uFFFF]/g,'')
    .replace(/[&<>]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[char]));
}
const crcTable = Uint32Array.from({length:256},(_,index)=>{
  let value=index;
  for(let bit=0;bit<8;bit++) value=(value&1)?0xEDB88320^(value>>>1):value>>>1;
  return value>>>0;
});
function zipWorkbook(files) {
  const encoder=new TextEncoder();
  const chunks=[],directory=[];
  let offset=0,centralSize=0;
  for (const [path,body] of Object.entries(files)) {
    const name=encoder.encode(path),data=encoder.encode(body);
    let crc=0xFFFFFFFF;
    for (const byte of data) crc=crcTable[(crc^byte)&255]^(crc>>>8);
    crc=(crc^0xFFFFFFFF)>>>0;
    const local=new Uint8Array(30+name.length);
    const l=new DataView(local.buffer);
    l.setUint32(0,0x04034b50,true);l.setUint16(4,20,true);l.setUint16(12,33,true);
    l.setUint32(14,crc,true);l.setUint32(18,data.length,true);l.setUint32(22,data.length,true);
    l.setUint16(26,name.length,true);local.set(name,30);
    const central=new Uint8Array(46+name.length);
    const c=new DataView(central.buffer);
    c.setUint32(0,0x02014b50,true);c.setUint16(4,20,true);c.setUint16(6,20,true);c.setUint16(14,33,true);
    c.setUint32(16,crc,true);c.setUint32(20,data.length,true);c.setUint32(24,data.length,true);
    c.setUint16(28,name.length,true);c.setUint32(42,offset,true);central.set(name,46);
    chunks.push(local,data);directory.push(central);
    offset+=local.length+data.length;centralSize+=central.length;
  }
  const end=new Uint8Array(22),e=new DataView(end.buffer);
  e.setUint32(0,0x06054b50,true);e.setUint16(8,directory.length,true);e.setUint16(10,directory.length,true);
  e.setUint32(12,centralSize,true);e.setUint32(16,offset,true);
  return new Blob([...chunks,...directory,end],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
}
function makeWorkbook({headings,rows}) {
  const main='http://schemas.openxmlformats.org/spreadsheetml/2006/main';
  const rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships';
  const pack='http://schemas.openxmlformats.org/package/2006/relationships';
  const cells=[headings,...rows].map((row,i)=>{
    const entries=row.map((value,j)=>{
      const ref=String.fromCharCode(65+j)+(i+1);
      return typeof value==='number' && Number.isFinite(value)
        ? '<c r="'+ref+'"><v>'+value+'</v></c>'
        : '<c r="'+ref+'" t="inlineStr"><is><t xml:space="preserve">'+xmlText(value)+'</t></is></c>';
    }).join('');
    return '<row r="'+(i+1)+'">'+entries+'</row>';
  }).join('');
  const columns=headings.map((heading,i)=>{
    const size=rows.reduce((max,row)=>Math.max(max,String(row[i] ?? '').length),heading.length);
    return '<col min="'+(i+1)+'" max="'+(i+1)+'" width="'+Math.min(45,size+3)+'" customWidth="1"/>';
  }).join('');
  return zipWorkbook({
    '[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
    '_rels/.rels':'<Relationships xmlns="'+pack+'"><Relationship Id="rId1" Type="'+rel+'/officeDocument" Target="xl/workbook.xml"/></Relationships>',
    'xl/workbook.xml':'<workbook xmlns="'+main+'" xmlns:r="'+rel+'"><sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>',
    'xl/_rels/workbook.xml.rels':'<Relationships xmlns="'+pack+'"><Relationship Id="rId1" Type="'+rel+'/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
    'xl/worksheets/sheet1.xml':'<worksheet xmlns="'+main+'"><cols>'+columns+'</cols><sheetData>'+cells+'</sheetData><autoFilter ref="A1:'+String.fromCharCode(64+headings.length)+(rows.length+1)+'"/></worksheet>'
  });
}

async function report(kind){
  if(kind==='stock') return {title:'Equipment Register',headings:['Asset code','Equipment','Category','Type','Brand','Model','Serial',
    'Vehicle registration','LM reference','Location','Quantity','Condition','Last maintenance','Last calibration','Remarks'],
    rows:selectedStock().map(row=>[row.code,row.name,row.category,row.equipment_type,row.brand,row.model,row.serial_number,
      row.registration_number,row.lm_reference,row.location,row.quantity,row.condition,row.last_maintenance,row.last_calibration,row.notes])};
  const rows=await completeLog(logParams || logFilters());
  return {title:'Equipment Movement Log',headings:['Date','Asset code','Equipment','From','To','Type','Quantity','Handed over by','Received by','Requested by','Remarks'],
    rows:rows.map(row=>[row.moved_on,row.code,row.name,row.from_name,row.to_name,row.type,row.quantity,row.handed_over,
      row.receiver_name,row.requester_name,row.notes])};
}
function printReport(report){
  const container=byId('print-report'), title=document.createElement('h1'), table=document.createElement('table');
  title.textContent='VCMS · '+report.title+' · '+fmt(today());
  const header=table.createTHead().insertRow();
  for(const heading of report.headings){
    const cell=document.createElement('th');cell.scope='col';cell.textContent=heading;header.append(cell);
  }
  const body=table.createTBody();
  for(const values of report.rows){
    const row=body.insertRow();
    for(const value of values) row.insertCell().textContent=value ?? '';
  }
  container.replaceChildren(title,table);
  window.print();
}
for(const control of document.querySelectorAll('[data-export],[data-print]')){
  control.addEventListener('click',async ()=>{
    control.disabled=true;
    try{
      const data=await report(control.dataset.export || control.dataset.print);
      if(!data.rows.length){notice('No matching records to export.');return;}
      if(control.dataset.print) printReport(data);
      else {
        const url=URL.createObjectURL(makeWorkbook(data)),download=document.createElement('a');
        download.href=url;download.download='VCMS-'+data.title.replace(/ /g,'-')+'-'+today()+'.xlsx';download.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
      }
    }catch(error){notice(error.message);}
    finally{control.disabled=false;}
  });
}
refresh().then(()=>notice('')).catch(error=>notice(error.message));
loadRecent();
