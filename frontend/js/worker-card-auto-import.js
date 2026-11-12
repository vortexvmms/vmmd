/* Selected-page scan detection, independent side crops and reviewable matching. */
(function(){'use strict';const Base=window.WorkerCardImporter;
window.WorkerCardImporter=class extends Base {
 constructor(use){super(use);this.candidates=[];this.previewUrls=[];this.cropVersion=0;this.generation=0;
 const layout=this.$('.scan-layout');layout.innerHTML='<aside class="scan-pages" aria-label="All PDF pages"></aside><section class="scan-pairs" aria-label="Detected card pairs"></section>';
 this.$('.scan-front').closest('label').hidden=true;this.$('.scan-back').closest('label').hidden=true;
 for(const a of ['pages','full','create'])this.$('[data-action='+a+']').hidden=true;
 const toolbar=this.$('.scan-file').closest('.wc-toolbar');
 toolbar.classList.add('scan-controls');
 const controls=document.createElement('div');
 controls.className='scan-page-controls';
 controls.innerHTML='<label>PDF page<select class="scan-page" disabled></select></label><label>Detect as<select class="scan-role"><option value="front">Card fronts</option><option value="back">Card backs</option></select></label><button class="primary" data-action="detect" disabled>Detect selected page</button><button data-action="add-crop" disabled>Draw card crop</button>';
 toolbar.after(controls);
 this.$('.scan-page').onchange=()=>this.action('preview-page').catch(e=>this.status(e.message));
 this.dialog.lastElementChild.classList.add('scan-actions');
 this.cropDialog=document.createElement('dialog');this.cropDialog.id='scan-crop-dialog';this.cropDialog.innerHTML='<div class="wc-toolbar"><h2>Adjust crop from original page</h2><button class="crop-close">Cancel</button><button class="crop-full">Use full page</button><button class="crop-apply primary">Apply independent crop</button></div><p>Drag a new box around this card. Adjust edges below. Tilt, rotate, perspective and masking remain available in Edit.</p><div class="crop-fields"></div><div class="crop-stage"><canvas class="crop-original"></canvas></div>';
 document.body.append(this.cropDialog);const fields=this.cropDialog.querySelector('.crop-fields');for(const name of ['x','y','w','h']){const label=document.createElement('label');label.textContent=({x:'Left %',y:'Top %',w:'Width %',h:'Height %'})[name];const input=document.createElement('input');input.type='number';input.min='0';input.max='100';input.step='.1';input.dataset.coord=name;input.oninput=()=>{if(!this.cropTarget)return;const v=Number(input.value)/100;this.cropRect[name]=v;this.cropPaint()};label.append(input);fields.append(label);}
 const canvas=this.cropDialog.querySelector('canvas'),point=e=>{const b=canvas.getBoundingClientRect();return{x:Math.max(0,Math.min(1,(e.clientX-b.left)/b.width)),y:Math.max(0,Math.min(1,(e.clientY-b.top)/b.height))}};
 canvas.onpointerdown=e=>{this.cropStart=point(e);canvas.setPointerCapture(e.pointerId)};canvas.onpointermove=e=>{if(!this.cropStart)return;this.cropRect=this.rectangle(this.cropStart,point(e));this.cropFields();this.cropPaint()};canvas.onpointerup=e=>{if(!this.cropStart)return;this.cropRect=this.rectangle(this.cropStart,point(e));this.cropStart=null;this.cropFields();this.cropPaint()};canvas.onpointercancel=()=>this.cropStart=null;
 this.cropDialog.querySelector('.crop-full').onclick=()=>{this.cropRect={x:0,y:0,w:1,h:1};this.cropFields();this.cropPaint()};this.cropDialog.addEventListener('close',()=>this.pendingCrop=null);this.cropDialog.querySelector('.crop-close').onclick=()=>this.cropDialog.close();this.cropDialog.querySelector('.crop-apply').onclick=async()=>{const r=this.cropRect;if(!r||r.w<.01||r.h<.01||r.x<0||r.y<0||r.x+r.w>1.001||r.y+r.h>1.001){this.status('Keep the crop inside the page with a positive width and height.');return}if(this.pendingCrop){const {ref,item}=this.pendingCrop;this.candidates.push(ref);(this.pageCards[ref.page]??=[]).push(ref);if(item)this.items.push(item);this.pendingCrop=null;}this.cropTarget.rect={...r};this.cropTarget.auto=false;delete this.cropTarget.file;this.invalidate(this.cropItem);this.renderPage(this.cropTarget.page);this.cropDialog.close();await this.renderAsync();};
 this.status('Upload a PDF, choose a page and select Detect selected page.');
 }
 rectangle(a,b){return{x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),w:Math.abs(a.x-b.x),h:Math.abs(a.y-b.y)}}
 invalidate(item){if(!item)return;for(const k of ['front','back','label','institute','expiry_date','text'])delete item[k];item.checked=false;}
 open(w){if(this.worker?.id!==w.id&&this.items.some(i=>!i.saved)&&!confirm('Discard unsaved imported cards for the previous worker?'))return;if(this.worker?.id!==w.id){this.items=[];this.candidates=[];this.pageCards=[];this.pages.clear();this.pdf?.destroy();this.pdf=null;this.current=null;this.$('.scan-file').value='';this.setPages(0);this.status('Upload a PDF, choose a page and select Detect selected page.');this.$('.scan-pages').replaceChildren();this.render();}this.worker=w;this.$('.scan-worker').textContent=w.name+' · '+w.worker_code;this.dialog.showModal();}
 async load(){if(this.busy)return;const f=this.$('.scan-file').files[0];if(!f)return;if(f.size>20971520)throw Error('Choose a PDF up to 20 MB.');if(this.items.some(i=>!i.saved)&&!confirm('Replace this unsaved import batch?'))return;const version=++this.generation;this.busy=true;this.status('Opening scanned PDF…');try{const lib=await import('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs');lib.GlobalWorkerOptions.workerSrc='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs';const doc=await lib.getDocument({data:await f.arrayBuffer(),isEvalSupported:false}).promise;if(version!==this.generation){await doc.destroy();return}if(doc.numPages>30){await doc.destroy();throw Error('Import up to 30 pages at a time. Split larger PDFs.');}await this.pdf?.destroy();this.pdf=doc;this.pages.clear();this.items=[];this.candidates=[];this.pageCards=[];this.deleted=null;this.current=null;this.setPages(doc.numPages);await this.showSelectedPage();await this.renderAsync();this.status(doc.numPages+' pages available. Choose the page and detect as fronts or backs.');}catch(e){this.status('PDF processing could not finish: '+e.message)}finally{this.busy=false;}}
 async page(n){if(!this.pages.has(n)){const p=await this.pdf.getPage(n),v=p.getViewport({scale:1}),viewport=p.getViewport({scale:Math.min(2.5,2400/Math.max(v.width,v.height))}),c=document.createElement('canvas');c.width=Math.ceil(viewport.width);c.height=Math.ceil(viewport.height);await p.render({canvasContext:c.getContext('2d'),viewport}).promise;this.pages.set(n,c);p.cleanup();}return this.pages.get(n)}
 setPages(count){
  const select=this.$('.scan-page');
  select.replaceChildren(...Array.from({length:count},(_,i)=>new Option('Page '+(i+1),i+1)));
  for(const control of [select,this.$('[data-action=detect]'),this.$('[data-action=add-crop]')])control.disabled=!count;
  this.$('.scan-role').value='front';
 }
 async showSelectedPage(){
  const number=Number(this.$('.scan-page').value);
  await this.page(number);
  this.renderPage(number);
 }
 renderPage(number){
  if(number!==Number(this.$('.scan-page').value))return;
  const root=this.$('.scan-pages'),source=this.pages.get(number);
  const title=document.createElement('strong'),thumb=document.createElement('canvas');
  title.textContent='Page '+number+' · '+(this.pageCards[number]?.length||0)+' crops';
  thumb.width=320;thumb.height=Math.round(source.height/source.width*320);
  const context=thumb.getContext('2d');
  context.drawImage(source,0,0,thumb.width,thumb.height);
  for(const [index,ref] of (this.pageCards[number]||[]).entries()){
   const {x,y,w,h}=ref.rect;
   context.strokeStyle='#0077ff';context.lineWidth=2;
   context.strokeRect(x*thumb.width,y*thumb.height,w*thumb.width,h*thumb.height);
   context.fillStyle='#005bbb';context.font='bold 14px sans-serif';
   context.fillText(String(index+1),x*thumb.width+4,y*thumb.height+16);
  }
  root.replaceChildren(title,thumb);
 }
 async detectPage(number,role){
  if(this.pageCards[number])throw Error('This page already has crops. Use the source selectors or Draw card crop to add a missed side.');
  const source=await this.page(number);
  const refs=WorkerCardScanDetect.detect(source).map((rect,i)=>({id:'p'+number+'c'+i,page:number,rect,auto:true,role}));
  if(refs.length)this.pageCards[number]=refs;
  this.candidates.push(...refs);
  if(role==='front')this.items.push(...refs.map(frontRef=>({frontRef,backRef:null,selected:false,checked:false})));
  this.renderPage(number);
  await this.renderAsync();
  this.status(refs.length?refs.length+' crops on page '+number+'. '+(role==='back'?'Choose the correct Back source for each card.':'Review each full crop. Choose a back only when the card has one.'):'No cards detected. Use Draw card crop.');
 }
 async candidateFile(ref){if(!ref)return null;if(ref.file)return ref.file;const source=await this.page(ref.page),raw=await this.crop(source,ref.rect);if(ref.auto){const image=await createImageBitmap(raw);try{const c=document.createElement('canvas');c.width=image.width;c.height=image.height;c.getContext('2d').drawImage(image,0,0);const q=WorkerCardGeometry.detect(c);if(q){const cx=q.reduce((s,p)=>s+p.x,0)/4,cy=q.reduce((s,p)=>s+p.y,0)/4,safe=q.map(p=>({x:Math.max(0,Math.min(1,cx+(p.x-cx)*1.035)),y:Math.max(0,Math.min(1,cy+(p.y-cy)*1.035))}));const flat=await WorkerCardGeometry.flatten(c,safe,null);ref.file=new File([await new Promise(r=>flat.toBlob(r,'image/png'))],'scan-page-'+ref.page+'.png',{type:'image/png'});return ref.file;}}catch{/* Keep the independent crop when straightening is uncertain. */}finally{image.close();}}ref.file=raw;return raw;}
 async prepare(item){item.front=await this.candidateFile(item.frontRef);item.back=await this.candidateFile(item.backRef);return item;}
 render(){if(!this.$('.scan-pairs'))return;void this.renderAsync().catch(e=>this.status(e.message));}
 async renderAsync(){const version=++this.cropVersion;this.previewUrls.forEach(u=>URL.revokeObjectURL(u));this.previewUrls=[];const root=this.$('.scan-pairs');root.replaceChildren();for(const [i,item] of this.items.entries()){if(version!==this.cropVersion)return;const row=document.createElement('article');row.className='scan-pair';const heading=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=!!item.selected;check.disabled=!!item.saved;check.onchange=()=>item.selected=check.checked;heading.append(check,document.createTextNode('Card '+(i+1)+' · '+(item.saved?'Saved':item.checked?'Pair checked':'Check pairing')));row.append(heading);for(const side of ['front','back']){const cell=document.createElement('div'),select=document.createElement('select'),label=document.createElement('label'),preview=document.createElement('img'),adjust=document.createElement('button');label.textContent=side==='front'?'Front source':'Back source';select.setAttribute('aria-label',side+' source for card '+(i+1));select.add(new Option(side==='front'?'No front':'No back',''));for(const c of this.candidates)select.add(new Option('Page '+c.page+' · side '+(this.pageCards[c.page]?.indexOf(c)+1||'?'),c.id));select.value=item[side+'Ref']?.id||'';select.disabled=!!item.saved;select.onchange=async()=>{const ref=this.candidates.find(c=>c.id===select.value)||null;if(ref&&item[(side==='front'?'back':'front')+'Ref']===ref){select.value=item[side+'Ref']?.id||'';this.status('Choose different source sides for the front and back.');return}const owner=ref&&this.items.find(other=>other!==item&&(other.frontRef===ref||other.backRef===ref));if(owner){if(owner.saved||!confirm('This side is assigned to another pair. Exchange it with the current side?')){select.value=item[side+'Ref']?.id||'';return}const ownerSide=owner.frontRef===ref?'frontRef':'backRef';owner[ownerSide]=item[side+'Ref'];this.invalidate(owner);}item[side+'Ref']=ref;this.invalidate(item);await this.renderAsync();};label.append(select);preview.alt=side+' preview for card '+(i+1);const file=await this.candidateFile(item[side+'Ref']);if(version!==this.cropVersion)return;if(file){const url=URL.createObjectURL(file);this.previewUrls.push(url);preview.src=url;}else preview.alt='Missing '+side;adjust.textContent='Adjust '+side+' crop';adjust.disabled=!item[side+'Ref']||!!item.saved;adjust.onclick=()=>this.adjust(item,item[side+'Ref']);cell.append(label,preview,adjust);row.append(cell);}const details=document.createElement('div');details.className='scan-details';for(const [key,title,type] of [['label','Course / card name','text'],['institute','Institute','text'],['expiry_date','Expiry date','date']]){const l=document.createElement('label'),input=document.createElement('input');l.textContent=title;input.type=type;input.value=item[key]||'';input.disabled=!!item.saved;input.oninput=()=>item[key]=input.value;l.append(input);details.append(l);}const reviewed=document.createElement('label'),flag=document.createElement('input');flag.type='checkbox';flag.checked=!!item.checked;flag.disabled=!!item.saved;flag.onchange=()=>{item.checked=flag.checked;heading.lastChild.textContent='Card '+(i+1)+' · '+(flag.checked?'Pair checked':'Check pairing')};reviewed.append(flag,document.createTextNode('Front/back pairing checked'));const read=document.createElement('button');read.type='button';read.textContent='Read card details';read.disabled=!!item.saved||!item.frontRef;read.onclick=()=>this.readCards([item]).catch(e=>this.status(e.message));details.append(reviewed,read);row.append(details);root.append(row);}}
 adjust(item,ref){this.cropTarget=ref;this.cropItem=item;this.cropRect={...ref.rect};this.cropFields();this.cropPaint();this.cropDialog.showModal();}
 cropFields(){for(const input of this.cropDialog.querySelectorAll('[data-coord]'))input.value=(this.cropRect[input.dataset.coord]*100).toFixed(1);}
 cropPaint(){const c=this.cropDialog.querySelector('canvas'),source=this.pages.get(this.cropTarget.page);c.width=source.width;c.height=source.height;const x=c.getContext('2d'),r=this.cropRect;x.drawImage(source,0,0);x.strokeStyle='#006fff';x.lineWidth=5;x.strokeRect(r.x*c.width,r.y*c.height,r.w*c.width,r.h*c.height);}
 async readCards(items){
  if(this.busy)return;
  this.busy=true;
  this.dialog.inert=true;
  try{
   for(const item of items){
    await this.prepare(item);
    const files=[item.front,item.checked?item.back:null].filter(Boolean).map(file=>({file,type:'image/png'}));
    if(!files.length)continue;
    const parts=await SICCardReader.read(files,{onProgress:message=>this.status(message)});
    const fields=WorkerCardFields.read(parts.map(part=>part.text));
    for(const [key,value] of Object.entries(fields))if(!item[key]&&value)item[key]=value;
    item.text=parts.map(part=>part.text).join('\n');
   }
   this.status('Review the suggested course name, institute and expiry. Enter any missing details.');
  }finally{
   this.busy=false;
   this.dialog.inert=false;
   await this.renderAsync();
  }
 }
 async action(action){
  if(this.busy)return;
  if(['detect','preview-page','add-crop'].includes(action)){
   if(!this.pdf)throw Error('Upload a scanned PDF first.');
   const number=Number(this.$('.scan-page').value),role=this.$('.scan-role').value;
   this.busy=true;
   const select=this.$('.scan-page');
   select.disabled=true;
   try{
    if(action==='detect')await this.detectPage(number,role);
    else if(action==='preview-page')await this.showSelectedPage();
    else{
     await this.page(number);
     const ref={id:'p'+number+'m'+Date.now(),page:number,rect:{x:.1,y:.1,w:.8,h:.8},auto:false,role};
     const item=role==='front'?{frontRef:ref,backRef:null,selected:false,checked:false}:null;
     this.pendingCrop={ref,item};
     this.adjust(item,ref);
    }
   }finally{this.busy=false;select.disabled=false;}
   return;
  }
  if(['edit','read','swap'].includes(action)){
   const selected=this.items.filter(item=>item.selected&&!item.saved);
   if(!selected.length)throw Error('Select an unsaved card.');
   if(action==='read')return this.readCards(selected);
   if(action==='swap'){
    if(selected.some(item=>!item.frontRef||!item.backRef))throw Error('Select cards with both sides to swap.');
    for(const item of selected){[item.frontRef,item.backRef]=[item.backRef,item.frontRef];this.invalidate(item);}
    return this.renderAsync();
   }
   if(selected.length!==1)throw Error('Select one card to edit.');
   const [item]=selected;
   if(!item.frontRef)throw Error('Assign a front side first.');
   if(!item.checked)throw Error('Confirm the front and optional back before editing.');
   this.busy=true;
   try{await this.prepare(item);}finally{this.busy=false;}
  }
  return super.action(action);
 }
};})();
