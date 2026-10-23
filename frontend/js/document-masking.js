/* Photo editing stays local. The existing upload API validates the file digest
 * and permanently flattens reviewed masks into the saved copy. */
window.WorkerDocumentMasker=class {
 constructor(api,worker){
  this.api=api;this.worker=worker;this.states={};this.version=0;this.pointers=new Map();
  this.el=id=>document.getElementById(id);this.canvas=this.el('mask-canvas');this.dialog=this.el('mask-editor');
  for(const side of ['front','back']){
   this.el(side+'-file').addEventListener('change',()=>{delete this.states[side];this.status(side);const f=this.el(side+'-file').files[0];if(f)this.start(side,f)});
   this.el('review-'+side).onclick=()=>{const f=this.el(side+'-file').files[0];if(f)this.start(side,f)};
  }
  this.el('mask-close').onclick=()=>this.close();
  this.dialog.addEventListener('cancel',e=>{e.preventDefault();this.close()});
  this.el('mask-confirm').onclick=()=>{if(!this.image||this.crop)return; if([...this.el('mask-boxes').querySelectorAll('input')].some(i=>!i.reportValidity()))return;this.page().reviewed=true;this.status(this.side);if(this.index+1<this.state.count)this.load(this.index+1);else this.close()};
  this.el('mask-previous').onclick=()=>this.load(this.index-1);this.el('mask-next').onclick=()=>this.load(this.index+1);
  this.el('mask-undo').onclick=()=>{this.page().boxes.pop();this.changed()};
  this.el('mask-clear').onclick=()=>{if(this.page().boxes.length&&confirm('Remove all masks on this page?')){this.page().boxes=[];this.changed()}};
  this.el('mask-draw').onclick=()=>this.mode('mask');this.el('mask-move').onclick=()=>this.mode(this.tool==='pan'?'mask':'pan');
  this.el('mask-zoom').onclick=()=>this.setZoom(this.zoom===1?2:1);
  this.el('mask-zoom-in').onclick=()=>this.setZoom(this.zoom*1.25);this.el('mask-zoom-out').onclick=()=>this.setZoom(this.zoom/1.25);
  this.el('mask-fit').onclick=()=>this.setZoom(1);
  this.el('mask-crop').onclick=()=>this.mode('crop');this.el('mask-crop-apply').onclick=()=>this.transform('crop');
  this.el('mask-crop-cancel').onclick=()=>this.mode('mask');this.el('mask-rotate').onclick=()=>this.transform('rotate');
  this.el('mask-reset').onclick=()=>{if(confirm('Restore the original photo and remove its edits?')){delete this.states[this.side];this.start(this.side,this.el(this.side+'-file').files[0])}};
  this.el('mask-suggest').onclick=()=>this.suggest();
  this.canvas.addEventListener('pointerdown',e=>this.down(e));this.canvas.addEventListener('pointermove',e=>this.move(e));
  this.canvas.addEventListener('pointerup',e=>this.up(e));this.canvas.addEventListener('pointercancel',e=>this.up(e,true));
  this.canvas.addEventListener('wheel',e=>{if(e.ctrlKey||e.metaKey){e.preventDefault();this.setZoom(this.zoom*(e.deltaY<0?1.1:.9))}},{passive:false});
  window.addEventListener('resize',()=>{if(this.image&&this.dialog.open)this.layout()});for(const help of this.dialog.querySelectorAll('details'))help.addEventListener('toggle',()=>{if(this.image)this.layout()});
 }
 reset(){this.version++;this.states={};this.image=null;this.state=null;this.pointers.clear();this.drag=null;this.dialog.close();this.canvas.width=this.canvas.height=1;this.el('mask-boxes').replaceChildren();for(const s of ['front','back'])this.status(s)}
 close(){this.version++;this.dialog.close();this.pointers.clear();this.drag=null;this.gesture=null;this.active=null}
 status(side){const s=this.states[side],n=s?Object.values(s.pages).filter(p=>p.reviewed).length:0;this.el('mask-status-'+side).textContent=s?`${n} of ${s.count} pages checked`:'Choose a file to crop and mask';this.el('review-'+side).disabled=!this.el(side+'-file').files[0]}
 async start(side,file){this.side=side;this.state=this.states[side]||{file,pages:{},count:1};this.states[side]=this.state;if(!this.dialog.open)this.dialog.showModal();await this.load(0)}
 page(){return this.state.pages[this.index]}
 async decode(blob){const url=URL.createObjectURL(blob);try{const image=new Image();image.src=url;await image.decode();return image}finally{URL.revokeObjectURL(url)}}
 async load(index){
  if(index<0||index>=this.state.count)return;
  const version=++this.version,state=this.state;this.index=index;this.image=null;this.drag=null;this.crop=null;this.pointers.clear();this.active=this.side;this.el('mask-review').hidden=false;this.canvas.hidden=true;
  this.message('Opening document…');this.controls(false);this.el('mask-boxes').replaceChildren();
  try{
   if(state.file.size>20971520)throw Error('Files must be 20 MB or smaller.');
   if(!state.pages[index]){
    if(state.file.type==='application/pdf'||/\.pdf$/i.test(state.file.name)){
     this.message('Preparing PDF page… Photos open locally without this step.');
     const p=await this.preview(state.file,index);if(version!==this.version)return;
     state.count=p.pages;state.sha256=p.sha256;state.policy=p.policy;
     state.pages[index]={boxes:p.boxes,reviewed:false,image:await this.decode(await (await fetch('data:image/png;base64,'+p.image)).blob())};
    }else{
     let blob=state.file;
     if(/heic|heif/i.test(blob.type)||/\.hei[cf]$/i.test(blob.name)){
      this.message('Converting iPhone photo…');
      if(!window.heic2any)throw Error('HEIC conversion is unavailable. Choose a JPG / PNG photo.');
      blob=await window.heic2any({blob,toType:'image/jpeg',quality:.95});if(Array.isArray(blob))blob=blob[0];
     }
     const image=await this.decode(blob);if(version!==this.version)return;
     const scale=Math.min(1,Math.sqrt(4000000/(image.naturalWidth*image.naturalHeight)),4096/Math.max(image.naturalWidth,image.naturalHeight));
     const c=document.createElement('canvas');c.width=Math.max(1,Math.round(image.naturalWidth*scale));c.height=Math.max(1,Math.round(image.naturalHeight*scale));c.getContext('2d').drawImage(image,0,0,c.width,c.height);
     state.pages[0]={boxes:[],reviewed:false,image:c};state.policy='fin-dob-wp-v1';state.local=true;
    }
   }
   if(version!==this.version)return;this.image=state.pages[index].image;this.canvas.width=this.image.naturalWidth||this.image.width;this.canvas.height=this.image.naturalHeight||this.image.height;this.canvas.hidden=false;
   this.zoom=1;this.mode('mask');this.controls(true);this.layout();this.boxList();this.paint();this.status(this.side);
   this.el('mask-page').textContent=`${this.side==='front'?'Document / front':'Back'} · Page ${index+1} of ${state.count}`;
   this.message('Drag over sensitive details to hide them. Use Crop to trim the photo. Automatic suggestions are optional.');
  }catch(e){if(version===this.version){this.message(e.message||'Could not open this image. Try JPG or PNG.');this.el('mask-page').textContent='Document could not open';}}
 }
 controls(ready){for(const id of ['mask-confirm','mask-undo','mask-clear','mask-zoom','mask-zoom-in','mask-zoom-out','mask-fit','mask-move','mask-draw','mask-suggest','mask-crop','mask-rotate','mask-reset'])this.el(id).disabled=!ready;this.el('mask-previous').disabled=!ready||this.index===0;this.el('mask-next').disabled=!ready||this.index+1>=this.state.count;this.el('mask-previous').hidden=this.el('mask-next').hidden=this.state?.count===1;for(const id of ['mask-crop','mask-rotate','mask-reset'])this.el(id).hidden=!this.state?.local;this.el('mask-crop-actions').hidden=true}
 message(text){this.el('mask-message').textContent=text}
 mode(tool){this.tool=tool;this.crop=null;this.drag=null;this.canvas.style.cursor=tool==='pan'?'grab':'crosshair';this.el('mask-move').textContent=tool==='pan'?'Draw masks':'Move view';this.el('mask-draw').setAttribute('aria-pressed',tool==='mask');this.el('mask-crop').setAttribute('aria-pressed',tool==='crop');this.el('mask-crop-actions').hidden=tool!=='crop';this.el('mask-crop-apply').disabled=true;this.el('mask-confirm').disabled=tool==='crop';this.paint()}
 layout(){const stage=this.el('mask-stage');const w=Math.max(100,stage.clientWidth-32),h=Math.max(120,stage.clientHeight-32);this.fit=Math.min(w/this.canvas.width,h/this.canvas.height);this.canvas.style.width=Math.round(this.canvas.width*this.fit*this.zoom)+'px';this.canvas.style.height=Math.round(this.canvas.height*this.fit*this.zoom)+'px';this.el('mask-scale').textContent=Math.round(this.zoom*100)+'%';}
 setZoom(zoom){if(!this.image)return;this.zoom=Math.min(6,Math.max(.5,zoom));this.layout();this.el('mask-zoom').textContent=this.zoom===1?'Zoom in':'Fit page';if(this.tool!=='crop')this.mode(this.zoom>1?'pan':'mask')}
 point(e){const r=this.canvas.getBoundingClientRect();return{x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))}}
 rectangle(a,b){return{x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),w:Math.abs(a.x-b.x),h:Math.abs(a.y-b.y)}}
 down(e){if(!this.image||e.button>0)return;e.preventDefault();this.canvas.setPointerCapture(e.pointerId);this.pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});if(this.pointers.size===2){this.drag=null;this.gesture={distance:this.distance(),zoom:this.zoom};this.paint();return}this.drag={point:this.point(e),x:e.clientX,y:e.clientY,left:this.el('mask-stage').scrollLeft,top:this.el('mask-stage').scrollTop}}
 distance(){const [a,b]=[...this.pointers.values()];return Math.hypot(a.x-b.x,a.y-b.y)||1}
 move(e){if(!this.pointers.has(e.pointerId))return;e.preventDefault();this.pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});if(this.pointers.size>1&&this.gesture){this.zoom=Math.min(6,Math.max(.5,this.gesture.zoom*this.distance()/this.gesture.distance));this.layout();return}if(!this.drag||this.gesture)return;if(this.tool==='pan'){this.el('mask-stage').scrollLeft=this.drag.left+this.drag.x-e.clientX;this.el('mask-stage').scrollTop=this.drag.top+this.drag.y-e.clientY}else this.paint(this.rectangle(this.drag.point,this.point(e)))}
 up(e,cancel=false){if(!this.pointers.has(e.pointerId))return;this.pointers.delete(e.pointerId);if(this.gesture){if(!this.pointers.size){this.gesture=null;this.drag=null;}return}if(!this.drag)return;const b=this.rectangle(this.drag.point,this.point(e));this.drag=null;if(!cancel&&this.tool!=='pan'&&b.w*this.canvas.width>=3&&b.h*this.canvas.height>=3){if(this.tool==='crop'){this.crop=b;this.el('mask-crop-apply').disabled=false;this.paint()}else if(this.page().boxes.length<100){this.page().boxes.push({...b,field:'Manual mask',suffix:''});this.changed()}else this.message('Maximum 100 masks per page.');}else this.paint()}
 changed(){this.page().reviewed=false;this.version++;this.el('mask-suggest').disabled=false;this.status(this.side);this.paint();this.boxList()}
 paint(extra){if(!this.image)return;const c=this.canvas.getContext('2d'),w=this.canvas.width,h=this.canvas.height;c.drawImage(this.image,0,0,w,h);for(const b of this.page().boxes){c.fillStyle='#000';c.fillRect(b.x*w,b.y*h,b.w*w,b.h*h);if(b.suffix){const size=Math.min(b.h*h*.65,b.w*w/(b.suffix.length*.7));c.fillStyle='#fff';c.font=`${size}px Arial`;c.textAlign='right';c.fillText(b.suffix,(b.x+b.w)*w-2,b.y*h+b.h*h*.78)}}const b=extra||this.crop;if(b){if(this.tool==='crop'){c.fillStyle='#0008';c.fillRect(0,0,w,b.y*h);c.fillRect(0,(b.y+b.h)*h,w,h);c.fillRect(0,b.y*h,b.x*w,b.h*h);c.fillRect((b.x+b.w)*w,b.y*h,w,b.h*h);c.strokeStyle='#38bdf8';c.lineWidth=3/Math.max(.1,this.fit*this.zoom);c.strokeRect(b.x*w,b.y*h,b.w*w,b.h*h)}else{c.fillStyle='#000';c.fillRect(b.x*w,b.y*h,b.w*w,b.h*h)}}}
 async transform(action){if(!this.state.local||!this.image)return;const old=this.page(),w=this.canvas.width,h=this.canvas.height,c=document.createElement('canvas');let boxes=[];
  if(action==='rotate'){c.width=h;c.height=w;const ctx=c.getContext('2d');ctx.translate(h,0);ctx.rotate(Math.PI/2);ctx.drawImage(this.image,0,0,w,h);boxes=old.boxes.map(b=>({...b,x:1-b.y-b.h,y:b.x,w:b.h,h:b.w}));}
  else{if(!this.crop)return;const r=this.crop,x=Math.round(r.x*w),y=Math.round(r.y*h),cw=Math.max(1,Math.min(w-x,Math.round(r.w*w))),ch=Math.max(1,Math.min(h-y,Math.round(r.h*h)));c.width=cw;c.height=ch;c.getContext('2d').drawImage(this.image,x,y,cw,ch,0,0,cw,ch);
   for(const b of old.boxes){const x0=Math.max(x,b.x*w),y0=Math.max(y,b.y*h),x1=Math.min(x+cw,(b.x+b.w)*w),y1=Math.min(y+ch,(b.y+b.h)*h);if(x1>x0&&y1>y0)boxes.push({...b,x:(x0-x)/cw,y:(y0-y)/ch,w:(x1-x0)/cw,h:(y1-y0)/ch,suffix:''})}
  }
  this.state.pages[0]={image:c,boxes,reviewed:false};this.image=c;this.canvas.width=c.width;this.canvas.height=c.height;this.zoom=1;this.mode('mask');this.layout();this.changed();this.message(action==='crop'?'Photo cropped. Check the masks before confirming.':'Photo rotated. Check the masks before confirming.');
 }
 boxList(){const root=this.el('mask-boxes');root.replaceChildren();this.page().boxes.forEach((b,i)=>{const row=document.createElement('div'),label=document.createElement('label'),input=document.createElement('input'),remove=document.createElement('button');row.className='wc-mask-box';label.textContent=b.field+' · visible ending (optional)';input.value=b.suffix;input.disabled=b.field==='Date of birth';input.maxLength=4;input.pattern=b.field==='FIN'?'[0-9]{3}[A-Z]':b.field==='Work Permit number'?'[0-9]{4}':'([0-9]{3}[A-Z]|[0-9]{4})';input.placeholder='Hidden completely';input.setAttribute('aria-label',`Visible ending for mask ${i+1}`);input.oninput=()=>{const value=input.value.toUpperCase();input.value=value;input.setCustomValidity(/^(?:\d{3}[A-Z]|\d{4})?$/.test(value)?'':'Use three digits and one letter, four digits, or leave blank.');b.suffix=value;this.page().reviewed=false;this.version++;this.el('mask-suggest').disabled=false;this.status(this.side);this.paint()};label.append(input);remove.type='button';remove.textContent=`Remove mask ${i+1}`;remove.onclick=()=>{this.page().boxes.splice(i,1);this.changed()};row.append(label,remove);root.append(row)})}
 async blob(canvas){return new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('Could not prepare photo.')),'image/png'))}
 async preview(file,page){const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),25000);try{return await this.api('/mask-preview?'+new URLSearchParams({worker_id:this.worker(),page}),{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream'},body:file,signal:controller.signal})}finally{clearTimeout(timeout)}}
 async suggest(){const version=this.version,state=this.state,index=this.index;this.el('mask-suggest').disabled=true;this.message('Finding sensitive details… You can continue masking manually.');try{const file=state.local?await this.blob(this.image):state.file;const result=await this.preview(file,index);if(version!==this.version||state!==this.state||!this.dialog.open)return;if(result.recognition==='manual_required'){this.message('Automatic detection is unavailable. Draw masks manually and check this page.');return}this.page().boxes.push(...result.boxes.slice(0,100-this.page().boxes.length));this.changed();this.message(result.boxes.length?'Suggestions added. Check each box and any missed details.':'No suggestions found. Check all details and add masks manually.');}catch(e){if(version===this.version)this.message('Automatic detection could not finish. Manual masking is ready to use.');}finally{if(state===this.state&&this.dialog.open)this.el('mask-suggest').disabled=false}}
 plan(side,file){const s=this.states[side];if(!s||s.file!==file||Array.from({length:s.count},(_,i)=>s.pages[i]).some(p=>!p?.reviewed))throw Error(`Review the masking on every page of the ${side==='front'?'document / front':'back'} before saving.`);return s}
 async upload(side,file){const s=this.plan(side,file);let output=file,digest=s.sha256;if(s.local){output=new File([await this.blob(s.pages[0].image)],'worker-card.png',{type:'image/png'});if(output.size>20971520)throw Error('Edited photo exceeds 20 MB. Crop it or choose a smaller photo.');const hash=await crypto.subtle.digest('SHA-256',await output.arrayBuffer());digest=Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('')}
  if(!digest)throw Error('Document review is incomplete. Open the masking editor again.');
  return {file:output,plan:JSON.stringify({policy:s.policy,sha256:digest,pages:Array.from({length:s.count},(_,i)=>({boxes:s.pages[i].boxes.map(({x,y,w,h,field,suffix})=>({x,y,w,h,field,suffix})),reviewed:true}))})};
 }
};
