/* An explicit, ordered print pack. Unavailable files never disappear silently. */
window.WorkerCardPrinter=class {
 constructor(response,notice){
  this.response=response;this.notice=notice;this.el=id=>document.getElementById(id);this.dialog=this.el('card-print-dialog');this.rows=[];this.version=0;this.loading=false;this.controllers=new Set();
  const finLabel=document.createElement('label'),finInput=document.createElement('input');finLabel.className='wc-print-fin-field';finLabel.textContent='FIN last four characters';finInput.id='card-print-fin';finInput.maxLength=4;finInput.placeholder='e.g. 772L';finInput.autocomplete='off';finLabel.append(finInput);this.el('card-print-worker').insertAdjacentElement('afterend',finLabel);finInput.oninput=()=>{finInput.value=finInput.value.toUpperCase().replace(/[^A-Z0-9]/g,'');this.worker.fin_last4=finInput.value;delete this.worker.fin;this.el('card-print-worker').textContent=this.identity(this.worker);this.invalidate();};
  this.el('card-print-close').onclick=()=>this.close();this.dialog.addEventListener('cancel',e=>{e.preventDefault();this.close()});
  this.el('card-print-all').onclick=()=>this.choose('all');this.el('card-print-none').onclick=()=>this.choose('none');this.el('card-print-fronts').onclick=()=>this.choose('front');
  this.el('card-print-prepare').onclick=()=>this.prepare();this.el('card-print-exclude').onclick=()=>this.exclude();this.el('card-print-go').onclick=()=>this.print();
  const download=document.createElement('button');
  download.type='button';
  download.textContent='Download v7 A4 PDF';
  download.disabled=true;
  download.onclick=()=>this.downloadV7();
  this.el('card-print-go').after(download);
  this.v7Download=download;
  this.el('card-print-list').addEventListener('change',e=>{const input=e.target;if(!input.dataset.side)return;const r=this.rows.find(r=>r.id===input.dataset.card);r.sides[input.dataset.side].selected=input.checked;this.invalidate();this.summary()});
  this.el('card-print-list').addEventListener('click',e=>{const b=e.target.closest('button[data-order]');if(!b)return;this.move(b.dataset.card,Number(b.dataset.order));this.el('card-print-list').querySelector(`[data-card="${b.dataset.card}"][data-order="${b.dataset.order}"]`)?.focus()});
  this.el('card-print-list').addEventListener('dragstart',e=>{if(this.loading){e.preventDefault();return}const r=e.target.closest('[data-print-row]');if(r){this.dragged=r.dataset.printRow;e.dataTransfer.setData('text/plain',this.dragged);e.dataTransfer.effectAllowed='move'}});
  this.el('card-print-list').addEventListener('dragover',e=>{if(e.target.closest('[data-print-row]'))e.preventDefault()});
  this.el('card-print-list').addEventListener('drop',e=>{e.preventDefault();const row=e.target.closest('[data-print-row]');if(!row||!this.dragged||this.loading)return;const a=this.rows.findIndex(r=>r.id===this.dragged),b=this.rows.findIndex(r=>r.id===row.dataset.printRow);if(a>=0&&b>=0){this.rows.splice(b,0,this.rows.splice(a,1)[0]);this.invalidate();this.render()}this.dragged=null});
  window.addEventListener('pagehide',()=>this.close());
 }
 title(c){return c.label||({course:'Course card',work_permit:'Work permit',visit_pass:'Visit pass',other:'Other'}[c.category])||'Card'}
 identity(worker){const suffix=String(worker.fin_last4||worker.fin||'').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(-4);return worker.name+(suffix.length===4?' · FIN: ***'+suffix:'')+' · '+worker.worker_code;}
 open(worker,cards){this.close();this.worker={...worker};this.rows=cards.map(c=>({...c,sides:Object.fromEntries(['front','back'].map(side=>[side,{selected:!!c[side==='front'?'image_path':'back_image_path'],attached:!!c[side==='front'?'image_path':'back_image_path'],status:'unchecked'}]))}));this.el('card-print-fin').value=String(worker.fin_last4||worker.fin||'').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(-4);this.el('card-print-worker').textContent=this.identity(worker);this.el('card-print-message').textContent='Choose the required cards and sides. Move cards into the client’s required order, then prepare a preview.'+(this.el('card-print-fin').value?'':' FIN is not recorded for this worker; enter its last four characters above to include it.');this.render();this.dialog.showModal()}
 close(){this.version++;for(const controller of this.controllers)controller.abort();this.controllers.clear();for(const r of this.rows)for(const s of Object.values(r.sides))if(s.url)URL.revokeObjectURL(s.url);this.rows=[];this.loading=false;this.dragged=null;this.dialog.close();this.invalidate(false);this.lock(false)}
 invalidate(bump=true){if(bump)this.version++;this.ready=false;this.v7Download.disabled=true;document.body.classList.remove('wc-print-ready');this.el('print-sheet').replaceChildren();this.el('card-print-preview').replaceChildren();this.el('card-print-go').disabled=true;this.el('card-print-exclude').hidden=true;if(bump)this.el('card-print-message').textContent='Selection or order changed. Prepare the preview before printing.'}
 choose(mode){if(this.loading)return;for(const r of this.rows)for(const [side,s]of Object.entries(r.sides))s.selected=s.attached&&(mode==='all'||mode==='front'&&side==='front');this.invalidate();this.render()}
 move(id,delta){if(this.loading)return;const i=this.rows.findIndex(r=>r.id===id),next=i+delta;if(i<0||next<0||next>=this.rows.length)return;[this.rows[i],this.rows[next]]=[this.rows[next],this.rows[i]];this.invalidate();this.render()}
 selected(){return this.rows.flatMap(r=>Object.entries(r.sides).filter(([,s])=>s.selected).map(([side,s])=>({row:r,side,state:s})))}
 summary(){const selected=this.selected();const count=this.rows.filter(r=>Object.values(r.sides).some(s=>s.selected)).length;this.el('card-print-count').textContent=`${count} of ${this.rows.length} cards selected · ${selected.length} sides`;this.el('card-print-prepare').disabled=this.loading||!selected.length;this.el('card-print-go').disabled=!this.ready||!selected.length;this.v7Download.disabled=!this.ready||!selected.length||this.v7Building;}
 render(){const list=this.el('card-print-list');list.replaceChildren();this.rows.forEach((r,i)=>{const row=document.createElement('li');row.dataset.printRow=r.id;row.draggable=!this.loading;row.className='wc-print-choice';const heading=document.createElement('div'),title=document.createElement('strong'),meta=document.createElement('small');title.textContent=`${i+1}. ${this.title(r)}`;meta.textContent=[r.institute,r.cert_no,r.expiry_date?'Expires '+r.expiry_date:''].filter(Boolean).join(' · ');heading.append(title,meta);row.append(heading);const fields=document.createElement('div');fields.className='wc-print-side-options';for(const [side,s]of Object.entries(r.sides)){const label=document.createElement('label'),input=document.createElement('input'),text=document.createElement('span');input.type='checkbox';input.checked=s.selected;input.disabled=this.loading||!s.attached;input.dataset.card=r.id;input.dataset.side=side;input.setAttribute('aria-label',`${this.title(r)} ${side} (${i+1})`);text.textContent=(side==='front'?'Front':'Back')+' · '+(!s.attached?'Not attached':s.status==='ready'?'Ready':s.status==='failed'?'Unavailable':s.status==='loading'?'Loading…':'Not checked');label.append(input,text);if(s.status==='ready'){const thumb=document.createElement('img');thumb.src=s.url;thumb.alt=this.title(r)+' '+side;thumb.className='wc-print-thumb';label.append(thumb)}if(s.status==='failed'){label.className='wc-print-unavailable';label.title=s.error;}fields.append(label)}row.append(fields);const controls=document.createElement('div');controls.className='wc-toolbar';for(const [text,delta]of [['Move up',-1],['Move down',1]]){const b=document.createElement('button');b.type='button';b.textContent=text;b.dataset.order=delta;b.dataset.card=r.id;b.disabled=this.loading||i+delta<0||i+delta>=this.rows.length;b.setAttribute('aria-label',`${text}: ${this.title(r)}`);controls.append(b)}row.append(controls);list.append(row)});this.summary()}
 lock(locked){this.el('card-print-fin').disabled=locked;for(const id of ['card-print-all','card-print-none','card-print-fronts'])this.el(id).disabled=locked;this.el('card-print-prepare').disabled=locked;this.el('card-print-exclude').disabled=locked;}
 async file(item,signal){const r=await this.response(`/cards/${item.row.id}/file?side=${item.side}`,{signal}),blob=await r.blob();if(!blob.type.startsWith('image/'))throw Error('This card side is not an image. Upload a replacement JPG / PNG.');const url=URL.createObjectURL(blob);try{const image=new Image();image.src=url;await image.decode();return url}catch(e){URL.revokeObjectURL(url);throw Error('The saved image could not be read. Upload a replacement.')}}
 async prepare(){if(this.loading)return;if(this.el('card-print-fin').value&&this.el('card-print-fin').value.length!==4){this.el('card-print-message').textContent='Enter exactly four FIN characters, or clear the field if unknown.';return;}this.invalidate();const selected=this.selected();if(!selected.length){this.el('card-print-message').textContent='Select at least one card side.';return}const version=this.version;this.loading=true;this.lock(true);this.render();let done=0;
  try{let next=0;for(const item of selected)if(item.state.status!=='ready')item.state.status='loading';this.render();
   const progress=()=>{if(version===this.version)this.el('card-print-message').textContent=`Checking card images… ${done} of ${selected.length}`;};progress();
   const load=async()=>{while(next<selected.length&&version===this.version){const item=selected[next++];if(item.state.status==='ready'){done++;progress();continue}
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);this.controllers.add(controller);
    try{const url=await this.file(item,controller.signal);if(version!==this.version){URL.revokeObjectURL(url);return}item.state.url=url;item.state.status='ready';delete item.state.error;}
    catch(e){if(version!==this.version)return;item.state.status='failed';item.state.error=e.name==='AbortError'?'Loading timed out. Try preparing the preview again.':e.message;}
    finally{clearTimeout(timer);this.controllers.delete(controller);}done++;progress();
   }};await Promise.all(Array.from({length:Math.min(4,selected.length)},()=>load()));
   if(version!==this.version)return;const failed=selected.filter(i=>i.state.status==='failed');if(failed.length){const root=this.el('card-print-preview'),h=document.createElement('h3'),list=document.createElement('ul');h.textContent='These selected sides could not load';root.append(h,list);for(const f of failed){const li=document.createElement('li');li.textContent=`${this.title(f.row)} (${this.rows.indexOf(f.row)+1}) · ${f.side}: ${f.state.error}`;list.append(li)}this.el('card-print-message').textContent=`${failed.length} selected side(s) unavailable. Retry, change your selection, or exclude unavailable sides. Nothing has been printed.`;this.el('card-print-exclude').hidden=false;}
   else{this.build();await Promise.all([...this.el('print-sheet').querySelectorAll('img'),...this.el('card-print-preview').querySelectorAll('img')].map(i=>i.decode()));if(version!==this.version)return;this.ready=true;this.el('card-print-message').textContent='Preview ready. Check the order and sides below, then print or choose Save as PDF in your browser.';}
  }finally{if(version===this.version){this.loading=false;this.lock(false);this.render()}}
 }
 exclude(){if(this.loading)return;for(const item of this.selected())if(item.state.status==='failed')item.state.selected=false;this.invalidate();this.render();this.prepare()}
 build(){const sheet=this.el('print-sheet'),preview=this.el('card-print-preview');let index=0,page;for(const row of this.rows){const selected=Object.entries(row.sides).filter(([,s])=>s.selected);if(!selected.length)continue;if(index%4===0){page=document.createElement('section');page.className='wc-print-page';const heading=document.createElement('h1');heading.textContent=this.identity(this.worker);page.append(heading);sheet.append(page)}const article=document.createElement('article'),title=document.createElement('h2'),sides=document.createElement('div');title.textContent=`${++index}. ${this.title(row)} · ${row.no_expiry?'No expiry':'Expiry: '+(row.expiry_date?row.expiry_date.split('-').reverse().join('/'):'—')}`;sides.className='wc-print-sides';article.append(title,sides);for(const [side,s]of selected){const figure=document.createElement('figure'),image=document.createElement('img');image.src=s.url;image.alt=side;figure.append(image);sides.append(figure)}page.append(article)}preview.append(sheet.cloneNode(true));preview.firstChild.removeAttribute('id');preview.firstChild.removeAttribute('aria-hidden');preview.firstChild.className='wc-print-preview-sheet';}
 async downloadV7(){
  if(!this.ready||this.loading||this.v7Building)return;
  const version=this.version;
  const identity=this.worker.name+(this.el('card-print-fin').value?' · FIN '+this.el('card-print-fin').value:'');
  const selection=this.rows.map(row=>Object.entries(row.sides).filter(([,state])=>state.selected).map(([side,state])=>[side,state.url])).filter(sides=>sides.length);
  this.v7Building=true;
  this.summary();
  try{
   const {makeCardPdf}=await import('../card-import/arrange.mjs');
   const sets=[];
   for(const sides of selection){
    const set={};
    for(const [side,url] of sides){
     if(version!==this.version)return;
     const image=new Image();
     image.src=url;
     await image.decode();
     const canvas=document.createElement('canvas');
     canvas.width=image.naturalWidth;
     canvas.height=image.naturalHeight;
     const context=canvas.getContext('2d');
     context.fillStyle='#fff';
     context.fillRect(0,0,canvas.width,canvas.height);
     context.drawImage(image,0,0);
     set[side]={jpeg:canvas.toDataURL('image/jpeg',.96),size:canvas.width+' × '+canvas.height};
    }
    sets.push(set);
   }
   if(version!==this.version)return;
   const header=document.createElement('canvas');
   header.width=1800;
   header.height=60;
   const context=header.getContext('2d');
   context.fillStyle='#fff';
   context.fillRect(0,0,1800,60);
   context.fillStyle='#182d50';
   context.font='bold 36px Arial';
   context.fillText(identity,0,44,1800);
   const pdf=makeCardPdf(sets,{jpeg:header.toDataURL('image/jpeg',.96),width:1800,height:60});
   const url=URL.createObjectURL(pdf);
   const link=document.createElement('a');
   link.href=url;
   link.download='Worker_Cards_A4.pdf';
   link.click();
   setTimeout(()=>URL.revokeObjectURL(url),30000);
  }catch(error){
   if(version===this.version)this.el('card-print-message').textContent='Could not create the A4 PDF. '+error.message;
  }finally{
   this.v7Building=false;
   this.summary();
  }
 }
 print(){if(!this.ready||this.loading)return;document.body.classList.add('wc-print-ready');try{window.print();this.notice('Selected card sheet ready.')}catch(e){this.el('card-print-message').textContent='Printing could not open. Try your browser’s Print / Save as PDF option.'}}
};
