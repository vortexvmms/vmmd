const {test,expect}=require('@playwright/test');
// Explicit network smoke check: downloads the actual pinned OCR/PDF libraries.
// Ordinary CI keeps deterministic extraction contracts in sic-register.spec.js.
test('real browser OCR and PDF text extraction on synthetic SIC cards',async({page})=>{
  test.skip(!process.env.SIC_OCR_SMOKE,'Run explicitly with SIC_OCR_SMOKE=1 and internet access');
  test.setTimeout(120000);
  await page.route('**/sic-reader-smoke',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><script src="/js/sic-card-data.js"></script><script src="/js/sic-card-reader.js"></script>'}));
  await page.goto('/sic-reader-smoke');
  const result=await page.evaluate(async()=>{
    const canvas=document.createElement('canvas');canvas.width=1600;canvas.height=850;const c=canvas.getContext('2d');c.fillStyle='white';c.fillRect(0,0,1600,850);c.fillStyle='black';c.font='48px Arial';
    const lines=['SITE INDUCTION COURSE','Name: TEST WORKER','FIN: G1234567X','Designation: Rigger & Signalman','Site: CCP3','SIC Date: 01/10/2026','Expiry Date: 30/09/2027','Card No: SIC-123'];
    lines.forEach((line,i)=>c.fillText(line,60,90+i*95));
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    const image=await SICCardReader.read([{file:new File([blob],'synthetic-card.png',{type:'image/png'}),type:'image/png'}]);
    // Minimal valid text PDF, generated entirely from public synthetic data.
    const stream='BT /F1 18 Tf 40 760 Td '+lines.map((line,i)=>(i?'0 -34 Td ':'')+'('+line+') Tj').join('\n')+' ET';
    const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 850] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>','<< /Length '+stream.length+' >>\nstream\n'+stream+'\nendstream'];
    let pdf='%PDF-1.4\n',offsets=[0];objects.forEach((obj,i)=>{offsets.push(pdf.length);pdf+=(i+1)+' 0 obj\n'+obj+'\nendobj\n'});const xref=pdf.length;pdf+='xref\n0 6\n0000000000 65535 f \n'+offsets.slice(1).map(n=>String(n).padStart(10,'0')+' 00000 n \n').join('')+'trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n'+xref+'\n%%EOF';
    const text=await SICCardReader.read([{file:new File([pdf],'synthetic-card.pdf',{type:'application/pdf'}),type:'application/pdf'}]);
    return {image:SICCardData.merge(image),text:SICCardData.merge(text),imageOCR:image[0].ocr,pdfOCR:text[0].ocr};
  });
  expect(result.imageOCR).toBe(true);expect(result.pdfOCR).toBe(false);
  for(const fields of [result.image,result.text]){expect(fields.fin).toEqual(['G1234567X']);expect(fields.name).toEqual(['TEST WORKER']);expect(fields.designation).toEqual(['Rigger & Signalman']);expect(fields.site).toEqual(['CCP3']);expect(fields.sic_date).toEqual(['2026-10-01']);expect(fields.expiry_date).toEqual(['2027-09-30']);expect(fields.reference).toEqual(['SIC-123'])}
});
test('cancellation releases a late OCR worker and settles the reader',async({page})=>{
  await page.route('**/sic-reader-cancel',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><script src="/js/sic-card-reader.js"></script>'}));
  await page.goto('/sic-reader-cancel');
  await page.evaluate(async()=>{
    const c=document.createElement('canvas');c.width=100;c.height=50;const blob=await new Promise(resolve=>c.toBlob(resolve));
    window.workerStops=0;window.Tesseract={createWorker:()=>new Promise(resolve=>{window.lateWorker=()=>resolve({terminate:async()=>{window.workerStops++},recognize:async()=>{throw Error('Cancelled worker must not read')}})})};
    window.cardAbort=new AbortController();window.cardRead=SICCardReader.read([{file:new File([blob],'card.png'),type:'image/png'}],{signal:cardAbort.signal}).then(()=> 'unexpected success',e=>e.name);
  });
  await expect.poll(()=>page.evaluate(()=>typeof window.lateWorker)).toBe('function');
  expect(await page.evaluate(async()=>{cardAbort.abort();return await cardRead})).toBe('AbortError');
  await page.evaluate(()=>window.lateWorker());await expect.poll(()=>page.evaluate(()=>window.workerStops)).toBe(1);
});
