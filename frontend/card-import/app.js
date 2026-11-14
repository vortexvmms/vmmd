import {uploadSets} from './save.mjs';
import {reviewMask, maskSuggestions, applyMasks} from './masking.mjs';
import {readCrop} from './ocr.mjs';
import {readCourseFields, isWorkPermitFront, applyCourseFields, updateCalculatedExpiry, cardCategory, reviewSides, workerPdfName} from './fields.mjs';
import * as pdfjsLib from './vendor/pdf.mjs';
import {makeCardPdf, matchScannedSides, scanIdentity, selectedSets} from './arrange.mjs';
import {recognizedFin, suggestedTitle} from './titles.mjs';
import {area, detection, encloses, intersection, iou, withMargin} from './detector.mjs';

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdf.worker.mjs', import.meta.url).href;
const $ = id => document.getElementById(id);
const bridge=window.parent!==window?window.parent.workerImportBridge:null;
const DPI_SCALE = 300/72;
const OK = 'Crop OK';
const WARN = 'Check Required';
const failures = new Set(['Multiple Cards','Edge Cut','Mostly Blank','Duplicate']);
const hardBlock = new Set(['Multiple Cards','Duplicate']);
const icons = status => status === OK ? '✓' : failures.has(status) ? '✕' : '⚠';
const clean = s => s.replace(/[\x00-\x1f<>:"/\\|?*]/g,'-').replace(/\s+/g,' ').trim().replace(/[. ]+$/,'');
const pause = () => new Promise(resolve => setTimeout(resolve,0));
const cards = [];
const pages = new Map();
let pdfOrder=[];
let previewUrl;
let pdf, loadTask, currentPage=1, pageData, zoom=1, selected, showBoxes=true, manual=false;
let loading=false, busy=null, lastAuto=[], nextNumber=1, drag, displayVersion=0, exporting=false;

function status(message) { $('status').textContent=message; }
function makeCanvas(width,height) {
  const canvas=document.createElement('canvas');
  canvas.width=Math.max(1,Math.round(width)); canvas.height=Math.max(1,Math.round(height));
  return canvas;
}
function invalidateReview() {
  $('qa').checked=false; $('exportStatus').textContent='';
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl=null; $('pdfPreview').hidden=true; $('pdfPreview').removeAttribute('src');
}
function updateControls() {
  const locked=loading || !!busy || exporting;
  $('pdfInput').disabled=locked;
  for (const id of ['autoAll','autoPage','page','fit','zoomOut','zoomIn','boxes','manual']) $(id).disabled=!pdf || locked;
  $('previous').disabled=!pdf || locked || currentPage<=1;
  $('next').disabled=!pdf || locked || currentPage>=pdf.numPages;
  $('cancel').disabled=!busy || busy.cancelled;
  $('undo').disabled=locked || !lastAuto.some(id=>cards.some(c=>c.id===id));
  $('clearBtn').disabled=locked;
  $('margin').disabled=$('quality').disabled=$('straighten').disabled=locked;
  $('applySides').disabled=locked || !cards.length;
  $('readBatch').disabled=locked || !cards.some(canExport);
  $('qa').disabled=locked;
  $('download').disabled=locked || !$('qa').checked || !clean($('workerName').value) || !cards.some(canExport);
  const pdfDisabled=$('download').disabled || !/^[A-Z0-9]{4}$/i.test($('fin').value.trim());
  $('downloadPdf').disabled=$('previewPdf').disabled=pdfDisabled;
  $('saveWorker').disabled=locked||!bridge||!$('qa').checked||!cards.some(canExport);
  $('download').textContent=clean($('workerName').value) ? `Download ${workerName()}.zip` : 'Download worker ZIP';
}
function workerName() { return clean($('workerName').value).toUpperCase().replace(/\s+/g,'_'); }
function canExport(card) { return card.include && !!card.jpeg && !hardBlock.has(card.status); }
function option(text,value=text) { return new Option(text,value); }

async function pageImage(number, job) {
  const page=await pdf.getPage(number);
  if (job?.cancelled) throw new DOMException('Cancelled','AbortError');
  const full=page.getViewport({scale:DPI_SCALE});
  const scale=Math.min(1,4200/Math.max(full.width,full.height),Math.sqrt(13500000/(full.width*full.height)));
  const viewport=scale===1 ? full : page.getViewport({scale:DPI_SCALE*scale});
  const canvas=makeCanvas(viewport.width,viewport.height);
  const context=canvas.getContext('2d',{willReadFrequently:true});
  const task=page.render({canvasContext:context,viewport,background:'#fff'});
  if (job) job.interrupt=()=>task.cancel();
  await task.promise;
  if (job) job.interrupt=null;
  return {canvas,context,page,viewport,marginScale:scale};
}

function physicalCandidates(image, job) {
  const {canvas}=image;
  const scale=Math.min(1,detection.maxAnalysisSide/Math.max(canvas.width,canvas.height));
  const small=makeCanvas(canvas.width*scale,canvas.height*scale);
  const context=small.getContext('2d',{willReadFrequently:true});
  context.drawImage(canvas,0,0,small.width,small.height);
  const pixels=context.getImageData(0,0,small.width,small.height).data;
  return new Promise((resolve,reject)=>{
    const worker=new Worker(new URL('./detect-worker.mjs',import.meta.url),{type:'module'});
    const finish=(callback,value)=>{ worker.terminate(); job.interrupt=null; callback(value); };
    job.interrupt=()=>finish(reject,new DOMException('Cancelled','AbortError'));
    worker.onmessage=event=>finish(resolve,event.data);
    worker.onerror=event=>finish(reject,new Error(event.message || 'Card detection failed.'));
    worker.postMessage({pixels,width:small.width,height:small.height,
      sourceWidth:canvas.width,sourceHeight:canvas.height},[pixels.buffer]);
  });
}

async function readPageInfo(image) {
  const {page,viewport,canvas}=image;
  const [text,ops]=await Promise.all([page.getTextContent(),page.getOperatorList()]);
  const words=text.items.filter(item=>item.str && item.transform).map(item=>{
    const [x,y]=viewport.convertToViewportPoint(item.transform[4],item.transform[5]);
    return {x,y,text:item.str.trim(),size:Math.abs(item.height*viewport.scale)};
  });
  const rasterSizes=ops.fnArray.flatMap((op,i)=>{
    const args=ops.argsArray[i] || [];
    if (op===pdfjsLib.OPS.paintImageXObject && args[1] && args[2]) return [[args[1],args[2]]];
    if (op===pdfjsLib.OPS.paintInlineImageXObject && args[0]?.width) return [[args[0].width,args[0].height]];
    return [];
  });
  const pageScan=rasterSizes.find(([w,h])=>Math.abs(w/h-canvas.width/canvas.height)<.09 && h>=400);
  const estimatedDpi=pageScan ? Math.min(pageScan[0]/canvas.width,pageScan[1]/canvas.height)*viewport.scale*72 : null;
  return {words,estimatedDpi};
}

function embeddedTitle(card,info) {
  if (card.side!=='Front' || hardBlock.has(card.status) || card.status==='Mostly Blank') return '';
  const box=card.box;
  const lines=info.words.filter(word=>word.x>=box.x && word.x<=box.x+box.w &&
    word.y>=box.y && word.y<=box.y+box.h*.65).sort((a,b)=>a.y-b.y || a.x-b.x);
  const rows=[];
  for (const word of lines) {
    const row=rows.find(r=>Math.abs(r[0].y-word.y)<Math.max(4,word.size*.4));
    if (row) row.push(word); else rows.push([word]);
  }
  return suggestedTitle(rows.map(row=>row.sort((a,b)=>a.x-b.x).map(word=>word.text).join(' ')));
}

async function reviewBatch(sets) {
  const job={cancelled:false,interrupt:null};
  busy=job;invalidateReview();render();
  let failed=0;
  const read=async card=>{
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),30000);
    job.interrupt=()=>controller.abort();
    try{return await readCrop(card,controller.signal);}
    catch{failed++;return [];}
    finally{clearTimeout(timeout);job.interrupt=null;}
  };
  try{
    for(const [index,set] of sets.entries()){
      if(job.cancelled)break;
      if(!set.front)continue;
      const front=set.front;
      status(`Reading card set ${index+1} of ${sets.length}…`);
      const lines=await read(front);
      if(job.cancelled)break;
      const backLines=set.back?await read(set.back):[];
      if(job.cancelled)break;
      const heading=suggestedTitle(lines);
      if(!front.category&&(isWorkPermitFront(lines)||heading==='Work Permit'))front.category='work_permit';
      const workPermit=cardCategory(front)==='work_permit';
      const fields=readCourseFields(lines,backLines,{workPermit});
      if(workPermit){
        front.ocrFields={cert_no:fields.cert_no};
        if(!front.editedFields?.cert_no)front.cert_no=fields.cert_no.value;
        if(!front.titleEdited)front.title=heading==='S Pass'?'S Pass':'Work Permit';
      }else if(cardCategory(front)==='course'&&(lines.length||backLines.length)){
        if(!fields.title.value&&!fields.title.sources.length&&heading){
          fields.title.value=heading;
          fields.title.sources.push({side:'Front',text:heading});
        }
        applyCourseFields(front,fields);
      }
      if(!$('fin').value)$('fin').value=recognizedFin(lines)||recognizedFin(backLines);
      for(const card of reviewSides(set)){
        if(card.maskBoxes?.length)continue;
        const suggested=maskSuggestions(card===front?lines:backLines);
        card.maskNeedsAttention=suggested.uncertain||!suggested.boxes.length;
        if(suggested.boxes.length)await applyMasks(card,suggested.boxes);
      }
    }
    status(job.cancelled?'Card reading cancelled.':`Check the crop previews and fields below.${failed?' OCR unavailable on '+failed+' side(s). Enter those details manually.':''}`);
  }catch(error){status('Could not finish card review: '+error.message);}
  finally{busy=null;render();}
}

function sampleCrop(canvas) {
  const scale=Math.min(1,520/Math.max(canvas.width,canvas.height));
  const sample=makeCanvas(canvas.width*scale,canvas.height*scale);
  const context=sample.getContext('2d',{willReadFrequently:true});
  context.drawImage(canvas,0,0,sample.width,sample.height);
  const {width:w,height:h}=sample;
  const pixels=context.getImageData(0,0,w,h).data;
  const isDark=(data,i)=>Math.min(data[i],data[i+1],data[i+2])<224;
  const dark=(x,y)=>isDark(pixels,(y*w+x)*4);
  let ink=0;
  for (let y=0;y<h;y+=2) for (let x=0;x<w;x+=2) ink+=dark(x,y);
  const full=canvas.getContext('2d');
  const {width,height}=canvas;
  const vertical=Math.min(2,width),horizontal=Math.min(2,height);
  const strips={left:[0,0,vertical,height],right:[width-vertical,0,vertical,height],
    top:[0,0,width,horizontal],bottom:[0,height-horizontal,width,horizontal]};
  const contacts=Object.entries(strips).filter(([,rect])=>{
    const band=full.getImageData(...rect).data;
    let darkPixels=0;
    for (let i=0;i<band.length;i+=4) darkPixels+=isDark(band,i);
    return darkPixels>=Math.max(6,band.length/4*.045);
  }).map(([side])=>side);
  return {contacts,blank:ink/(Math.ceil(w/2)*Math.ceil(h/2))<.006};
}

function copyCrop(source,box) {
  const canvas=makeCanvas(box.w,box.h);
  const context=canvas.getContext('2d');
  context.fillStyle='#fff'; context.fillRect(0,0,canvas.width,canvas.height);
  context.drawImage(source,box.x,box.y,box.w,box.h,0,0,canvas.width,canvas.height);
  return canvas;
}
function rotateCrop(canvas,angle) {
  const sin=Math.abs(Math.sin(angle)),cos=Math.abs(Math.cos(angle));
  const out=makeCanvas(Math.ceil(canvas.width*cos+canvas.height*sin)+16,
    Math.ceil(canvas.width*sin+canvas.height*cos)+16);
  const context=out.getContext('2d');
  context.fillStyle='#fff'; context.fillRect(0,0,out.width,out.height);
  context.translate(out.width/2,out.height/2); context.rotate(-angle);
  context.drawImage(canvas,-canvas.width/2,-canvas.height/2);
  return out;
}

function validate(card, info, width, height, cropBox, sample) {
  const {box,boundary}=card;
  const known=info.boxes.filter(other=>iou(box,other)<.70);
  const contained=info.boxes.filter(other=>encloses(box,other));
  const mostlyInCrop=info.boxes.filter(other=>intersection(cropBox,other)/area(other)>.62);
  if ([contained,mostlyInCrop].some(group=>group.some((a,i)=>group.slice(i+1).some(b=>iou(a,b)<.18)))) return 'Multiple Cards';
  if (cards.some(other=>other!==card && other.page===card.page && other.number<card.number && iou(other.box,box)>.80)) return 'Duplicate';
  if (sample.blank) return 'Mostly Blank';
  const againstPage=(side)=>({left:cropBox.x<=1,top:cropBox.y<=1,
    right:cropBox.x+cropBox.w>=width-1,bottom:cropBox.y+cropBox.h>=height-1})[side];
  if (boundary?.incomplete || sample.contacts.some(againstPage)) return 'Original Scan Incomplete';
  if (known.some(other=>intersection(cropBox,other)>Math.max(18,area(other)*.005))) return WARN;
  if (boundary && intersection(cropBox,boundary)/area(boundary)<.988) return 'Edge Cut';
  if (sample.contacts.length) return 'Edge Cut';
  if (Math.min(box.w,box.h)<160 || (info.estimatedDpi!==null && info.estimatedDpi<125)) return 'Low Resolution';
  if (!boundary || boundary.confidence<.79 || Math.abs(boundary.angle)>.26 || box.w/box.h<.42 || box.w/box.h>2.46) return WARN;
  return OK;
}

function makePreview(card,image,info) {
  const started=performance.now();
  const {canvas,marginScale}=image;
  const w=canvas.width,h=canvas.height;
  const margin=Math.round(Number($('margin').value)*marginScale);
  let cropBox=withMargin(card.box,info.boxes,w,h,margin);
  let crop=copyCrop(canvas,cropBox), sample=sampleCrop(crop);
  if (sample.contacts.length) {
    const expanded=withMargin(card.box,info.boxes,w,h,margin+24);
    const edges={left:cropBox.x,right:cropBox.x+cropBox.w,top:cropBox.y,bottom:cropBox.y+cropBox.h};
    for (const side of sample.contacts) edges[side]=({left:expanded.x,top:expanded.y,
      right:expanded.x+expanded.w,bottom:expanded.y+expanded.h})[side];
    cropBox={x:edges.left,y:edges.top,w:edges.right-edges.left,h:edges.bottom-edges.top};
    crop=copyCrop(canvas,cropBox); sample=sampleCrop(crop);
  }
  card.status=validate(card,info,w,h,cropBox,sample);
  const angle=card.boundary?.angle || 0;
  if ($('straighten').checked && card.status===OK && Math.abs(angle)>.012 && Math.abs(angle)<=.26) crop=rotateCrop(crop,angle);
  card.maskReviewed=false;card.maskNeedsAttention=false;card.maskBoxes=[];card.sourceJpeg=null;
  card.jpeg=crop.toDataURL('image/jpeg',Number($('quality').value));
  card.size=`${crop.width} × ${crop.height}`;
  card.include=card.status===OK;
  console.debug('Worker card crop preparation duration (ms)',Math.round(performance.now()-started));
}

async function preparePage(number,image,job) {
  if (pages.has(number)) return pages.get(number);
  const boxes=await physicalCandidates(image,job);
  const info=await readPageInfo(image);
  info.boxes=boxes;
  pages.set(number,info);
  return info;
}
function newCard(page,box,boundary,side='Front') {
  const number=nextNumber++;
  return {id:crypto.randomUUID(),number,page,box:{x:box.x,y:box.y,w:box.w,h:box.h},boundary,
    title:`Card ${String(number).padStart(2,'0')}`,side,partner:null,include:false};
}

function updatePosition(card,canvas) {
  const {x,y,w,h}=card.box;
  card.position={x:(x+w/2)/canvas.width,y:(y+h/2)/canvas.height,w:w/canvas.width,h:h/canvas.height};
}
function autoPair() { matchScannedSides(cards,$('pairMode').value,pdf.numPages); }
function displayTitle(card) {
  const front=card.side==='Back' && !card.titleEdited && cards.find(item=>item.id===card.partner && item.side==='Front');
  return front ? front.title : card.title;
}

async function runAuto(all) {
  const job={cancelled:false,interrupt:null};
  busy=job; manual=false; updateControls(); renderBoxes();
  $('progress').hidden=false; $('progress').value=0;
  const targets=all ? Array.from({length:pdf.numPages},(_,i)=>i+1) : [currentPage];
  const added=[];
  try {
    for (const [index,number] of targets.entries()) {
      if (job.cancelled) break;
      status(`Processing page ${number} of ${pdf.numPages} · Detecting card candidates`);
      const image=number===currentPage && pageData ? pageData : await pageImage(number,job);
      const info=await preparePage(number,image,job);
      for (const [i,box] of info.boxes.entries()) {
        if (job.cancelled) break;
        if (cards.some(card=>card.page===number && iou(card.box,box)>.67)) continue;
        status(`Page ${number} of ${pdf.numPages} · Validating crop ${i+1} of ${info.boxes.length}`);
        await pause();
        if (job.cancelled) break;
        const card=newCard(number,box,box,defaultSide(number));
        makePreview(card,image,info);
        updatePosition(card,image.canvas);
        card.title=embeddedTitle(card,info) || card.title;
        cards.push(card); added.push(card.id);
      }
      autoPair();
      $('progress').value=(index+1)/targets.length*100;
      render();
    }
    const accepted=cards.filter(card=>added.includes(card.id) && card.status===OK).length;
    status(`${job.cancelled?'Processing cancelled. ':''}${added.length} new candidates · ${accepted} Crop OK · ${added.length-accepted} to review.${!job.cancelled && !added.length ? ' Add a missed card manually or review existing crops.' : ''}`);
  } catch (error) {
    status(job.cancelled ? `Processing cancelled. ${added.length} completed crops kept.` : `Auto crop stopped: ${error.message}`);
  } finally {
    if (added.length) { lastAuto=added; autoPair(); invalidateReview(); }
    busy=null; $('progress').hidden=true; render();
  }
}

function setZoom(value) {
  zoom=Math.min(4,Math.max(.6,value));
  if (!pageData) return;
  const viewer=$('viewer');
  const fitted=Math.min(viewer.clientWidth,viewer.clientHeight*pageData.canvas.width/pageData.canvas.height);
  $('sheet').style.width=`${Math.max(1,fitted)*zoom}px`;
}
function fitPage() {
  if (!pageData) return;
  const viewer=$('viewer');
  const maxHeight=Math.min(window.innerHeight*(window.innerWidth<=560?.60:.72),
    viewer.clientWidth*pageData.canvas.height/pageData.canvas.width);
  viewer.style.height=`${Math.round(maxHeight)+2}px`;
  setZoom(1); viewer.scrollTo(0,0);
}
async function showPage(number) {
  if (!pdf) return;
  const version=++displayVersion;
  pageData=null; currentPage=number; $('page').value=number; loading=true;
  updateControls(); $('overlay').replaceChildren();
  try {
    const image=await pageImage(number);
    if (version!==displayVersion) return;
    pageData=image;
    const visible=$('pageCanvas');
    const scale=Math.min(1,1600/Math.max(image.canvas.width,image.canvas.height));
    visible.width=Math.round(image.canvas.width*scale); visible.height=Math.round(image.canvas.height*scale);
    visible.getContext('2d').drawImage(image.canvas,0,0,visible.width,visible.height);
    $('viewer').hidden=false; fitPage(); renderBoxes();
  } catch (error) { status(`Could not display page ${number}: ${error.message}`); }
  finally { if (version===displayVersion) { loading=false; updateControls(); } }
}

function bounds(element,box) {
  const {width,height}=pageData.canvas;
  Object.assign(element.style,{left:`${box.x/width*100}%`,top:`${box.y/height*100}%`,
    width:`${box.w/width*100}%`,height:`${box.h/height*100}%`});
}
const handles={nw:[0,0],n:[50,0],ne:[100,0],e:[100,50],se:[100,100],s:[50,100],sw:[0,100],w:[0,50]};
function renderBoxes() {
  const overlay=$('overlay'); overlay.replaceChildren();
  overlay.classList.toggle('drawing',manual);
  $('manual').setAttribute('aria-pressed',String(manual));
  $('boxes').setAttribute('aria-pressed',String(showBoxes));
  $('boxes').textContent=showBoxes?'Hide Detection Boxes':'Show Detection Boxes';
  const active=cards.find(card=>card.id===selected && card.page===currentPage);
  $('selection').hidden=!active;
  $('selectedInfo').textContent=active ? `Card ${active.number} · Page ${active.page} · ${active.status}` : '';
  $('duplicate').disabled=$('deleteSelected').disabled=loading || !!busy || exporting;
  if (!pageData || !showBoxes) return;
  for (const card of cards.filter(card=>card.page===currentPage)) {
    const box=document.createElement('div');
    box.className=`box ${card.status===OK?'ok':failures.has(card.status)?'fail':''} ${card===active?'active':''}`;
    box.tabIndex=0; box.setAttribute('role','button');
    box.setAttribute('aria-label',`Card ${card.number} · ${card.status}`);
    const label=document.createElement('span'); label.className='box-label'; label.textContent=`Card ${card.number}`;
    box.append(label); bounds(box,card.box);
    box.onkeydown=event=>{ if (event.target===box && ['Enter',' '].includes(event.key)) {event.preventDefault(); selectCard(card,true);} };
    box.onpointerdown=event=>{ if (!manual && !busy && !loading) beginDrag(event,card,event.target.dataset.handle || 'move'); };
    if (card===active && !manual) for (const [direction,[left,top]] of Object.entries(handles)) {
      const handle=document.createElement('button'); handle.type='button'; handle.className=`handle ${direction}`;
      handle.dataset.handle=direction; handle.style.left=`${left}%`; handle.style.top=`${top}%`;
      handle.setAttribute('aria-label',`Adjust ${direction.toUpperCase()} edge or corner`);
      handle.onkeydown=event=>keyboardResize(event,card,direction);
      box.append(handle);
    }
    overlay.append(box);
  }
}
function selectCard(card,scrollReview=false) {
  selected=card.id; manual=false;
  if (scrollReview) $('filter').value='All';
  render();
  if (scrollReview) $(`review-${card.id}`)?.scrollIntoView({block:'nearest'});
}
function point(event) {
  const rect=$('overlay').getBoundingClientRect();
  const {width,height}=pageData.canvas;
  return {x:Math.max(0,Math.min(width,(event.clientX-rect.left)/rect.width*width)),
    y:Math.max(0,Math.min(height,(event.clientY-rect.top)/rect.height*height))};
}
function boundedBox(x,y,r,b) {
  return {x:Math.round(x),y:Math.round(y),w:Math.max(1,Math.round(r)-Math.round(x)),h:Math.max(1,Math.round(b)-Math.round(y))};
}
function adjustedBox(box,mode,dx,dy) {
  const {width,height}=pageData.canvas;
  if (mode==='move') {
    const x=Math.max(0,Math.min(width-box.w,box.x+dx));
    const y=Math.max(0,Math.min(height-box.h,box.y+dy));
    return boundedBox(x,y,x+box.w,y+box.h);
  }
  let {x,y}=box,r=x+box.w,b=y+box.h;
  if (mode.includes('w')) x=Math.max(0,Math.min(r-16,x+dx));
  if (mode.includes('e')) r=Math.min(width,Math.max(x+16,r+dx));
  if (mode.includes('n')) y=Math.max(0,Math.min(b-16,y+dy));
  if (mode.includes('s')) b=Math.min(height,Math.max(y+16,b+dy));
  return boundedBox(x,y,r,b);
}
function beginDrag(event,card,mode) {
  if (event.button!==0 || drag || !pageData) return;
  event.preventDefault(); event.stopPropagation();
  const overlay=$('overlay');
  const ghost=document.createElement('div'); ghost.className='box draft'; ghost.style.pointerEvents='none';
  overlay.append(ghost); overlay.setPointerCapture(event.pointerId);
  drag={start:point(event),card,mode,ghost,pointer:event.pointerId,moved:false};
  if (card) bounds(ghost,card.box);
}
$('overlay').onpointerdown=event=>{ if (manual && !busy && !loading) beginDrag(event,null,'draw'); };
$('overlay').onpointermove=event=>{
  if (!drag || drag.pointer!==event.pointerId) return;
  const p=point(event),{start,card,mode,ghost}=drag;
  const dx=p.x-start.x,dy=p.y-start.y;
  if (Math.hypot(dx,dy)<5 && !drag.moved) return;
  drag.moved=true;
  drag.box=card ? adjustedBox(card.box,mode,dx,dy) : boundedBox(Math.min(start.x,p.x),Math.min(start.y,p.y),Math.max(start.x,p.x),Math.max(start.y,p.y));
  bounds(ghost,drag.box);
};
$('overlay').onpointercancel=()=>{ drag?.ghost.remove(); drag=null; };
$('overlay').onpointerup=event=>{
  if (!drag || drag.pointer!==event.pointerId) return;
  const {box,card,ghost}=drag;
  drag=null; ghost.remove();
  if (box && box.w>=16 && box.h>=16) void saveBox(card,box);
  else if (card) selectCard(card,true);
};
function keyboardResize(event,card,direction) {
  const shift={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
  if (!shift) return;
  event.preventDefault();
  void saveBox(card,adjustedBox(card.box,direction,shift[0]*8,shift[1]*8));
}
async function saveBox(card,box) {
  if (!pageData || busy || loading) return;
  const job={cancelled:false,interrupt:null};
  const image=pageData, number=currentPage;
  busy=job; updateControls();
  try {
    const info=await preparePage(number,image,job);
    if (job.cancelled) return;
    const nearby=info.boxes.find(candidate=>iou(candidate,box)>.65);
    const boundary=nearby || (card?.boundary && intersection(card.boundary,box)>area(card.boundary)*.28 ? card.boundary : null);
    const result=card || newCard(number,box,boundary,defaultSide(number));
    result.box=box; result.boundary=boundary;
    makePreview(result,image,info);
    updatePosition(result,image.canvas);
    if (!card) { result.title=embeddedTitle(result,info) || result.title; cards.push(result); }
    if (card && !card.pairOverride) unpair(card);
    autoPair();
    selected=result.id; manual=false; showBoxes=true; $('filter').value='All';
    invalidateReview(); status(`Card ${result.number} · ${result.status}`);
  } catch (error) { status(job.cancelled?'Crop edit cancelled.':`Could not save crop: ${error.message}`); }
  finally { busy=null; render(); }
}

function defaultSide(number) {
  const mode=$('pairMode').value;
  if (mode==='pairs') return number%2?'Front':'Back';
  return mode==='split' && number>Math.ceil(pdf.numPages/2)?'Back':'Front';
}
function unpair(card) {
  const other=cards.find(item=>item.id===card.partner);
  if (other) other.partner=null;
  card.partner=null;
}
function removeCard(card) {
  if (busy || loading || exporting) return;
  unpair(card);
  cards.splice(cards.indexOf(card),1);
  if (selected===card.id) selected=null;
  invalidateReview(); render();
}
function button(text,action,style='secondary',disabled=false) {
  const element=document.createElement('button');
  element.type='button'; element.textContent=text; element.className=style; element.onclick=action; element.disabled=disabled;
  return element;
}
function labelField(name,element) {
  const label=document.createElement('label'); label.append(name,element); return label;
}
function renderGallery() {
  const gallery=$('gallery'); gallery.replaceChildren();
  const filter=$('filter').value;
  const shown=cards.filter(card=>filter==='All' || filter===card.side || filter===card.status ||
    (filter==='Unpaired' && !card.partner) || (filter==='Failed' && failures.has(card.status)) ||
    (filter===WARN && card.status!==OK && !failures.has(card.status)));
  const ready=cards.filter(c=>c.status===OK).length;
  $('count').textContent=`${cards.length} crops · ${ready} Crop OK · ${cards.length-ready} to review`;
  if (!shown.length) {
    const empty=document.createElement('div'); empty.className='empty';
    empty.textContent=cards.length ? 'No crops match this filter.' : 'Load a PDF and select Auto Crop All Pages.';
    gallery.append(empty);
    return;
  }
  for (const card of shown) {
    const locked=loading || !!busy || exporting;
    const tile=document.createElement('article'); tile.className=`tile ${selected===card.id?'selected':''}`;
    tile.id=`review-${card.id}`;
    const preview=document.createElement('div'); preview.className='preview';
    const image=document.createElement('img'); image.src=card.jpeg; image.alt=`Card ${card.number} crop from page ${card.page}`;
    image.loading='lazy'; preview.append(image);
    const meta=document.createElement('div'); meta.className='meta';
    const confidence=card.boundary ? `${Math.round(card.boundary.confidence*100)}% detection confidence` : 'Manual crop';
    meta.textContent=`Card ${card.number} · Page ${card.page} · ${confidence} · ${card.size} px`;
    const badge=document.createElement('div'); badge.className=`badge ${card.status===OK?'ok':failures.has(card.status)?'fail':''}`;
    badge.textContent=`${icons(card.status)} ${card.status}`;
    const title=document.createElement('textarea'); title.rows=2; title.value=displayTitle(card); title.disabled=locked;
    title.oninput=()=>{ card.title=title.value; card.titleEdited=true; invalidateReview(); updateControls();
      const back=cards.find(item=>item.id===card.partner && item.side==='Back' && !item.titleEdited);
      if (back) {
        const input=$(`review-${back.id}`)?.querySelector('textarea');
        if (input) input.value=displayTitle(back);
      }
      renderPdfOrder(); };
    const side=document.createElement('select'); side.append(option('Front'),option('Back')); side.value=card.side; side.disabled=locked;
    side.onchange=()=>{ unpair(card); card.pairOverride=true; card.side=side.value; invalidateReview(); render(); };
    const pair=document.createElement('select'); pair.append(option('Unpaired / one-sided',''));
    for (const candidate of cards.filter(other=>other.side!==card.side && (!other.partner || other.partner===card.id))) {
      pair.append(option(`Card ${candidate.number} · Page ${candidate.page} · ${candidate.title}`,candidate.id));
    }
    pair.disabled=locked; pair.value=card.partner || '';
    pair.onchange=()=>{
      const previous=cards.find(item=>item.id===card.partner);
      if (previous) previous.pairOverride=true;
      unpair(card); card.pairOverride=true;
      const other=cards.find(item=>item.id===pair.value);
      if (other && !other.partner && other.side!==card.side) { card.partner=other.id; other.partner=card.id; other.pairOverride=true; }
      invalidateReview(); render();
    };
    const include=document.createElement('input'); include.type='checkbox'; include.checked=canExport(card);
    include.disabled=locked || hardBlock.has(card.status);
    include.onchange=()=>{ card.include=include.checked; invalidateReview(); updateControls(); renderPdfOrder(); };
    const includeLabel=labelField(card.status===OK?'Include in export':'Approve for export',include);
    includeLabel.className='inline'; includeLabel.prepend(include);
    const actions=document.createElement('div'); actions.className='tileActions';
    if(card.side==='Front'&&!hardBlock.has(card.status))actions.append(button('Read card details',()=>reviewBatch([{front:card,back:cards.find(item=>item.id===card.partner)}]),'secondary',locked));
    actions.append(button(card.maskBoxes?.length?'Edit masks':'Review / Auto Mask',async()=>{
      if(await reviewMask(card)){card.maskNeedsAttention=false;invalidateReview();render();}
    },'secondary',locked));
    actions.append(button('Edit / Re-crop',async()=>{
      selected=card.id; showBoxes=true; manual=false;
      if (currentPage!==card.page || !pageData) await showPage(card.page);
      render();
      $('editor').scrollIntoView({block:'start'});
      const box=$('overlay').querySelector('.active');
      box?.focus({preventScroll:true});
    },'secondary',locked),button('Delete',()=>removeCard(card),'danger',locked));
    tile.append(preview,meta,badge,labelField('Course / card title',title),labelField('Side',side),
      labelField('Pair Front / Back',pair),actions,includeLabel);
    const front=card.side==='Front'?card:cards.find(item=>item.id===card.partner&&item.side==='Front');
    if(front&&reviewSides({front,back:card.side==='Back'?card:null}).includes(card)){
      const badge=document.createElement('small');badge.className='field-source';
      badge.textContent=card.maskBoxes?.length?'Check suggested or edited mask':'Check this side for FIN';
      tile.append(badge);
    }
    if(card.saveError){const error=document.createElement('p');error.className='field-source';error.textContent='Save failed: '+card.saveError;tile.append(error);}
    if(card.maskNeedsAttention){
      const warning=document.createElement('p');warning.className='field-source';
      warning.textContent='Check this side for FIN and adjust masking if needed.';tile.append(warning);
    }
    if(card.side==='Front'){
      const category=document.createElement('select');
      for(const [value,label] of [['course','Course card'],['work_permit','Work permit'],['visit_pass','Visit pass'],['other','Other']])category.append(option(label,value));
      category.value=cardCategory(card);category.disabled=locked;
      category.onchange=()=>{card.category=category.value;invalidateReview();render();};
      tile.append(labelField('Card type',category));
      const fieldSource=key=>{
        const field=card.ocrFields?.[key];
        const calculated=key==='expiry_date'&&card.expiry_date&&!card.editedFields?.expiry_date&&!field?.sources.length&&card.ocrFields?.period.value;
        const info=calculated?card.ocrFields.period:field;
        if(key==='expiry_date'&&card.no_expiry)return;
        if(!info||card.editedFields?.[key]||key==='title'&&card.titleEdited)return;
        const note=document.createElement('small');note.className='field-source';
        note.textContent=(calculated?'Calculated from validity':info.review?'Check this field':'Read from card')+
          (info.sources.length?' · '+info.sources.map(source=>source.side+': '+source.text).join(' | '):' · no reliable value found');
        tile.append(note);
      };
      fieldSource('title');
      const needsCourseEnd=card.ocrFields?.period.value?.basis==='course_end_date'&&!card.ocrFields.expiry_date.sources.length;
      const fields=[['institute','Institute','text'],['cert_no','Certificate number','text'],['issued_date','Issue date','date'],['expiry_date','Expiry date','date']];
      if(needsCourseEnd)fields.splice(3,0,['course_end_date','Last date of course','date']);
      for(const [key,label,type] of fields){
        if(type==='date'&&cardCategory(card)==='work_permit')continue;
        const field=document.createElement('input');field.type=type;field.value=card[key]||'';field.disabled=locked;
        field.onchange=()=>{
          card[key]=field.value;(card.editedFields??={})[key]=true;
          if(key==='issued_date'||key==='course_end_date')updateCalculatedExpiry(card);
          if(key==='expiry_date'&&field.value){card.no_expiry=false;card.editedFields.no_expiry=true;}
          invalidateReview();render();
        };
        tile.append(labelField(label,field));fieldSource(key);
      }
      if(needsCourseEnd&&!card.course_end_date&&!card.expiry_date){
        const note=document.createElement('small');note.className='field-source';
        note.textContent='Enter the confirmed last date of the course to calculate expiry. '+card.ocrFields.period.sources.map(source=>source.side+': '+source.text).join(' | ');
        tile.append(note);
      }
      if(cardCategory(card)!=='work_permit'){
        const no=document.createElement('input');no.type='checkbox';no.checked=!!card.no_expiry;no.disabled=locked;
        no.onchange=()=>{(card.editedFields??={}).no_expiry=true;card.no_expiry=no.checked;if(no.checked)card.expiry_date='';else updateCalculatedExpiry(card);invalidateReview();render();};
        tile.append(labelField('No expiry',no));
        if(card.no_expiry&&card.ocrFields?.no_expiry?.sources.length)fieldSource('no_expiry');
      }
    }
    if (hardBlock.has(card.status)) {
      const message=document.createElement('p'); message.textContent='Correct or delete this crop before export.'; tile.append(message);
    }
    gallery.append(tile);
  }
}
function render() { renderBoxes(); renderGallery(); renderPdfOrder(); updateControls(); }

async function refreshPreviews() {
  if (!cards.length) return;
  const job={cancelled:false,interrupt:null};
  busy=job; invalidateReview(); render();
  const processed=new Set();
  try {
    for (const number of new Set(cards.map(card=>card.page))) {
      if (job.cancelled) break;
      status(`Updating crops on page ${number} of ${pdf.numPages}`);
      const image=number===currentPage && pageData ? pageData : await pageImage(number,job);
      const info=await preparePage(number,image,job);
      for (const card of cards.filter(item=>item.page===number)) {
        if (job.cancelled) break;
        makePreview(card,image,info); processed.add(card.id); await pause();
      }
    }
    status(job.cancelled?'Update cancelled. Reapply settings to refresh the remaining crops.':'Crop previews updated. Review them before export.');
  } catch (error) {
    status(job.cancelled?'Update cancelled. Reapply settings to refresh the remaining crops.':`Could not update all previews: ${error.message}`);
  } finally {
    for (const card of cards) if (!processed.has(card.id)) card.include=false;
    busy=null; render();
  }
}

$('pdfInput').onchange=async event=>{
  const file=event.target.files[0];
  if (!file) return;
  loading=true; updateControls();
  status('Opening PDF…');
  let task;
  try {
    task=pdfjsLib.getDocument({data:new Uint8Array(await file.arrayBuffer()),useWorkerFetch:false,isEvalSupported:false});
    const loaded=await task.promise;
    const previous=loadTask;
    pdf=loaded; loadTask=task; cards.length=0; pages.clear(); selected=null; lastAuto=[]; nextNumber=1; manual=false;
    if (previous) void previous.destroy().catch(console.error);
    const identity=scanIdentity(file.name);
    $('workerName').value=bridge?.identity.name||identity.name; $('fin').value=bridge?.identity.fin_last4||identity.fin; pdfOrder=[];
    $('page').replaceChildren(...Array.from({length:pdf.numPages},(_,i)=>option(`${i+1} of ${pdf.numPages}`,i+1)));
    invalidateReview();
    await showPage(1);
    if (pageData) status(`${pdf.numPages} ${pdf.numPages===1?'page':'pages'} loaded. Choose a page or crop all pages.`);
  } catch (error) {
    if (task && task!==loadTask) void task.destroy().catch(console.error);
    status(`Could not open PDF: ${error.message}`);
  } finally { loading=false; render(); }
};
$('autoAll').onclick=()=>runAuto(true);
$('autoPage').onclick=()=>runAuto(false);
$('cancel').onclick=()=>{
  if (!busy) return;
  busy.cancelled=true; busy.interrupt?.(); updateControls(); status('Cancelling processing…');
};
$('undo').onclick=()=>{
  for (let index=cards.length-1;index>=0;index--) if (lastAuto.includes(cards[index].id)) {
    unpair(cards[index]); cards.splice(index,1);
  }
  if (lastAuto.includes(selected)) selected=null;
  lastAuto=[]; invalidateReview(); render(); status('Last automatic crop run undone.');
};
$('page').onchange=()=>showPage(Number($('page').value));
$('previous').onclick=()=>showPage(currentPage-1);
$('next').onclick=()=>showPage(currentPage+1);
$('fit').onclick=fitPage;
$('zoomIn').onclick=()=>setZoom(zoom*1.3);
$('zoomOut').onclick=()=>setZoom(zoom/1.3);
window.addEventListener('resize',()=>{ if (zoom===1) fitPage(); else setZoom(zoom); });
$('boxes').onclick=()=>{ showBoxes=!showBoxes; renderBoxes(); };
$('manual').onclick=()=>{
  manual=!manual;
  if (manual) status('Drag a box around one physical card. Include all edges and corners.');
  renderBoxes();
};
$('duplicate').onclick=()=>{
  const card=cards.find(item=>item.id===selected);
  if (!card) return;
  const copy=newCard(card.page,card.box,null,card.side);
  Object.assign(copy,{title:card.title,jpeg:card.jpeg,size:card.size,status:'Duplicate'});
  cards.push(copy); selected=copy.id; showBoxes=true; invalidateReview(); render();
  status('Box duplicated. Move or resize it to cover a different card.');
};
$('deleteSelected').onclick=()=>{ const card=cards.find(item=>item.id===selected); if (card) removeCard(card); };
$('applySides').onclick=()=>{
  for (const card of cards) {
    const side=defaultSide(card.page);
    unpair(card); card.side=side; card.pairOverride=false;
  }
  autoPair(); invalidateReview(); render();
};
$('filter').onchange=renderGallery;
for (const id of ['margin','quality','straighten']) $(id).onchange=refreshPreviews;
$('workerName').oninput=()=>{ invalidateReview(); updateControls(); };
$('fin').oninput=()=>{
  $('fin').value=$('fin').value.toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,4);
  invalidateReview(); updateControls();
};
$('qa').onchange=updateControls;
$('clearBtn').onclick=()=>{
  if ((pdf || cards.length) && !window.confirm('Clear the PDF and all crop edits?')) return;
  void loadTask?.destroy().catch(console.error);
  pdf=null; loadTask=null; pageData=null; selected=null; manual=false; showBoxes=true;
  cards.length=0; pages.clear(); lastAuto=[]; nextNumber=1;
  $('pdfInput').value=''; $('workerName').value=''; $('viewer').hidden=true; $('page').replaceChildren();
  $('fin').value=''; pdfOrder=[]; $('filter').value='All'; invalidateReview(); status('Load a PDF to begin.'); render();
};
$('download').onclick=async()=>{
  const ready=cards.filter(canExport),worker=workerName();
  if (!ready.length || !worker || !$('qa').checked || exporting) return;
  exporting=true; render();
  $('exportStatus').textContent='Creating ZIP…';
  try {
    const zip=new window.JSZip(),folder=zip.folder(worker),used=new Set(),list=[];
    for (const card of ready) {
      const base=clean(displayTitle(card)) || `Card ${card.number}`;
      let name=`${base} - ${card.side}.jpg`, sequence=2;
      while (used.has(name.toLowerCase())) name=`${base} - ${card.side} ${String(sequence++).padStart(2,'0')}.jpg`;
      used.add(name.toLowerCase()); list.push(name);
      folder.file(name,card.jpeg.slice(card.jpeg.indexOf(',')+1),{base64:true});
    }
    folder.file('File_List.txt',list.join('\n')+'\n');
    const blob=await zip.generateAsync({type:'blob'}), url=URL.createObjectURL(blob);
    const link=document.createElement('a'); link.href=url; link.download=`${worker}.zip`;
    document.body.append(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),30000);
    $('exportStatus').textContent=`Created ${worker}.zip with ${ready.length} JPEGs. ${cards.length-ready} crops excluded.`;
  } catch (error) { $('exportStatus').textContent=`Could not create ZIP: ${error.message}`; }
  finally { exporting=false; render(); }
};

function arrangedSets() {
  const sets=selectedSets(cards.filter(canExport));
  const byId=new Map(sets.map(set=>[set.id,set]));
  const ids=pdfOrder.filter(id=>byId.has(id));
  for (const set of sets) if (!ids.includes(set.id)) ids.push(set.id);
  pdfOrder=ids;
  return ids.map(id=>byId.get(id));
}
function renderPdfOrder(focusId,focusStep) {
  const sets=arrangedSets();
  const list=$('pdfOrder');
  list.replaceChildren();
  list.hidden=!sets.length;
  for (const [index,set] of sets.entries()) {
    const row=document.createElement('li');
    const content=document.createElement('div');
    content.className='pdf-order-row';
    const label=document.createElement('span');
    label.className='pdf-order-label';
    label.textContent=`${displayTitle(set.front || set.back)} · ${set.front && set.back?'Front and back':set.front?'Front only':'Back only'}`;
    const controls=document.createElement('div');
    controls.className='pdf-order-controls';
    let focusButton;
    for (const [text,step] of [['↑',-1],['↓',1]]) {
      const target=index+step;
      const move=button(text,()=>{
        [pdfOrder[index],pdfOrder[target]]=[pdfOrder[target],pdfOrder[index]];
        invalidateReview(); renderPdfOrder(set.id,step); updateControls();
      },'secondary',!!busy || loading || exporting || target<0 || target>=sets.length);
      move.setAttribute('aria-label',`Move set ${index+1} ${step<0?'up':'down'}`);
      if (set.id===focusId && !move.disabled && (step===focusStep || !focusButton)) focusButton=move;
      controls.append(move);
    }
    content.append(label,controls);
    row.append(content);
    list.append(row);
    focusButton?.focus();
  }
}
function pdfBlob() {
  const header=makeCanvas(1356,54);
  const ctx=header.getContext('2d');
  ctx.fillStyle='#fff'; ctx.fillRect(0,0,header.width,header.height);
  ctx.fillStyle='#18283e'; ctx.font='bold 32px Arial, sans-serif'; ctx.textBaseline='middle';
  ctx.fillText(`${$('workerName').value.trim()}  ·  FIN ${$('fin').value.trim().toUpperCase()}`,0,25,header.width);
  return makeCardPdf(arrangedSets(),{jpeg:header.toDataURL('image/jpeg',.96),width:header.width,height:header.height});
}
function exportPdf(preview) {
  if ($('downloadPdf').disabled) return;
  try {
    const blob=pdfBlob();
    const url=URL.createObjectURL(blob);
    if (preview) {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl=url; $('pdfPreview').src=url; $('pdfPreview').hidden=false;
      return;
    }
    const link=document.createElement('a'); link.href=url; link.download=workerPdfName(bridge?.identity.name||$('workerName').value);
    document.body.append(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),30000);
    $('exportStatus').textContent='A4 PDF ready.';
  } catch (error) { $('exportStatus').textContent=`Could not create PDF: ${error.message}`; }
}
$('previewPdf').onclick=()=>exportPdf(true);
$('downloadPdf').onclick=()=>exportPdf(false);

let installPrompt;
window.addEventListener('beforeinstallprompt',event=>{
  event.preventDefault(); installPrompt=event; $('install').hidden=false;
});
$('install').onclick=async()=>{
  if (!installPrompt) return;
  await installPrompt.prompt(); installPrompt=null; $('install').hidden=true;
};
window.addEventListener('appinstalled',()=>{ $('install').hidden=true; });
// The VCMS service worker owns this application.
render();
$('readBatch').onclick=()=>reviewBatch(arrangedSets());

$('saveWorker').onclick=async()=>{if(!bridge||exporting||busy)return;const reviewed=$('qa').checked;exporting=true;bridge.setSaving(true);render();try{await uploadSets(arrangedSets(),bridge,message=>$('exportStatus').textContent=message,{reviewed});}catch(e){$('exportStatus').textContent=e.message;}finally{exporting=false;bridge.setSaving(false);render();}};
if(bridge){$('workerName').value=bridge.identity.name;$('workerName').readOnly=true;$('fin').value=bridge.identity.fin_last4||'';updateControls();}
