const {test,expect}=require('@playwright/test');
const sites=[{id:'s1',site_name:'PCS',status:'active',supervisors:[]},{id:'s2',site_name:'TWRP',status:'active',supervisors:[]}];
const workers=[{id:'w1',name:'Long Worker Name That Must Remain Fully Readable',worker_code:'VTX015',status:'active'},{id:'w2',name:'Available Worker',worker_code:'QA02',status:'active'},{id:'w3',name:'Other Site Worker',worker_code:'QA03',status:'active'},{id:'w4',name:'On Leave Worker',worker_code:'QA04',status:'on_leave'}];
async function fixture(page){
 let alloc=[{worker_id:'w3',site_id:'s2',site_name:'TWRP'}];const saves=[];
 await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',refresh_token:'test',expires_at:Date.now()+3600000})));
 await page.route('**/api/v1/**',async route=>{
 const ep=new URL(route.request().url()).pathname.split('/api/v1/')[1];
 if(ep==='allocations/bulk'){const data=route.request().postDataJSON();saves.push(data);alloc=alloc.filter(a=>a.site_id!==data.site_id).concat(data.worker_ids.map(id=>({worker_id:id,site_id:data.site_id,site_name:sites.find(s=>s.id===data.site_id).site_name})));return route.fulfill({json:{added:1,removed:0}});}
 const requests=sites.map(s=>({site_id:s.id,site_name:s.site_name,worker_id:'w1',worker_name:workers[0].name,worker_code:'VTX015'}));
 return route.fulfill({json:ep==='me'?{role:'admin',name:'Test Administrator',user_id:'u1'}:ep==='sites'?sites:ep==='workers'?workers:ep==='allocations'?alloc:ep==='requests'?requests:[]});
 });
 await page.goto('/allocation.html');await expect(page.locator('#summary')).not.toHaveText('Loading…');return saves;
}
test('desktop assignments survive view changes, update site totals, review and save only intended changes',async({page},info)=>{
 test.skip(info.project.name!=='desktop-chromium');
 const saves=await fixture(page);
 await expect(page.locator('.desktop-table')).toHaveCount(2);await expect(page.locator('#desktop-review')).not.toBeVisible();
 await page.locator('#tab-worker').click();await page.getByLabel('Assigned site for VTX015 '+workers[0].name).selectOption('s1');
 await expect(page.locator('tr.edited')).toHaveCount(1);await page.locator('#desktop-review').click();await expect(page.locator('#desktop-review-panel')).toContainText('Not working → PCS');
 await page.locator('#tab-site').click();await expect(page.locator('tr.edited')).toHaveCount(1);await expect(page.locator('.desktop-site-panels')).toContainText('Available workers');
 await page.locator('#tab-requests').click();await expect(page.locator('tr.edited')).toHaveCount(2);await expect(page.locator('#summary')).toContainText('1/2 requested workers allocated');
 await expect(page.locator('#selcount')).toHaveText('1 unsaved change');await page.locator('#save').click();await expect(page.locator('tr.edited')).toHaveCount(0);
 expect(saves).toHaveLength(1);expect(saves[0].worker_ids).toEqual(['w1']);
});
test('desktop full names, filters and narrower desktop fit without page overflow',async({page},info)=>{
 test.skip(info.project.name!=='desktop-chromium');await fixture(page);
 for(const width of [1920,1366,1024,900]){
 await page.setViewportSize({width,height:1000});await page.locator('#tab-worker').click();
 await expect(page.locator('.desktop-table').first()).toContainText(workers[0].name);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
 await page.locator('#search').fill('QA02');await expect(page.locator('.desktop-table tbody tr')).toHaveCount(1);await expect(page.locator('.desktop-table tbody')).toContainText('Available Worker');await page.locator('#search').fill('');
 }
});
test('mobile retains worker cards and existing controls in every mode',async({page},info)=>{
 test.skip(info.project.name!=='mobile-safari');await fixture(page);
 for(const mode of ['requests','worker','site']){
 await page.locator('#tab-'+mode).click();await expect(page.locator('.desktop-table')).toHaveCount(0);await expect(page.locator('#desktop-review')).not.toBeVisible();await expect(page.locator('#desktop-review-panel')).not.toBeVisible();
 await expect(page.locator('#list')).toContainText(workers[0].name);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
 }
 await expect(page.locator('#search')).toBeVisible();await expect(page.locator('#f-allochere')).toBeVisible();
});

test('drafts survive tabs on mobile and desktop, and date cancellation keeps them',async({page})=>{
 await fixture(page);
 await page.evaluate(()=>{ASSIGN.w1='s1';render();});
 for(const mode of ['worker','site','requests']){await page.locator('#tab-'+mode).click();expect(await page.evaluate(()=>ASSIGN.w1)).toBe('s1');}
 page.once('dialog',d=>d.dismiss());
 await page.locator('#date').fill('2026-11-02');
 expect(await page.evaluate(()=>ASSIGN.w1)).toBe('s1');
 expect(await page.locator('#date').inputValue()).toBe(await page.evaluate(()=>loadedDate));
 await expect(page.locator('#generate-whatsapp')).toHaveText('Save & Generate WhatsApp');
});

test('bulk assignment saves before generating; preview scope, summary and edited share text',async({page})=>{
 const saves=await fixture(page);
 await page.locator('#bulk-tools summary').click();
 await page.locator('#bulk-search').fill('Available Worker');
 await page.getByRole('button',{name:'Select matching',exact:true}).click();
 await page.locator('#bulk-site').selectOption('s1');
 await page.getByRole('button',{name:'Apply to selected workers',exact:true}).click();
 expect(await page.evaluate(()=>ASSIGN.w2)).toBe('s1');expect(saves).toHaveLength(0);
 await page.locator('#generate-whatsapp').click();
 await expect(page.locator('#allocation-message')).toBeVisible();expect(saves).toHaveLength(1);
 await expect(page.locator('#allocation-message-text')).toHaveValue(/QA02_AVAILABLE\ WORKER/);
 await expect(page.locator('#allocation-message-text')).toHaveValue(/TOTAL\ ALLOCATED:\ 2\ PAX/);
 await page.locator('#message-site').selectOption('s1');
 await expect(page.locator('#allocation-message-text')).not.toHaveValue(/QA03/);
 await page.locator('#message-format').selectOption('summary');
 await expect(page.locator('#allocation-message-text')).not.toHaveValue(/QA02/);
 await expect(page.locator('#allocation-message-text')).toHaveValue(/TOTAL\ ALLOCATED:\ 1\ PAX/);
 await page.locator('#allocation-message-text').fill('Edited message & review');
 await page.evaluate(()=>{window.open=(...args)=>{window.sharedArgs=args;};});
 await page.getByRole('button',{name:'Open WhatsApp',exact:true}).click();
 expect(await page.evaluate(()=>sharedArgs[0])).toBe('https://wa.me/?text=Edited%20message%20%26%20review');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});

test('failed save never opens a broadcast, and saved incomplete days do not show done',async({page})=>{
 await fixture(page);
 await expect(page.locator('#statusbar')).toContainText('Allocation saved');
 await expect(page.locator('#alloc-kpis')).toContainText('Unmet requests');
 await page.evaluate(()=>{ASSIGN.w1='s1';render();});
 await expect(page.locator('#alloc-exceptions')).toContainText('1 site request(s) unmet');
 await page.route('**/api/v1/allocations/bulk',r=>r.fulfill({status:409,json:{detail:'Attendance already recorded'}}));
 await page.locator('#generate-whatsapp').click();
 await expect(page.locator('#allocation-message')).not.toBeVisible();
 await expect(page.locator('#toast')).toContainText('Attendance already recorded');
});

