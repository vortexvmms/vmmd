const {test,expect}=require('@playwright/test');
const W='10000000-0000-0000-0000-000000000001',C='30000000-0000-0000-0000-000000000001';
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII=','base64');
async function fixture(page,{conflict=false}={}){
 const writes=[],cards=[{id:C,worker_id:W,category:'course',label:'Construction Safety Orientation',institute:'Sample Training Centre',cert_no:'COURSE-001',issued_date:'2025-01-10',expiry_date:'2025-12-31',image_path:W+'/front.jpg',back_image_path:W+'/back.jpg',updated_at:'v1'},{id:'30000000-0000-0000-0000-000000000002',worker_id:W,category:'work_permit',label:'Work permit',expiry_date:'2028-06-30',image_path:W+'/permit.jpg',updated_at:'v1'}],certificates=[];
 await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',expires_at:Date.now()+3600000})));
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(),u=new URL(req.url()),p=u.pathname;
  if(p.endsWith('/me'))return route.fulfill({json:{role:'site_sup',name:'Test Supervisor',user_id:'u1'}});
  if(!p.includes('/worker-documents/'))return route.fulfill({json:[]});
  if(p.endsWith('/workers'))return route.fulfill({json:u.searchParams.get('search')==='nobody'?[]:[{id:W,name:'Sample Worker',worker_code:'EMP-050',status:'active'}]});
  if(p.endsWith('/file'))return route.fulfill({status:502,json:{detail:'Original file is unavailable. The saved record is retained; upload a replacement if available.'}});
  const kind=p.includes('/certificates')?'certificates':'cards',rows=kind==='cards'?cards:certificates;
  if(req.method()==='POST'){
   writes.push({method:'POST',path:p,query:Object.fromEntries(u.searchParams)});
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
 const {writes}=await fixture(page);await page.locator('#add').click();await page.locator('[name=label]').fill('New course');await page.locator('#front-file').setInputFiles({name:'front.png',mimeType:'image/png',buffer:png});await page.locator('#back-file').setInputFiles({name:'back.png',mimeType:'image/png',buffer:png});await page.locator('#save').click();await expect(page.locator('#edit-dialog')).not.toBeVisible();expect(writes.map(w=>w.method)).toEqual(['POST','POST','PATCH']);expect(writes[0].query).toEqual({worker_id:W,side:'front'});expect(writes[1].query).toMatchObject({worker_id:W,side:'back',record_id:'new-cards',updated_at:'v1'});expect(writes[2].body.updated_at).toBe('v2');
});
test('certificate upload and title editing use the certificate section',async({page})=>{
 const {writes}=await fixture(page);await page.locator('#certificates-tab').click();await page.locator('#add').click();await expect(page.locator('#back-label')).toBeHidden();await page.locator('[name=title]').fill('Trade certificate');await page.locator('#front-file').setInputFiles({name:'trade.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4 test')});await page.locator('#save').click();await expect(page.getByRole('heading',{name:'Trade certificate'})).toBeVisible();expect(writes[0].path).toContain('/certificates/upload');expect(writes[1].body).toEqual({updated_at:'v1',title:'Trade certificate'});
});
test('a stale edit stays open and asks the supervisor to refresh',async({page})=>{
 const {writes}=await fixture(page,{conflict:true});await page.getByRole('button',{name:'Edit',exact:true}).first().click();await page.locator('[name=label]').fill('Stale correction');await page.locator('#save').click();await expect(page.locator('#edit-error')).toContainText('Refresh before editing');await expect(page.locator('#edit-dialog')).toBeVisible();expect(writes).toHaveLength(1);
});

test('card sheet loads both sides and retains the selected worker identity for printing',async({page})=>{
 await fixture(page);
 await page.route('**/worker-documents/cards/*/file?*',route=>route.fulfill({status:200,contentType:'image/png',body:png}));
 await page.evaluate(()=>{window.print=()=>{window.cardPrintReady=true}});
 await page.locator('#print-cards').click();await expect.poll(()=>page.evaluate(()=>window.cardPrintReady)).toBeTruthy();
 await expect(page.locator('#print-sheet img')).toHaveCount(3);
 await expect(page.locator('#print-sheet h1')).toHaveText('Sample Worker · EMP-050');
 await page.emulateMedia({media:'print'});await expect(page.locator('#print-sheet')).toBeVisible();await expect(page.locator('main')).toBeHidden();
});
