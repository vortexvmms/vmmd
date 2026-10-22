const {test,expect}=require('@playwright/test');
async function fixture(page){
  const rows=[0,1,2].map(i=>({allocation_id:'a'+i,worker_id:'w'+i,worker_name:'Worker '+i,worker_code:'EMP-'+i,site_id:'s1',site_name:'Site',marked:true,present:true,start_time:'08:00',end_time:null,normal_hours:0,ot_hours:0,submitted:false,absence_type:'absent',shift_type:'day'}));
  const writes=[];
  await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',expires_at:Date.now()+3600000})));
  await page.route('**/api/v1/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/me'))return route.fulfill({json:{role:'admin',name:'Admin',user_id:'u1'}});
    if(path.endsWith('/sites'))return route.fulfill({json:[{id:'s1',site_name:'Site',status:'active'}]});
    if(path.endsWith('/attendance/batch')){const body=route.request().postDataJSON();writes.push(body);return route.fulfill({json:{results:body.changes.map(c=>({allocation_id:c.allocation_id,ok:true,normal_hours:8,ot_hours:2}))}});}
    if(path.endsWith('/attendance'))return route.fulfill({json:rows});
    return route.fulfill({json:[]});
  });
  await page.goto('/attendance.html?date=2026-10-22&site_id=s1');
  await expect(page.locator('.worker-card')).toHaveCount(3);return writes;
}
test('views preserve selected workers, search and pending attendance',async({page,isMobile})=>{
  const writes=await fixture(page);
  await expect(page.locator('body')).toHaveAttribute('data-att-view',isMobile?'card':'list');
  await page.locator('.sel-cb').first().check();
  for(const view of ['gallery','list','card']){
    await page.locator('[data-view='+view+']').click();
    await expect(page.locator('.sel-cb').first()).toBeChecked();
    await expect(page.locator('#groupcount')).toHaveText('1');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  }
  await page.locator('#att-search').fill('EMP-1');await expect(page.locator('.worker-card')).toHaveCount(1);
  await page.locator('[data-view=gallery]').click();await expect(page.locator('#att-search')).toHaveValue('EMP-1');
  await page.locator('.tchip[data-t="19:00"]').click();
  await page.locator('[data-view=list]').click();
  await expect.poll(()=>writes.length).toBe(1);
  expect(writes[0].changes[0]).toMatchObject({allocation_id:'a1',end_time:'19:00'});
  await page.reload();await expect(page.locator('body')).toHaveAttribute('data-att-view','list');
});
test('portrait fallback and gallery sizing on mobile and desktop',async({page})=>{
  await fixture(page);await page.locator('[data-view=gallery]').click();
  await expect(page.locator('.worker-portrait').first()).toContainText('W0');
  const size=await page.locator('.worker-portrait').first().boundingBox();expect(size.width).toBeGreaterThan(100);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
