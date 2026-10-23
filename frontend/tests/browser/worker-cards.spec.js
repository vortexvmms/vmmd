const {test,expect}=require('@playwright/test');
const W='10000000-0000-0000-0000-000000000001',C='30000000-0000-0000-0000-000000000001';
// A valid PNG is required: Linux WebKit rejects corrupt chunk checksums.
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAGQAAAA8CAIAAAAfXYiZAAAAlUlEQVR4nO3QsQEAIAyAMPX/n+sLZU9mJu7MHHbessOsxqzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCswKzArMCss/cBpwsDdcmiT80AAAAASUVORK5CYII=','base64');
async function draw(page,x,y,w,h){const b=await page.locator('#mask-canvas').boundingBox();await page.mouse.move(b.x+b.width*x,b.y+b.height*y);await page.mouse.down();await page.mouse.move(b.x+b.width*(x+w),b.y+b.height*(y+h));await page.mouse.up()}
async function fixture(page,{conflict=false}={}){
 const writes=[],cards=[{id:C,worker_id:W,category:'course',label:'Construction Safety Orientation',institute:'Sample Training Centre',cert_no:'COURSE-001',issued_date:'2025-01-10',expiry_date:'2025-12-31',image_path:W+'/front.jpg',back_image_path:W+'/back.jpg',updated_at:'v1'},{id:'30000000-0000-0000-0000-000000000002',worker_id:W,category:'work_permit',label:'Work permit',expiry_date:'2028-06-30',image_path:W+'/permit.jpg',updated_at:'v1'}],certificates=[];
 await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',expires_at:Date.now()+3600000})));
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(),u=new URL(req.url()),p=u.pathname;
  if(p.endsWith('/me'))return route.fulfill({json:{role:'site_sup',name:'Test Supervisor',user_id:'u1'}});
  if(!p.includes('/worker-documents/'))return route.fulfill({json:[]});
  if(p.endsWith('/workers'))return route.fulfill({json:u.searchParams.get('search')==='nobody'?[]:[{id:W,name:'Sample Worker',worker_code:'EMP-050',status:'active'}]});
  if(p.endsWith('/mask-preview'))return route.fulfill({json:{policy:'fin-dob-wp-v1',sha256:'test-digest',page:Number(u.searchParams.get('page')),pages:req.headers()['content-type']==='application/pdf'?2:1,width:1000,height:600,image:png.toString('base64'),recognition:'suggested',boxes:[{x:.1,y:.1,w:.4,h:.1,field:'FIN',suffix:'567X'}]}});
  if(p.endsWith('/file'))return route.fulfill({status:502,json:{detail:'Original file is unavailable. The saved record is retained; upload a replacement if available.'}});
  const kind=p.includes('/certificates')?'certificates':'cards',rows=kind==='cards'?cards:certificates;
  if(req.method()==='POST'){
   const manifest=JSON.parse(req.headers()['x-document-masking']);const body=req.postDataBuffer();if(body&&req.headers()['content-type']==='image/png')expect(manifest.sha256).toBe(require('node:crypto').createHash('sha256').update(body).digest('hex'));writes.push({method:'POST',path:p,query:Object.fromEntries(u.searchParams),masking:manifest,body});
   const id=u.searchParams.get('record_id')||'new-'+kind;
   let row=rows.find(r=>r.id===id);if(!row){row={id,worker_id:W,category:'course',updated_at:'v0'};rows.push(row)}
   row.updated_at='v'+writes.length;row[kind==='certificates'?'file_path':u.searchParams.get('side')==='back'?'back_image_path':'image_path']=W+'/new.png';
   return route.fulfill({status:201,json:row});
  }
  if(req.method()==='PATCH'){
   const body=req.postDataJSON();writes.push({method:'PATCH',body});
   if(conflict)return route.fulfill({status:409,json:{detail:'This document changed. Refresh before editing again.'}});
   const row=rows.find(r=>r.id===p.split('/').pop());Object.assign(row,body);return route.fulfill({json:row});
  }
  return route.fulfill({json:rows});
 });
 await page.goto('/worker-cards.html');await page.getByRole('button',{name:'Sample Worker'}).click();await expect(page.locator('#card-count')).toHaveText('(2)');return{writes,cards,certificates};
}
async function checkPages(page,count=1){for(let i=0;i<count;i++){await expect(page.locator('#mask-confirm')).toBeEnabled();await page.locator('#mask-confirm').click()}}
test('supervisor has a responsive worker register and clear expiry states',async({page,isMobile})=>{
 await fixture(page);await expect(page.locator('#scope')).toContainText('allocated to your sites today');await expect(page.getByText('Expired',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.getByRole('button',{name:'View front',exact:true}).first().click();await expect(page.locator('#preview-body')).toContainText('saved record is retained');await page.locator('#close-preview').click();
 await page.locator('#worker-search').fill('nobody');await expect(page.locator('#worker-list')).toHaveText('No workers available.');
 if(!isMobile&&process.env.WORKER_CARDS_PREVIEW){await page.locator('#worker-search').fill('');await expect(page.locator('.wc-worker')).toBeVisible();await page.screenshot({path:process.env.WORKER_CARDS_PREVIEW,fullPage:true})}
});
test('supervisor can correct card metadata and clear expiry without replacing files',async({page})=>{
 const {writes}=await fixture(page);await page.getByRole('button',{name:'Edit',exact:true}).first().click();await page.locator('[name=label]').fill('Corrected safety course');await page.locator('#clear-expiry').click();await page.locator('#save').click();await expect(page.locator('#edit-dialog')).not.toBeVisible();await expect(page.getByRole('heading',{name:'Corrected safety course'})).toBeVisible();expect(writes).toHaveLength(1);expect(writes[0].body).toMatchObject({updated_at:'v1',label:'Corrected safety course',expiry_date:null});
});
test('new front and back upload once then metadata is saved against the returned version',async({page})=>{
 const {writes}=await fixture(page);await page.locator('#add').click();await page.locator('[name=label]').fill('New course');await page.locator('#front-file').setInputFiles({name:'front.png',mimeType:'image/png',buffer:png});await checkPages(page);await page.locator('#back-file').setInputFiles({name:'back.png',mimeType:'image/png',buffer:png});await checkPages(page);await page.locator('#save').click();await expect(page.locator('#edit-dialog')).not.toBeVisible();expect(writes.map(w=>w.method)).toEqual(['POST','POST','PATCH']);expect(writes[0].query).toEqual({worker_id:W,side:'front'});expect(writes[1].query).toMatchObject({worker_id:W,side:'back',record_id:'new-cards',updated_at:'v1'});expect(writes[2].body.updated_at).toBe('v2');expect(writes[0].masking.pages[0]).toMatchObject({reviewed:true,boxes:[]});expect(writes[0].masking.sha256).toMatch(/^[a-f0-9]{64}$/);
});
test('certificate upload and title editing use the certificate section',async({page})=>{
 const {writes}=await fixture(page);await page.locator('#certificates-tab').click();await page.locator('#add').click();await expect(page.locator('#back-label')).toBeHidden();await page.locator('[name=title]').fill('Trade certificate');await page.locator('#front-file').setInputFiles({name:'trade.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4 test')});await checkPages(page,2);await page.locator('#save').click();await expect(page.getByRole('heading',{name:'Trade certificate'})).toBeVisible();expect(writes[0].path).toContain('/certificates/upload');expect(writes[0].masking.pages).toHaveLength(2);expect(writes[1].body).toEqual({updated_at:'v1',title:'Trade certificate'});
});
test('a stale edit stays open and asks the supervisor to refresh',async({page})=>{
 const {writes}=await fixture(page,{conflict:true});await page.getByRole('button',{name:'Edit',exact:true}).first().click();await page.locator('[name=label]').fill('Stale correction');await page.locator('#save').click();await expect(page.locator('#edit-error')).toContainText('Refresh before editing');await expect(page.locator('#edit-dialog')).toBeVisible();expect(writes).toHaveLength(1);
});

test('card sheet loads both sides and retains the selected worker identity for printing',async({page})=>{
 await fixture(page);
 await page.route('**/worker-documents/cards/*/file?*',route=>route.fulfill({status:200,contentType:'image/png',body:png}));
 await page.evaluate(()=>{window.print=()=>{window.cardPrintReady=true}});
 await page.locator('#print-cards').click();await page.locator('#card-print-prepare').click();await expect(page.locator('#card-print-go')).toBeEnabled();await page.locator('#card-print-go').click();await expect.poll(()=>page.evaluate(()=>window.cardPrintReady)).toBeTruthy();
 await expect(page.locator('#print-sheet img')).toHaveCount(3);
 await expect(page.locator('#print-sheet h1')).toHaveText('Sample Worker · EMP-050');
 await page.emulateMedia({media:'print'});await expect(page.locator('#print-sheet')).toBeVisible();await expect(page.locator('main')).toBeHidden();
});

test('new files cannot save before review and changed files require a new check',async({page})=>{
 const {writes}=await fixture(page);await page.locator('#add').click();
 await page.locator('#front-file').setInputFiles({name:'front.png',mimeType:'image/png',buffer:png});
 await expect(page.locator('#mask-confirm')).toBeEnabled();await page.locator('#mask-close').click();await page.locator('#save').click();
 await expect(page.locator('#edit-error')).toContainText('Review the masking');expect(writes).toHaveLength(0);
 await page.locator('#review-front').click();await checkPages(page);await page.locator('#front-file').setInputFiles({name:'replacement.png',mimeType:'image/png',buffer:png});
 await expect(page.locator('#mask-confirm')).toBeEnabled();await page.locator('#mask-close').click();await page.locator('#save').click();
 await expect(page.locator('#edit-error')).toContainText('Review the masking');expect(writes).toHaveLength(0);
 await page.locator('#close-edit').click();await page.locator('#add').click();
 await expect(page.locator('#mask-review')).toBeHidden();await expect(page.locator('#front-file')).toHaveValue('');
});

test('masks can be corrected and a manually drawn black area is included in the upload',async({page,isMobile})=>{
 const {writes}=await fixture(page);await page.locator('#add').click();
 await page.locator('#front-file').setInputFiles({name:'front.png',mimeType:'image/png',buffer:png});
 await expect(page.locator('#mask-confirm')).toBeEnabled();
 await page.locator('#mask-zoom-in').click();await expect(page.locator('#mask-move')).toHaveText('Draw masks');
 await page.locator('#mask-fit').click();await expect(page.locator('#mask-move')).toHaveText('Move view');
 await page.locator('#mask-suggest').click();await expect(page.locator('#mask-boxes input')).toHaveCount(1);await page.locator('#mask-adjustments summary').click();
 await page.getByRole('button',{name:'Remove mask 1',exact:true}).click();
 const canvas=page.locator('#mask-canvas');await canvas.scrollIntoViewIfNeeded();const box=await canvas.boundingBox();
 await page.mouse.move(box.x+box.width*.15,box.y+box.height*.2);await page.mouse.down();
 await page.mouse.move(box.x+box.width*.45,box.y+box.height*.35);await page.mouse.up();
 await expect(page.locator('#mask-boxes input')).toHaveCount(1);
 await page.locator('#mask-boxes input').fill('1234');await checkPages(page);
 if(!isMobile&&process.env.MASKING_PREVIEW){await page.locator('#review-front').click();await expect(page.locator('#mask-confirm')).toBeEnabled();await page.screenshot({path:process.env.MASKING_PREVIEW,fullPage:true});await checkPages(page)}
 await page.locator('#save').click();await expect(page.locator('#edit-dialog')).not.toBeVisible();
 const b=writes[0].masking.pages[0].boxes[0];expect(b.field).toBe('Manual mask');expect(b.suffix).toBe('1234');expect(b.x).toBeCloseTo(.15,2);expect(b.w).toBeCloseTo(.3,2);
});


test('photo editor opens without OCR, crops and rotates while preserving mask coverage',async({page})=>{
 const {writes}=await fixture(page);let previews=0;await page.route('**/mask-preview?*',route=>{previews++;return route.fulfill({status:503,json:{detail:'Detection unavailable'}})});
 await page.locator('#add').click();await page.locator('#front-file').setInputFiles({name:'photo.png',mimeType:'image/png',buffer:png});await expect(page.locator('#mask-canvas')).toBeVisible();expect(previews).toBe(0);
 const size=await page.locator('#mask-editor').boundingBox();const viewport=page.viewportSize();expect(size.width).toBeGreaterThanOrEqual(Math.min(1600,viewport.width*.9));expect(size.height).toBeGreaterThan(viewport.height*.9);
 await draw(page,.2,.2,.2,.2);await page.locator('#mask-crop').click();for(const [name,x,y] of [['Top left',.1,.1],['Bottom right',.8,.8]]){const h=await page.getByRole('button',{name:name+' crop handle',exact:true}).boundingBox(),b=await page.locator('#mask-canvas').boundingBox();await page.mouse.move(h.x+h.width/2,h.y+h.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width*x,b.y+b.height*y);await page.mouse.up();}await page.locator('#mask-crop-apply').click();await expect(page.locator('#mask-canvas')).toHaveAttribute('width','70');await expect(page.locator('#mask-canvas')).toHaveAttribute('height','42');
 await page.locator('#mask-rotate').click();await expect(page.locator('#mask-canvas')).toHaveAttribute('width','42');await expect(page.locator('#mask-canvas')).toHaveAttribute('height','70');
 await page.locator('#mask-suggest').click();await expect(page.locator('#mask-message')).toContainText('Manual masking is ready');await checkPages(page);await page.locator('#save').click();await expect(page.locator('#edit-dialog')).toBeHidden();
 const b=writes[0].masking.pages[0].boxes[0];expect(b.x).toBeCloseTo(4/7,2);expect(b.y).toBeCloseTo(1/7,2);expect(b.w).toBeCloseTo(2/7,2);expect(b.h).toBeCloseTo(2/7,2);
 if(!writes[0].body)return;
 const dimensions=await page.evaluate(async bytes=>{const image=await createImageBitmap(new Blob([new Uint8Array(bytes)],{type:'image/png'}));return[image.width,image.height]},[...writes[0].body]);expect(dimensions).toEqual([42,70]);
});
test('drop and phone camera inputs open the same review; camera denial offers upload',async({page,isMobile})=>{
 await fixture(page);await page.addInitScript(()=>{});await page.locator('#add').click();
 await page.locator('#front-drop').evaluate((zone,data)=>{const binary=atob(data),bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));const transfer=new DataTransfer();transfer.items.add(new File([bytes],'dropped.png',{type:'image/png'}));zone.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:transfer}))},png.toString('base64'));
 await expect(page.locator('#mask-canvas')).toBeVisible();await checkPages(page);await expect(page.locator('#front-selected')).toHaveText('dropped.png');
 await page.evaluate(()=>Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{throw new Error('Denied')}}}));
 if(isMobile){const chooser=page.waitForEvent('filechooser');await page.locator('#back-drop').getByRole('button',{name:'Take photo',exact:true}).click();await chooser;}else{await page.locator('#back-drop').getByRole('button',{name:'Take photo',exact:true}).click();await expect(page.locator('#capture-message')).toContainText('Camera could not open');await page.locator('#capture-close').click();}
 await page.locator('#back-camera-file').setInputFiles({name:'camera-back.png',mimeType:'image/png',buffer:png});await expect(page.locator('#mask-canvas')).toBeVisible();await checkPages(page);await expect(page.locator('#back-selected')).toHaveText('camera-back.png');
});
test('desktop camera captures a photo and releases the camera after capture',async({page,isMobile})=>{
 if(isMobile)return;
 await fixture(page);await page.locator('#add').click();
 await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=800;canvas.height=500;const c=canvas.getContext('2d');c.fillStyle='white';c.fillRect(0,0,800,500);c.fillStyle='black';c.font='30px Arial';c.fillText('Synthetic permit card',30,70);const stream=canvas.captureStream(10);window.testCameraStream=stream;Object.defineProperty(navigator.mediaDevices,'getUserMedia',{configurable:true,value:async()=>stream})});
 await page.locator('#front-drop').getByRole('button',{name:'Take photo',exact:true}).click();await expect(page.locator('#capture-shoot')).toBeEnabled();await page.locator('#capture-shoot').click();await expect(page.locator('#mask-canvas')).toBeVisible();expect(await page.evaluate(()=>window.testCameraStream.getTracks().every(t=>t.readyState==='ended'))).toBe(true);await checkPages(page);
});


test('print pack includes only selected sides in the arranged sequence',async({page})=>{
 await fixture(page);const requests=[];await page.route('**/worker-documents/cards/*/file?*',route=>{requests.push(new URL(route.request().url()));return route.fulfill({status:200,contentType:'image/png',body:png})});
 await page.locator('#print-cards').click();await expect(page.locator('#card-print-count')).toHaveText('2 of 2 cards selected · 3 sides');
 await page.locator('#card-print-list [data-side=back]').first().uncheck();await page.getByRole('button',{name:'Move down: Construction Safety Orientation',exact:true}).click();
 await page.locator('#card-print-prepare').click();await expect(page.locator('#card-print-go')).toBeEnabled();
 expect(requests.map(u=>u.searchParams.get('side'))).toEqual(['front','front']);expect(requests[0].pathname).toContain('30000000-0000-0000-0000-000000000002');
 await expect(page.locator('#print-sheet h2').first()).toContainText('1. Work permit');await expect(page.locator('#print-sheet img')).toHaveCount(2);
 await page.locator('#card-print-list [data-side=front]').first().uncheck();await expect(page.locator('#card-print-go')).toBeDisabled();await expect(page.locator('#print-sheet')).toBeEmpty();
});
test('one unavailable side is explained and requires explicit exclusion before printing',async({page})=>{
 await fixture(page);await page.route('**/worker-documents/cards/*/file?*',route=>{const u=new URL(route.request().url());return u.pathname.includes(C)&&u.searchParams.get('side')==='front'?route.fulfill({status:502,json:{detail:'Original file is unavailable. Upload a replacement.'}}):route.fulfill({status:200,contentType:'image/png',body:png})});
 await page.evaluate(()=>window.print=()=>window.cardPrintReady=true);await page.locator('#print-cards').click();await page.locator('#card-print-prepare').click();
 await expect(page.locator('#card-print-message')).toContainText('1 selected side(s) unavailable');await expect(page.locator('#card-print-preview')).toContainText('Construction Safety Orientation (1) · front');await expect(page.locator('#card-print-go')).toBeDisabled();expect(await page.evaluate(()=>window.cardPrintReady)).toBeFalsy();
 await page.locator('#card-print-exclude').click();await expect(page.locator('#card-print-go')).toBeEnabled();await expect(page.locator('#print-sheet img')).toHaveCount(2);await expect(page.locator('#print-sheet img').first()).toHaveAttribute('alt','back');await page.locator('#card-print-go').click();expect(await page.evaluate(()=>window.cardPrintReady)).toBe(true);
});
test('print selection has front-only and clear controls; closing discards the print pack',async({page})=>{
 await fixture(page);await page.locator('#print-cards').click();await page.locator('#card-print-fronts').click();await expect(page.locator('#card-print-count')).toContainText('2 sides');await page.locator('#card-print-none').click();await expect(page.locator('#card-print-prepare')).toBeDisabled();await page.locator('#card-print-all').click();await expect(page.locator('#card-print-count')).toContainText('3 sides');await page.locator('#card-print-close').click();await expect(page.locator('#card-print-dialog')).toBeHidden();expect(await page.evaluate(()=>document.body.classList.contains('wc-print-ready'))).toBe(false);
});

test('no expiry persists and existing front can be edited without a new file picker',async({page})=>{
 const {writes}=await fixture(page);await page.route('**/worker-documents/cards/*/file?*',r=>r.fulfill({contentType:'image/png',body:png}));
 await page.getByRole('button',{name:'Edit',exact:true}).first().click();await page.locator('#no-expiry').check();await expect(page.locator('[name=expiry_date]')).toBeDisabled();await page.locator('#save').click();await expect(page.locator('#edit-dialog')).toBeHidden();expect(writes[0].body).toMatchObject({no_expiry:true,expiry_date:null});
 await page.getByRole('button',{name:'Edit',exact:true}).first().click();await expect(page.locator('#no-expiry')).toBeChecked();await page.locator('#edit-saved-front').click();await expect(page.locator('#mask-canvas')).toBeVisible();await draw(page,.2,.2,.3,.3);await checkPages(page);await page.locator('#save').click();await expect(page.locator('#edit-dialog')).toBeHidden();expect(writes[1].method).toBe('POST');expect(writes[1].query.record_id).toBe(C);expect(writes[1].masking.pages[0].boxes).toHaveLength(1);expect(writes[2].body.no_expiry).toBe(true);
});

test('crop handles resize edges and standard crop, flatten and tilt retain black masks',async({page})=>{
 const {writes}=await fixture(page);await page.locator('#add').click();await page.locator('#front-file').setInputFiles({name:'card.png',mimeType:'image/png',buffer:png});
 await draw(page,.3,.3,.3,.3);await page.locator('#mask-crop').click();await expect(page.locator('.wc-crop-handle:visible')).toHaveCount(8);
 const h=page.getByRole('button',{name:'Top edge crop handle',exact:true});const before=await h.boundingBox();await h.focus();await page.keyboard.press('ArrowDown');expect((await h.boundingBox()).y).toBeGreaterThan(before.y);await page.locator('#mask-ratio').selectOption('card');await page.locator('#mask-crop-apply').click();
 let dims=await page.locator('#mask-canvas').evaluate(c=>[c.width,c.height]);expect(dims[0]/dims[1]).toBeCloseTo(85.6/53.98,1);
 await page.locator('#mask-flat').click();await expect(page.locator('.wc-crop-handle:visible')).toHaveCount(8);const corner=page.getByRole('button',{name:'Top left crop handle',exact:true});await corner.focus();await page.keyboard.press('ArrowRight');await page.locator('#mask-flat-apply').click();await expect(page.locator('#mask-confirm')).toBeEnabled();
 await page.locator('#mask-tilt').click();await page.locator('#mask-angle').fill('10');await page.locator('#mask-tilt-apply').click();await expect(page.locator('#mask-confirm')).toBeEnabled();const pixel=await page.locator('#mask-canvas').evaluate(c=>Array.from(c.getContext('2d').getImageData(Math.floor(c.width*.45),Math.floor(c.height*.45),1,1).data));expect(pixel.slice(0,3)).toEqual([0,0,0]);await checkPages(page);await page.locator('#save').click();await expect(page.locator('#edit-dialog')).toBeHidden();expect(writes[0].masking.pages[0].reviewed).toBe(true);
});

test('local card edge detection suggests a quad and uncertain images fall back to manual',async({page})=>{
 await fixture(page);await page.locator('#add').click();await page.locator('#front-file').setInputFiles({name:'card.png',mimeType:'image/png',buffer:png});await page.locator('#mask-auto').click();await expect(page.locator('#mask-flat-actions')).toBeVisible();await expect(page.locator('.wc-crop-handle:visible')).toHaveCount(8);
 const detection=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=400;c.height=300;const x=c.getContext('2d');x.fillStyle='#333';x.fillRect(0,0,400,300);x.fillStyle='white';x.beginPath();x.moveTo(60,65);x.lineTo(330,45);x.lineTo(350,225);x.lineTo(45,245);x.closePath();x.fill();const q=WorkerCardGeometry.detect(c);return{q,valid:!!q&&WorkerCardGeometry.valid(q)}});expect(detection.valid).toBe(true);expect(detection.q[0].x).toBeCloseTo(.15,1);
});

test('print pack groups four card pairs per A4 page without side captions',async({page})=>{
 const {cards}=await fixture(page);for(let i=2;i<5;i++)cards.push({...cards[0],id:'extra-'+i,label:'Additional course '+i});await page.route('**/worker-documents/cards/*/file?*',r=>r.fulfill({contentType:'image/png',body:png}));await page.getByRole('button',{name:'Sample Worker'}).click();await expect(page.locator('#card-count')).toHaveText('(5)');await page.locator('#print-cards').click();await page.locator('#card-print-prepare').click();await expect(page.locator('#card-print-go')).toBeEnabled();await expect(page.locator('#print-sheet .wc-print-page')).toHaveCount(2);await expect(page.locator('#print-sheet .wc-print-page').first().locator('article')).toHaveCount(4);await expect(page.locator('#print-sheet figcaption')).toHaveCount(0);
});
