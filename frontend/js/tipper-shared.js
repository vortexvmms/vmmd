/* Document uploads preserve the complete page; DPR's 1600px / JPEG .72 policy. */
window.Tipper = (() => {
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = v => 'S$'+Number(v||0).toLocaleString('en-SG',{minimumFractionDigits:2,maximumFractionDigits:2});
  function totals(x) {
    if(x.billing_mode==='trip') return {normal:null,ot:null,total:null,amount:Number(x.quantity||0)*Number(x.transport_rate||0)};
    if(x.billing_mode==='legacy') return {normal:null,ot:null,total:null,amount:Number(x.quantity||0)*Number(x.transport_rate||0)};
    if(!x.start_time||!x.end_time) return {normal:0,ot:0,total:0,amount:0};
    const mins=s=>{const a=s.split(':').map(Number);return a[0]*60+a[1]}, elapsed=(mins(x.end_time)-mins(x.start_time)+1440)%1440;
    const total=Math.max(0,(elapsed-Number(x.break_minutes||0))/60),normal=Math.min(total,10),ot=Math.max(total-10,0);
    return {normal,ot,total,amount:normal*Number(x.transport_rate||0)+ot*Number(x.ot_rate||0)};
  }
  async function prepare(file) {
    if(file.type==='application/pdf'||/\.pdf$/i.test(file.name)) {
      if(file.size>10*1024*1024) throw Error('PDF must be below 10 MB. Upload one trip sheet per file.');
      return {blob:file,warnings:[]};
    }
    let source=file;
    if(/heic|heif/i.test(file.type)||/\.hei[cf]$/i.test(file.name)) {
      if(typeof heic2any!=='function') throw Error('HEIC converter unavailable. Choose a JPG or take a photo.');
      source=await heic2any({blob:file,toType:'image/jpeg',quality:.9}); if(Array.isArray(source))source=source[0];
    }
    const url=URL.createObjectURL(source),img=new Image();
    try { await new Promise((ok,no)=>{img.onload=ok;img.onerror=()=>no(Error('Photo cannot be opened'));img.src=url});
      const c=document.createElement('canvas'),scale=Math.min(1,1600/Math.max(img.naturalWidth,img.naturalHeight));
      c.width=Math.round(img.naturalWidth*scale);c.height=Math.round(img.naturalHeight*scale);
      c.getContext('2d').drawImage(img,0,0,c.width,c.height);
      const warnings=[];
      if(Math.min(c.width,c.height)<700)warnings.push('Photo resolution is low. Move closer and retake with the whole sheet visible.');
      const sample=document.createElement('canvas');sample.width=160;sample.height=160;sample.getContext('2d').drawImage(c,0,0,160,160);
      const pixels=sample.getContext('2d').getImageData(0,0,160,160).data;let sum=0,sq=0;
      for(let i=0;i<pixels.length;i+=4){const light=.2126*pixels[i]+.7152*pixels[i+1]+.0722*pixels[i+2];sum+=light;sq+=light*light;}
      const mean=sum/25600,contrast=Math.sqrt(sq/25600-mean*mean);
      if(mean<45)warnings.push('Photo is too dark. Retake in brighter light.');
      if(contrast<12)warnings.push('Text contrast is too low. Check blur or glare and retake.');
      const blob=await new Promise((ok,no)=>c.toBlob(b=>b?ok(b):no(Error('Could not prepare photo')),'image/jpeg',.72));
      if(blob.size>10*1024*1024)throw Error('Prepared photo exceeds 10 MB');
      return {blob,warnings};
    } finally { URL.revokeObjectURL(url); }
  }
  function rule(rules,client,site,mode,date) {
    return rules.filter(r=>r.active!==false&&r.client_id===client&&r.site_name===site&&r.billing_mode===mode&&r.effective_from<=date).sort((a,b)=>b.effective_from.localeCompare(a.effective_from))[0];
  }
  return {esc,money,totals,prepare,rule};
})();
