async function preparePhoto(file){
  if(!file || file.size>30*1024*1024) throw new Error('Choose a photo up to 30 MB.');
  let bitmap;
  try { bitmap=await createImageBitmap(file); }
  catch (_) { throw new Error('This photo could not be opened. Choose a JPEG, PNG or WebP image.'); }
  try{
    const ratio=Math.min(1,1600/Math.max(bitmap.width,bitmap.height));
    const canvas=document.createElement('canvas');
    canvas.width=Math.max(1,Math.round(bitmap.width*ratio));
    canvas.height=Math.max(1,Math.round(bitmap.height*ratio));
    const context=canvas.getContext('2d',{alpha:false});
    context.fillStyle='#fff';context.fillRect(0,0,canvas.width,canvas.height);
    context.drawImage(bitmap,0,0,canvas.width,canvas.height);
    return await new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('Photo could not be converted.')),'image/jpeg',0.8));
  }finally{bitmap.close();}
}
