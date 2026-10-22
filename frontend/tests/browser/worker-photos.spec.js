const {test,expect}=require('@playwright/test');
const PNG=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5S0AAAAASUVORK5CYII=','base64');
async function fixture(page,role='admin'){
  const workers=[{id:'w1',worker_code:'EMP-1',name:'Sample Worker',status:'active',photo_path:null}];const writes=[];
  await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',expires_at:Date.now()+3600000})));
  await page.route('**/api/v1/**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname;
    if(path.endsWith('/me'))return route.fulfill({json:{role,name:'Admin',user_id:'u1'}});
    if(path.endsWith('/workers'))return route.fulfill({json:workers});
    if(path.includes('/worker-photos/')){
      writes.push({method:req.method(),bytes:req.postDataBuffer()?.length});workers[0].photo_path=req.method()==='DELETE'?null:'w1/photo.jpg';
      return route.fulfill({json:{worker_id:'w1',photo_path:workers[0].photo_path}});
    }
    return route.fulfill({json:[]});
  });
  await page.goto('/workers.html');await expect(page.locator('#count')).toContainText('1 active');return writes;
}
test('management uploads cropped portrait and removes it',async({page,isMobile})=>{
  const writes=await fixture(page);
  if(isMobile)await page.locator('#list>div').first().click();else await page.getByRole('button',{name:'Edit',exact:true}).click();
  await page.getByRole('button',{name:'Manage profile photo'}).click();
  await page.locator('#photo-file').setInputFiles({name:'face.png',mimeType:'image/png',buffer:PNG});
  await expect(page.locator('#photo-save')).toBeEnabled();await page.locator('#photo-zoom').fill('1.5');
  await page.locator('#photo-save').click();await expect(page.locator('#photo-editor')).not.toBeVisible();
  expect(writes[0].method).toBe('POST');expect(writes[0].bytes).toBeGreaterThan(100);
  await page.getByRole('button',{name:'Manage profile photo'}).click();
  page.once('dialog',d=>d.accept());await page.locator('#photo-remove').click();
  await expect.poll(()=>writes.filter(w=>w.method==='DELETE').length).toBe(1);
});
test('bulk import requires matching preview before writes',async({page})=>{
  const writes=await fixture(page);await page.getByRole('button',{name:'Bulk upload profile photos'}).click();
  await page.locator('#bulk-photo-files').setInputFiles([{name:'EMP-1.png',mimeType:'image/png',buffer:PNG},{name:'UNKNOWN.png',mimeType:'image/png',buffer:PNG}]);
  await expect(page.locator('#bulk-photo-status')).toContainText('1 matched / 2 selected');expect(writes).toHaveLength(0);
  await page.locator('#bulk-photo-upload').click();await expect(page.locator('#bulk-photo-status')).toContainText('1 saved. 0 failed.');expect(writes[0].method).toBe('POST');
});
test('supervisor has no photo management controls',async({page})=>{
  await fixture(page,'site_sup');await expect(page.getByRole('button',{name:'Bulk upload profile photos'})).toBeHidden();await expect(page.getByRole('button',{name:'Edit',exact:true})).toHaveCount(0);
});
