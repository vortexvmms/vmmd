import {readCrop} from './ocr.mjs';

const finPattern=/\b[FGM]\s*(?:\d\s*){7}[A-Z]\b/gi;
export function maskSuggestions(lines) {
  const boxes=[];
  let uncertain=false;
  for(const line of lines){
    const symbols=(line.symbols||[]).filter(s=>s.text.trim());
    const text=symbols.map(s=>s.text).join('').toUpperCase();
    for(const match of line.text.matchAll(finPattern)){
      const fin=match[0].replace(/\s/g,'').toUpperCase();
      const start=text.indexOf(fin);
      if(start<0||text.indexOf(fin,start+1)>=0){uncertain=true;continue;}
      const glyphs=symbols.slice(start,start+9);
      if(glyphs.length!==9||glyphs.some(s=>s.text.trim().length!==1||!Number.isFinite(s.x+s.y+s.width+s.height)||s.width<=0||s.height<=0)){
        uncertain=true;continue;
      }
      const prefix=glyphs.slice(0,5);
      const x=Math.min(...prefix.map(s=>s.x));
      const y=Math.min(...prefix.map(s=>s.y));
      const right=Math.max(...prefix.map(s=>s.x+s.width));
      const bottom=Math.max(...prefix.map(s=>s.y+s.height));
      const previous=symbols[start-1];
      const suffix=glyphs.slice(5);
      if(right>Math.min(...suffix.map(s=>s.x))+1e-8||previous&&previous.x+previous.width>x+1e-8||
        glyphs.some((s,i)=>i&&s.x<=glyphs[i-1].x)||x<0||y<0||right>1||bottom>1){
        uncertain=true;continue;
      }
      boxes.push({x,y,w:right-x,h:bottom-y,field:'FIN'});
    }
    if(/\b(?:FIN|NRIC)\b/i.test(line.text)&&!line.text.match(finPattern)&&!boxes.length)uncertain=true;
  }
  return {boxes,uncertain};
}

const clamp=(value,min=0,max=1)=>Math.max(min,Math.min(max,value));
export function moveMask(box,edge,dx,dy) {
  if(edge==='move')return {...box,x:clamp(box.x+dx,0,1-box.w),y:clamp(box.y+dy,0,1-box.h)};
  let {x,y}=box,right=x+box.w,bottom=y+box.h;
  const minWidth=Math.min(.003,box.w),minHeight=Math.min(.003,box.h);
  if(edge.includes('w'))x=clamp(x+dx,0,right-minWidth);
  if(edge.includes('e'))right=clamp(right+dx,x+minWidth,1);
  if(edge.includes('n'))y=clamp(y+dy,0,bottom-minHeight);
  if(edge.includes('s'))bottom=clamp(bottom+dy,y+minHeight,1);
  return {...box,x,y,w:right-x,h:bottom-y};
}
function paint(ctx,image,boxes) {
  ctx.drawImage(image,0,0);
  ctx.fillStyle='#000';
  for(const box of boxes)ctx.fillRect(Math.floor(box.x*image.width+1e-7),Math.floor(box.y*image.height+1e-7),
    Math.ceil((box.x+box.w)*image.width-1e-7)-Math.floor(box.x*image.width+1e-7),
    Math.ceil((box.y+box.h)*image.height-1e-7)-Math.floor(box.y*image.height+1e-7));
}
export async function applyMasks(card,boxes,image) {
  const original=card.sourceJpeg||card.jpeg;
  if(JSON.stringify(boxes)===JSON.stringify(card.maskBoxes||[]))return;
  const started=performance.now();
  if(!image){image=new Image();image.src=original;await image.decode();}
  const canvas=document.createElement('canvas');
  canvas.width=image.width;canvas.height=image.height;
  paint(canvas.getContext('2d'),image,boxes);
  card.sourceJpeg=original;
  card.maskBoxes=structuredClone(boxes);
  card.jpeg=boxes.length?canvas.toDataURL('image/jpeg',.96):original;
  card.maskReviewed=false;
  console.debug('Worker card masking duration (ms)',Math.round(performance.now()-started));
}

export async function reviewMask(card) {
  const original=card.sourceJpeg||card.jpeg;
  const image=new Image();image.src=original;await image.decode();
  const dialog=document.createElement('dialog');
  dialog.className='mask-dialog';
  dialog.innerHTML='<h2>Edit card masks</h2><p>Drag on an empty area to draw. Select a mask to move, resize or delete it.</p><div class="actions"><button data-auto>Auto Mask</button><button data-undo>Undo</button><button data-delete>Delete selected</button><button data-confirm>Apply masks</button><button data-cancel class="secondary">Cancel</button></div><p role="status"></p><div class="mask-stage"><div class="mask-editor"><canvas aria-label="Card image"></canvas><div class="mask-overlay"></div></div></div><div class="mask-list"></div>';
  document.body.append(dialog);
  const get=selector=>dialog.querySelector(selector);
  const editor=get('.mask-editor'),canvas=get('canvas'),overlay=get('.mask-overlay');
  const message=get('[role=status]');
  canvas.width=image.width;canvas.height=image.height;
  editor.style.setProperty('--ratio',image.width/image.height);
  let boxes=structuredClone(card.maskBoxes||[]),selected=-1,drag,running=false,controller,closed=false;
  const history=[];
  const snapshot=()=>history.push({boxes:structuredClone(boxes),selected});
  const point=event=>{
    const r=canvas.getBoundingClientRect();
    return {x:clamp((event.clientX-r.left)/r.width),y:clamp((event.clientY-r.top)/r.height)};
  };
  function draw(){
    paint(canvas.getContext('2d'),image,boxes);
    overlay.replaceChildren();
    const list=get('.mask-list');list.replaceChildren();
    for(const [index,box] of boxes.entries()){
      const shape=document.createElement('div');
      shape.className='mask-shape'+(index===selected?' selected':'');
      shape.dataset.mask=index;
      Object.assign(shape.style,{left:box.x*100+'%',top:box.y*100+'%',width:box.w*100+'%',height:box.h*100+'%'});
      if(index===selected)for(const edge of ['nw','n','ne','w','e','sw','s','se']){
        const handle=document.createElement('span');
        handle.className='mask-handle '+edge;handle.dataset.edge=edge;shape.append(handle);
      }
      overlay.append(shape);
      const button=document.createElement('button');
      button.type='button';button.textContent=(box.field||'Manual')+' mask '+(index+1);
      button.setAttribute('aria-pressed',String(index===selected));
      button.onclick=()=>{selected=index;draw();};list.append(button);
    }
    get('[data-undo]').disabled=running||!history.length;
    get('[data-delete]').disabled=running||selected<0;
    get('[data-confirm]').disabled=running;
    get('[data-auto]').disabled=running;
  }
  editor.onpointerdown=event=>{
    if(running||event.button!==0||drag)return;
    event.preventDefault();
    snapshot();
    const shape=event.target.closest('[data-mask]');
    selected=shape?Number(shape.dataset.mask):boxes.length;
    const origin=point(event);
    drag={id:event.pointerId,origin,box:boxes[selected],edge:shape?(event.target.dataset.edge||'move'):'draw'};
    if(!shape)boxes.push({x:origin.x,y:origin.y,w:0,h:0,field:'Manual'});
    editor.setPointerCapture(event.pointerId);
    draw();
  };
  editor.onpointermove=event=>{
    if(!drag||drag.id!==event.pointerId)return;
    const p=point(event),{origin,box,edge}=drag;
    boxes[selected]=edge==='draw'?{x:Math.min(p.x,origin.x),y:Math.min(p.y,origin.y),w:Math.abs(p.x-origin.x),h:Math.abs(p.y-origin.y),field:'Manual'}:moveMask(box,edge,p.x-origin.x,p.y-origin.y);
    draw();
  };
  editor.onpointerup=event=>{
    if(drag?.id!==event.pointerId)return;
    if(!boxes[selected].w||!boxes[selected].h){boxes.splice(selected,1);selected=-1;}
    drag=null;draw();
  };
  editor.onpointercancel=event=>{if(drag?.id===event.pointerId){drag=null;undo();}};
  function undo(){const previous=history.pop();if(previous){({boxes,selected}=previous);draw();}}
  get('[data-undo]').onclick=undo;
  get('[data-delete]').onclick=()=>{if(selected>=0){snapshot();boxes.splice(selected,1);selected=-1;draw();}};
  get('[data-auto]').onclick=async()=>{
    running=true;controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),30000);
    message.textContent='Locating FIN…';draw();
    try{
      const result=maskSuggestions(await readCrop(card,controller.signal));
      if(closed)return;
      if(result.boxes.length){
        snapshot();
        boxes.push(...result.boxes.filter(box=>!boxes.some(b=>Math.abs(b.x-box.x)<.001&&Math.abs(b.y-box.y)<.001&&Math.abs(b.w-box.w)<.001&&Math.abs(b.h-box.h)<.001)));
        selected=boxes.length-1;
      }
      message.textContent=result.uncertain||!result.boxes.length?'Check the FIN manually. OCR could not locate every prefix boundary.':'Check that the original last four FIN characters remain visible.';
    }catch{message.textContent='Recognition unavailable. Draw the mask manually.';}
    finally{clearTimeout(timeout);running=false;if(!closed)draw();}
  };
  draw();dialog.showModal();
  return new Promise(resolve=>{
    function close(ok){closed=true;controller?.abort();dialog.close();dialog.remove();resolve(ok);}
    get('[data-confirm]').onclick=async()=>{
      running=true;draw();
      try{await applyMasks(card,boxes,image);close(true);}
      catch{running=false;message.textContent='Could not apply the masks. Try again.';draw();}
    };
    get('[data-cancel]').onclick=()=>close(false);
    dialog.oncancel=event=>{event.preventDefault();close(false);};
  });
}
