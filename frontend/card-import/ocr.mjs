// OCR runs locally in the browser. Images are never submitted to an OCR service.
let library, worker;
const cache=new WeakMap();
let queue=Promise.resolve();
async function engine() {
  if (!library) library = new Promise((resolve,reject)=>{
    const script=document.createElement('script');
    script.src='https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
    script.onload=resolve;
    script.onerror=()=>{library=null;script.remove();reject(Error('Could not load text recognition'));};
    document.head.append(script);
  });
  await library;
  if (!worker) worker=window.Tesseract.createWorker('eng').catch(error=>{worker=null;throw error;});
  return worker;
}
async function recognize(jpeg,signal) {
  if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
  const current=await engine();
  if(signal?.aborted) throw new DOMException('Cancelled','AbortError');
  let rejectAbort;
  const aborted=new Promise((_,reject)=>{rejectAbort=reject;});
  const stop=()=>{worker=null;rejectAbort(new DOMException('Cancelled','AbortError'));void current.terminate().catch(()=>{});};
  signal?.addEventListener('abort',stop,{once:true});
  try {
    const image=new Image();image.src=jpeg;await image.decode();
    if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
    const {data}=await Promise.race([current.recognize(jpeg,{}, {blocks:true}),aborted]);
    const geometry=b=>({x:b.x0/image.width,y:b.y0/image.height,
      width:(b.x1-b.x0)/image.width,height:(b.y1-b.y0)/image.height});
    const lines=data.blocks?.flatMap(block=>block.paragraphs.flatMap(paragraph=>paragraph.lines))??data.lines??[];
    return lines.map(line=>({text:line.text,confidence:line.confidence,...geometry(line.bbox),
      symbols:(line.words||[]).flatMap(word=>(word.symbols||[]).map(symbol=>({text:symbol.text,...geometry(symbol.bbox)})))}));
  } finally {signal?.removeEventListener('abort',stop);}
}

export function readCardLines(jpeg,signal) {
  const result=queue.then(()=>recognize(jpeg,signal));
  queue=result.catch(()=>{});
  return result;
}
export async function readCrop(card,signal) {
  const source=card.sourceJpeg||card.jpeg;
  const previous=cache.get(card);
  if(previous?.source===source)return previous.result;
  const started=performance.now();
  const result=readCardLines(source,signal);
  cache.set(card,{source,result});
  try{return await result;}
  catch(error){if(cache.get(card)?.result===result)cache.delete(card);throw error;}
  finally{console.debug('Worker card OCR duration (ms)',Math.round(performance.now()-started));}
}
