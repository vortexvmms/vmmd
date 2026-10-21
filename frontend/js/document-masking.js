/* Mandatory page-by-page review; only the server creates the saved copy. */
window.WorkerDocumentMasker=class{
 constructor(api,worker){
  this.api=api;this.worker=worker;this.states={};this.version=0;this.canvas=document.getElementById('mask-canvas');
  this.el=id=>document.getElementById(id);
  for(const side of ['front','back']){
   this.el(side+'-file').addEventListener('change',()=>{const file=this.el(side+'-file').files[0];delete this.states[side];this.status(side);if(file)this.start(side,file)});
   this.el('review-'+side).onclick=()=>{const file=this.el(side+'-file').files[0];if(file)this.start(side,file)};
  }
  this.el('mask-previous').onclick=()=>this.load(this.index-1);
  this.el('mask-next').onclick=()=>this.load(this.index+1);
  this.el('mask-confirm').onclick=()=>{if([...this.el('mask-boxes').querySelectorAll('input')].some(i=>!i.reportValidity()))return;this.state.pages[this.index].reviewed=true;this.status(this.side);if(this.index+1<this.state.count)this.load(this.index+1);else{this.el('mask-review').hidden=true;this.active=null}};
  this.el('mask-undo').onclick=()=>{this.page().boxes.pop();this.changed()};
  this.el('mask-zoom').onclick=()=>{this.zoom=this.zoom===2?1:2;this.canvas.style.width=this.zoom*100+'%';this.el('mask-zoom').textContent=this.zoom===2?'Fit page':'Zoom in';this.moveMode(this.zoom===2)};
  this.el('mask-move').onclick=()=>this.moveMode(!this.pan);
  this.canvas.addEventListener('pointerdown',e=>{if(!this.image||this.pan)return;e.preventDefault();this.canvas.setPointerCapture(e.pointerId);this.drag=this.point(e)});
  this.canvas.addEventListener('pointermove',e=>{if(this.drag){e.preventDefault();this.paint(this.rectangle(this.drag,this.point(e)))}});
  this.canvas.addEventListener('pointerup',e=>{if(!this.drag)return;const b=this.rectangle(this.drag,this.point(e));this.drag=null;if(b.w*this.canvas.width>=3&&b.h*this.canvas.height>=3){this.page().boxes.push({...b,field:'Manual mask',suffix:''});this.changed()}else this.paint()});
  this.canvas.addEventListener('pointercancel',()=>{this.drag=null;this.paint()});
 }
 reset(){this.version++;this.states={};this.active=null;this.image=null;this.drag=null;this.canvas.width=1;this.canvas.height=1;this.el('mask-boxes').replaceChildren();this.el('mask-review').hidden=true;for(const s of ['front','back'])this.status(s)}
 status(side){const s=this.states[side],n=s?Object.values(s.pages).filter(p=>p.reviewed).length:0;this.el('mask-status-'+side).textContent=s?`${n} of ${s.count} pages checked`:'Masking review required for a new file';this.el('review-'+side).disabled=!this.el(side+'-file').files[0]}
 async start(side,file){this.side=side;this.state=this.states[side]||{file,pages:{},count:1};this.states[side]=this.state;await this.load(0)}
 page(){return this.state.pages[this.index]}
 moveMode(pan){this.pan=pan;this.canvas.style.touchAction=pan?'pan-x pan-y':'none';this.canvas.style.cursor=pan?'grab':'crosshair';this.el('mask-move').textContent=pan?'Draw masks':'Move view'}
 async load(index){
  if(index<0||index>=this.state.count)return;
  const version=++this.version,side=this.side,state=this.state;
  this.index=index;this.image=null;this.drag=null;this.active=side;this.el('mask-review').hidden=false;this.el('mask-message').textContent='Finding FIN, date of birth and Work Permit numbers…';this.el('mask-boxes').replaceChildren();this.canvas.hidden=true;
  for(const id of ['mask-confirm','mask-previous','mask-next','mask-undo','mask-zoom','mask-move'])this.el(id).disabled=true;
  try{
   if(state.file.size>20971520)throw Error('Files must be 20 MB or smaller.');
   const p=await this.api('/mask-preview?'+new URLSearchParams({worker_id:this.worker(),page:index}),{method:'POST',headers:{'Content-Type':state.file.type||'application/octet-stream'},body:state.file});
   if(version!==this.version)return;
   state.count=p.pages;state.sha256=p.sha256;state.policy=p.policy;
   state.pages[index]??={boxes:p.boxes,reviewed:false};
   const image=new Image();image.src='data:image/png;base64,'+p.image;await image.decode();if(version!==this.version)return;
   this.image=image;this.canvas.width=p.width;this.canvas.height=p.height;this.canvas.hidden=false;this.zoom=1;this.canvas.style.width='100%';this.el('mask-zoom').textContent='Zoom in';this.moveMode(false);
   this.el('mask-page').textContent=`${side==='front'?'Document / front':'Back'} · Page ${index+1} of ${p.pages}`;
   this.el('mask-message').textContent=p.recognition==='manual_required'?'Automatic recognition is unavailable. Draw black boxes over the details yourself, then check this page.':'Check every box and any missed details. Drag on the document to add a black box. Remove incorrect boxes below.';
   this.el('mask-confirm').disabled=false;this.el('mask-previous').disabled=index===0;this.el('mask-next').disabled=index+1===p.pages;this.el('mask-undo').disabled=false;this.el('mask-zoom').disabled=false;this.el('mask-move').disabled=false;
   this.status(side);this.paint();this.boxList();
  }catch(e){if(version===this.version){this.el('mask-message').textContent=e.message;this.el('mask-page').textContent='Review could not load. Use Review masking to retry.'}}
 }
 point(e){const r=this.canvas.getBoundingClientRect();return{x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))}}
 rectangle(a,b){return{x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),w:Math.abs(a.x-b.x),h:Math.abs(a.y-b.y)}}
 changed(){this.page().reviewed=false;this.status(this.side);this.paint();this.boxList()}
 paint(extra){if(!this.image)return;const c=this.canvas.getContext('2d'),w=this.canvas.width,h=this.canvas.height;c.drawImage(this.image,0,0,w,h);for(const b of [...this.page().boxes,...(extra?[extra]:[])]){c.fillStyle='#000';c.fillRect(b.x*w,b.y*h,b.w*w,b.h*h);if(b.suffix){const size=Math.min(b.h*h*.65,b.w*w/(b.suffix.length*.7));c.fillStyle='#fff';c.font=`${size}px Arial`;c.textAlign='right';c.fillText(b.suffix,(b.x+b.w)*w-2,b.y*h+b.h*h*.78)}}}
 boxList(){const root=this.el('mask-boxes');root.replaceChildren();this.page().boxes.forEach((b,i)=>{const row=document.createElement('div'),label=document.createElement('label'),input=document.createElement('input'),remove=document.createElement('button');row.className='wc-mask-box';label.textContent=b.field+' · visible ending (optional)';input.value=b.suffix;input.disabled=b.field==='Date of birth';input.maxLength=4;input.pattern=b.field==='FIN'?'[0-9]{3}[A-Z]':b.field==='Work Permit number'?'[0-9]{4}':'([0-9]{3}[A-Z]|[0-9]{4})';input.placeholder='Hidden completely';input.setAttribute('aria-label',`Visible ending for mask ${i+1}`);input.oninput=()=>{const value=input.value.toUpperCase();input.value=value;input.setCustomValidity(/^(?:\d{3}[A-Z]|\d{4})?$/.test(value)?'':'Use three digits and one letter, four digits, or leave blank.');b.suffix=value;this.page().reviewed=false;this.status(this.side);this.paint()};label.append(input);remove.type='button';remove.textContent=`Remove mask ${i+1}`;remove.onclick=()=>{this.page().boxes.splice(i,1);this.changed()};row.append(label,remove);root.append(row)})}
 plan(side,file){const s=this.states[side];if(!s||s.file!==file||!s.sha256||Array.from({length:s.count},(_,i)=>s.pages[i]).some(p=>!p?.reviewed))throw Error(`Review the masking on every page of the ${side==='front'?'document / front':'back'} before saving.`);return JSON.stringify({policy:s.policy,sha256:s.sha256,pages:Array.from({length:s.count},(_,i)=>s.pages[i])})}
};
