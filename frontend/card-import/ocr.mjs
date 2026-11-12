// OCR runs locally in the browser. Images are never submitted to an OCR service.
let library, worker;
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
export async function readCardLines(jpeg,signal) {
  const current=await engine();
  if(signal?.aborted) throw new DOMException('Cancelled','AbortError');
  const stop=()=>{worker=null;current.terminate();};
  signal?.addEventListener('abort',stop,{once:true});
  try {
    const image=new Image();image.src=jpeg;await image.decode();
    const {data}=await current.recognize(jpeg);
    if(signal?.aborted) throw new DOMException('Cancelled','AbortError');
    return (data.lines||[]).map(line=>({text:line.text,confidence:line.confidence,
      x:line.bbox.x0/image.width,y:line.bbox.y0/image.height,
      width:(line.bbox.x1-line.bbox.x0)/image.width,
      height:(line.bbox.y1-line.bbox.y0)/image.height}));
  } finally {signal?.removeEventListener('abort',stop);}
}
