/* Upload, paste, drop and camera inputs use the same reviewed photo pipeline. */
window.WorkerCardInput=class {
 constructor(){
  this.el=id=>document.getElementById(id);this.sequence=0;this.facing='environment';this.stream=null;this.nativeCapture=/Android|iPhone|iPad/i.test(navigator.userAgent)||(/Macintosh/i.test(navigator.userAgent)&&navigator.maxTouchPoints>1);
  for(const side of ['front','back']){
   const input=this.el(side+'-file'),label=this.el(side+'-label'),zone=document.createElement('div');
   zone.className='wc-upload-zone';zone.id=side+'-drop';zone.tabIndex=0;zone.setAttribute('role','group');zone.setAttribute('aria-label',side+' photo upload');
   const help=document.createElement('p');help.textContent='Drop a file here, upload, or take a photo.';zone.append(help);
   const paste=document.createElement('button');paste.type='button';paste.id=side+'-paste';paste.textContent='Paste '+side+' screenshot';
   const pasteHelp=document.createElement('p');pasteHelp.className='wc-muted';pasteHelp.hidden=true;
   const target=document.createElement('textarea');target.id=side+'-paste-target';target.rows=1;target.hidden=true;target.placeholder='Press ⌘V or Ctrl+V here';target.setAttribute('aria-label','Paste '+side+' screenshot here');
   paste.setAttribute('aria-controls',target.id);
   paste.onclick=()=>{target.hidden=false;pasteHelp.hidden=false;pasteHelp.textContent='Press ⌘V on Mac or Ctrl+V on Windows to paste your screenshot.';target.focus();};
   paste.setAttribute('aria-describedby',side+'-paste-help');pasteHelp.id=side+'-paste-help';pasteHelp.setAttribute('role','status');
   const toolbar=document.createElement('div');toolbar.className='wc-toolbar';toolbar.append(paste);
   for(const [title,action] of [['Upload file',()=>input.click()],['Take photo',()=>this.camera(side)]]){const b=document.createElement('button');b.type='button';b.textContent=title;b.onclick=action;toolbar.append(b)}
   const selected=document.createElement('p');selected.id=side+'-selected';selected.className='wc-muted';selected.textContent='No file selected';zone.append(toolbar,target,pasteHelp,selected);label.insertAdjacentElement('afterend',zone);
   input.accept='image/jpeg,image/png,image/heic,image/heif,.jpg,.jpeg,.png,.heic,.heif';input.addEventListener('change',()=>selected.textContent=input.files[0]?.name||'No file selected');
   for(const event of ['dragenter','dragover'])zone.addEventListener(event,e=>{e.preventDefault();zone.classList.add('dragging')});
   zone.addEventListener('dragleave',()=>zone.classList.remove('dragging'));zone.addEventListener('drop',e=>{e.preventDefault();zone.classList.remove('dragging');if(e.dataTransfer.files.length!==1){this.error('Drop one file on each side.');return}this.assign(side,e.dataTransfer.files[0])});
   zone.addEventListener('paste',e=>{
    const clipboard=e.clipboardData;if(!clipboard)return;
    if(e.target===target)e.preventDefault();
    const file=[...clipboard.files].find(f=>f.type.startsWith('image/'))||
     [...clipboard.items].find(item=>item.kind==='file'&&item.type.startsWith('image/'))?.getAsFile();
    if(!file){this.error('Copy a screenshot first, then paste it into the '+side+' photo area.');return;}
    e.preventDefault();
    const extension=file.type==='image/jpeg'?'jpg':'png';
    const screenshot=/^image\/(png|jpeg)$/.test(file.type)?
     new File([file],side+'-screenshot.'+extension,{type:file.type}):file;
    if(this.assign(side,screenshot)){target.hidden=true;pasteHelp.hidden=true;}
   });
   // Native mobile capture is also available if webcam access is unsupported.
   const capture=document.createElement('input');capture.type='file';capture.accept='image/*';capture.setAttribute('capture','environment');capture.hidden=true;capture.id=side+'-camera-file';zone.append(capture);capture.onchange=()=>{if(capture.files[0])this.assign(side,capture.files[0]);capture.value=''};
  }
  this.el('capture-close').onclick=()=>this.stop();this.el('capture-dialog').addEventListener('cancel',e=>{e.preventDefault();this.stop()});
  this.el('capture-shoot').onclick=()=>this.shoot();this.el('capture-switch').onclick=()=>{this.facing=this.facing==='environment'?'user':'environment';this.camera(this.side)};
  window.addEventListener('pagehide',()=>this.stop());document.addEventListener('visibilitychange',()=>{if(document.hidden)this.stop()});
 }
 refresh(kind){for(const s of ['front','back']){this.el(s+'-drop').hidden=s==='back'&&kind!=='cards';this.el(s+'-paste').hidden=kind!=='cards';this.el(s+'-paste-help').hidden=true;this.el(s+'-paste-target').hidden=true;this.el(s+'-paste-target').value='';this.el(s+'-selected').textContent=this.el(s+'-file').files[0]?.name||'No file selected';this.el(s+'-file').accept=kind==='certificates'?'application/pdf,image/jpeg,image/png,image/heic,image/heif,.pdf,.jpg,.jpeg,.png,.heic,.heif':'image/jpeg,image/png,image/heic,image/heif,.jpg,.jpeg,.png,.heic,.heif'}}
 error(text){this.el('edit-error').textContent=text}
 assign(side,file){if(file.size>20971520){this.error('Files must be 20 MB or smaller.');return}if(!/\.(jpe?g|png|heic|heif|pdf)$/i.test(file.name)&&!/^image\/(jpeg|png|heic|heif)$|^application\/pdf$/.test(file.type)){this.error('Choose a JPG, PNG, HEIC photo or a certificate PDF.');return}if((file.type==='application/pdf'||/\.pdf$/i.test(file.name))&&this.el('certificate-fields').hidden){this.error('Upload PDFs under Certificates. Card sides need a photo.');return}const transfer=new DataTransfer();transfer.items.add(file);const input=this.el(side+'-file');input.files=transfer.files;this.error('');input.dispatchEvent(new Event('change',{bubbles:true}));return true}
 async camera(side){if(this.nativeCapture){this.el(side+'-camera-file').click();return}this.stop(false);this.side=side;const sequence=++this.sequence;const dialog=this.el('capture-dialog');if(!dialog.open)dialog.showModal();this.el('capture-shoot').disabled=true;this.el('capture-message').textContent='Allow camera access to take a photo.';
  try{if(!navigator.mediaDevices?.getUserMedia)throw Error('Camera is unavailable in this browser.');const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:this.facing},width:{ideal:2560},height:{ideal:1920}},audio:false});if(sequence!==this.sequence){stream.getTracks().forEach(t=>t.stop());return}this.stream=stream;const video=this.el('capture-video');video.srcObject=stream;await video.play();if(sequence!==this.sequence)return;this.el('capture-shoot').disabled=false;this.el('capture-message').textContent='Keep the whole card inside the picture. Capture, then crop and mask.';
  }catch(e){if(sequence!==this.sequence)return;this.el('capture-message').textContent='Camera could not open. Allow camera access in your browser, or use Upload file.';const fallback=this.el(side+'-camera-file');if(/Android|iPhone|iPad/i.test(navigator.userAgent)){this.el('capture-message').textContent+=' You can use your phone camera instead.';const b=document.createElement('button');b.type='button';b.textContent='Open phone camera';b.onclick=()=>{this.stop();fallback.click()};this.el('capture-message').append(b)}}
 }
 async shoot(){const sequence=this.sequence,side=this.side,video=this.el('capture-video');if(!video.videoWidth||!video.videoHeight)return;this.el('capture-shoot').disabled=true;try{const c=document.createElement('canvas'),scale=Math.min(1,Math.sqrt(12000000/(video.videoWidth*video.videoHeight)));c.width=Math.round(video.videoWidth*scale);c.height=Math.round(video.videoHeight*scale);c.getContext('2d').drawImage(video,0,0,c.width,c.height);const blob=await new Promise(resolve=>c.toBlob(resolve,'image/jpeg',.95));if(sequence!==this.sequence)return;if(!blob)throw Error('Capture failed');this.stop();this.assign(side,new File([blob],'camera-'+side+'.jpg',{type:'image/jpeg'}));}catch(e){this.el('capture-message').textContent='Photo could not be captured. Please try again.';this.el('capture-shoot').disabled=false}}
 stop(close=true){this.sequence++;this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;this.el('capture-video').srcObject=null;if(close)this.el('capture-dialog').close()}
};
