/* Local, sequential extraction. Card bytes are never sent to an OCR service. */
(function(root){'use strict';
let loading;
function ocrLibrary(){
  if(root.Tesseract)return Promise.resolve(root.Tesseract);
  if(!loading)loading=new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';s.onload=()=>resolve(root.Tesseract);s.onerror=()=>{loading=null;s.remove();reject(Error('Could not download the card reader. Check your connection or enter details manually.'))};document.head.appendChild(s)});
  return loading;
}
async function read(files,{signal,onProgress=()=>{}}={}){
  let worker,creating,terminating,pdfTask,renderTask,pagesRead=0;const parts=[];
  const check=()=>{if(signal?.aborted)throw new DOMException('Card reading cancelled','AbortError')};
  const terminate=()=>worker?(terminating??=worker.terminate().catch(()=>{})):Promise.resolve();
  function abortable(promise){if(!signal)return promise;check();return new Promise((resolve,reject)=>{const abort=()=>reject(new DOMException('Card reading cancelled','AbortError'));signal.addEventListener('abort',abort,{once:true});Promise.resolve(promise).then(resolve,reject).finally(()=>signal.removeEventListener('abort',abort))})}
  const cancel=()=>{renderTask?.cancel();pdfTask?.destroy().catch(()=>{});void terminate()};
  signal?.addEventListener('abort',cancel,{once:true});
  async function recognise(image){
    check();
    if(!worker){const lib=await abortable(ocrLibrary());check();creating=lib.createWorker('eng',1,{workerPath:'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/worker.min.js',corePath:'https://cdn.jsdelivr.net/npm/tesseract.js-core@5.1.1',logger:m=>{if(!signal?.aborted&&m.status==='recognizing text')onProgress('Reading card text · '+Math.round((m.progress||0)*100)+'%')}}).then(async w=>{worker=w;if(signal?.aborted){await terminate();check()}return w});await abortable(creating);check()}
    const result=await abortable(worker.recognize(image));check();return {text:result.data.text||'',confidence:result.data.confidence,ocr:true};
  }
  const add=(fileIndex,page,result)=>{if(result.text.length>100000)throw Error('Too much card text. Upload a smaller document.');parts.push({fileIndex,page,...result})};
  try{
    for(let i=0;i<files.length;i++){
      check();const {file,type}=files[i];onProgress('Reading '+file.name+' · '+(i+1)+' of '+files.length);
      if(type==='application/pdf'){
        const lib=await abortable(import('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs'));check();
        lib.GlobalWorkerOptions.workerSrc='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs';
        pdfTask=lib.getDocument({data:await file.arrayBuffer(),isEvalSupported:false});const pdf=await abortable(pdfTask.promise);
        try{
          if(pdf.numPages+pagesRead>30)throw Error('Read up to 30 pages per batch. Split this upload into smaller batches.');
          for(let n=1;n<=pdf.numPages;n++){
            check();onProgress(file.name+' · page '+n+' of '+pdf.numPages);
            const page=await pdf.getPage(n),content=await page.getTextContent();
            let text='',lastY;
            for(const item of content.items){if(!('str' in item))continue;const y=item.transform?.[5];if(lastY!==undefined&&Math.abs(y-lastY)>3)text+='\n';text+=item.str+(item.hasEOL?'\n':' ');lastY=y}
            let result={text,confidence:null,ocr:false};
            if(text.replace(/\s/g,'').length<30){
              const base=page.getViewport({scale:1}),scale=Math.min(3,2200/Math.max(base.width,base.height),Math.sqrt(6000000/(base.width*base.height)));
              const viewport=page.getViewport({scale}),canvas=document.createElement('canvas');canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
              try{renderTask=page.render({canvasContext:canvas.getContext('2d'),viewport});await abortable(renderTask.promise);renderTask=null;result=await recognise(canvas)}finally{canvas.width=canvas.height=1}
            }
            add(i,n,result);pagesRead++;page.cleanup();
          }
        }finally{await pdf.destroy();pdfTask=null}
      }else{
        if(++pagesRead>30)throw Error('Read up to 30 pages per batch.');
        const bitmap=await createImageBitmap(file,{resizeWidth:2200});
        try{check();if(bitmap.width*bitmap.height>6000000)throw Error('Card image is too tall. Crop it to the card and try again.');const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;try{canvas.getContext('2d').drawImage(bitmap,0,0);add(i,1,await recognise(canvas))}finally{canvas.width=canvas.height=1}}finally{bitmap.close()}
      }
    }
    check();return parts;
  }finally{
    signal?.removeEventListener('abort',cancel);
    await terminate();
  }
}
root.SICCardReader={read};
})(window);
