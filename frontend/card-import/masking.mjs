import {readCardLines} from './ocr.mjs';
export function maskSuggestions(lines) {
  const boxes=[];
  for (let i=0;i<lines.length;i++) {
    const line=lines[i],text=line.text;
    const fin=text.match(/\b[FGM]\s*(?:\d\s*){7}[A-Z]\b/i);
    const dob=/\b(date\s*of\s*birth|birth\s*date|DOB|D\.O\.B)\b/i.test(text);
    const wp=/\b(work\s*permit|W\.?P\.?)\s*(no\.?|number|#)/i.test(text);
    if(!fin&&!dob&&!wp)continue;
    let target=line,suffix='';
    if(fin)suffix=fin[0].replace(/\s/g,'').slice(-4).toUpperCase();
    if((dob||wp)&&lines[i+1]&&lines[i+1].y-line.y<line.height*3&&Math.abs(lines[i+1].x-line.x)<.3) {
      const hasValue=dob?/\d{1,4}[ /.-]\w+[ /.-]\d{1,4}/.test(text):/\d(?:[ -]?\d){5,11}/.test(text);
      if(!hasValue)target=lines[i+1];
    }
    if(wp){const n=target.text.match(/\d(?:[ -]?\d){5,11}/);suffix=n?n[0].replace(/\D/g,'').slice(-4):'';}
    const x=Math.max(0,target.x-.008),y=Math.max(0,target.y-.008);
    boxes.push({x,y,w:Math.min(1-x,(target.width||.65)+.016),h:Math.min(1-y,target.height+.016),suffix:dob?'':suffix,field:dob?'Date of birth':fin?'FIN':'Work Permit number'});
  }
  return boxes;
}
export async function reviewMask(card) {
  const original=card.sourceJpeg||card.jpeg,image=new Image();image.src=original;await image.decode();
  const dialog=document.createElement('dialog');dialog.className='mask-dialog';
  dialog.innerHTML='<h2>Review card masking</h2><p>Auto Mask suggests FIN, date of birth and work permit masks. Check all text and codes. Drag on the image to add a mask; select a mask to remove it.</p><div class="actions"><button data-auto>Auto Mask</button><button data-clear class="secondary">Clear masks</button><button data-confirm>Confirm masking</button><button data-cancel class="secondary">Cancel</button></div><p role="status"></p><div class="mask-stage"><canvas></canvas></div><div class="mask-list"></div>';
  document.body.append(dialog);const canvas=dialog.querySelector('canvas'),ctx=canvas.getContext('2d'),message=dialog.querySelector('[role=status]');
  canvas.width=image.width;canvas.height=image.height;
  let boxes=structuredClone(card.maskBoxes||[]),running=false,controller;
  function draw(){ctx.drawImage(image,0,0);for(const b of boxes){ctx.fillStyle='#000';ctx.fillRect(b.x*canvas.width,b.y*canvas.height,b.w*canvas.width,b.h*canvas.height);if(b.suffix){ctx.fillStyle='#fff';ctx.font=`${Math.max(8,b.h*canvas.height*.65)}px Arial`;ctx.fillText(b.suffix,b.x*canvas.width+3,(b.y+b.h*.8)*canvas.height,b.w*canvas.width-6);}}
    const list=dialog.querySelector('.mask-list');list.replaceChildren();boxes.forEach((b,i)=>{const button=document.createElement('button');button.textContent=`Remove ${b.field||'manual mask'} ${i+1}`;button.onclick=()=>{boxes.splice(i,1);draw();};button.disabled=running;list.append(button);});}
  const point=e=>{const r=canvas.getBoundingClientRect();return {x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))};};
  let start;canvas.onpointerdown=e=>{if(running)return;start=point(e);canvas.setPointerCapture(e.pointerId);};canvas.onpointerup=e=>{if(!start)return;const end=point(e),b={x:Math.min(start.x,end.x),y:Math.min(start.y,end.y),w:Math.abs(end.x-start.x),h:Math.abs(end.y-start.y),suffix:'',field:'Manual'};start=null;if(b.w>.003&&b.h>.003)boxes.push(b);draw();};
  dialog.querySelector('[data-auto]').onclick=async()=>{if(running)return;running=true;controller=new AbortController();message.textContent='Reading card locally…';draw();try{boxes=maskSuggestions(await readCardLines(original,controller.signal));message.textContent=boxes.length?'Suggested masks — inspect and correct before confirming.':'No masks detected. Inspect manually; recognition can miss text.';}catch(e){message.textContent='Recognition unavailable. Add masks manually.';}finally{running=false;draw();}};
  dialog.querySelector('[data-clear]').onclick=()=>{if(!running){boxes=[];draw();}};
  draw();dialog.showModal();
  return new Promise(resolve=>{function done(ok){if(running&&ok)return;controller?.abort();if(ok){card.sourceJpeg=original;card.maskBoxes=boxes;card.jpeg=canvas.toDataURL('image/jpeg',.96);card.maskReviewed=true;}dialog.close();dialog.remove();resolve(ok);}
    dialog.querySelector('[data-confirm]').onclick=()=>done(true);dialog.querySelector('[data-cancel]').onclick=()=>done(false);dialog.oncancel=e=>{e.preventDefault();done(false);};});
}
