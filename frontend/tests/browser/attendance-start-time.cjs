// Run with node; requires the project's Playwright browser runtime.
const assert = require('node:assert/strict');
const {chromium,webkit}=require('playwright');
const base=process.env.ATTENDANCE_TEST_URL||'http://127.0.0.1:4173';
const output=process.env.ATTENDANCE_SCREENSHOTS;
const row=(id,date)=>({allocation_id:id,site_id:'s1',site_name:'LOGISTICS',worker_name:`Worker ${id}`,worker_code:id,marked:true,present:true,start_time:'08:00',end_time:'19:00',end_next_day:false,normal_hours:8,ot_hours:2,submitted:false,absence_type:'absent',shift_type:'day',date});
(async()=>{
for(const [engine,width] of [[chromium,1440],[chromium,900],[chromium,899],[chromium,640],[chromium,320],[webkit,390]]){
 const browser=await engine.launch({headless:true});const page=await browser.newPage({viewport:{width,height:900},serviceWorkers:'block'});
 let role='main_sup',mode='ok',calls=[];const records=new Map();
 await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test-token',refresh_token:'test-refresh',expires_at:Date.now()+3600000})));
 await page.route('**/api/v1/**',async r=>{const url=new URL(r.request().url()),p=url.pathname;
 if(p.endsWith('/me'))return r.fulfill({json:{name:'Test Manager',role,user_id:'u1'}});
 if(p.endsWith('/attendance/batch')){const changes=r.request().postDataJSON().changes;calls.push(changes);
 if(mode==='offline')return r.abort();
 return r.fulfill({json:{ok:mode==='ok',results:changes.map((c,i)=>{if(mode==='denied')return {allocation_id:c.allocation_id,ok:false,status:403,detail:'Month closed by payroll'};for(const rows of records.values()){const x=rows.find(x=>x.allocation_id===c.allocation_id);if(x){x.start_time=c.start_time;x.ot_hours=3;}}
 return {allocation_id:c.allocation_id,ok:true,normal_hours:8,ot_hours:3,day_type:'WD'};})}});}
 if(p.endsWith('/attendance')){const date=url.searchParams.get('date');if(!records.has(date))records.set(date,[row(date+'-1',date),row(date+'-2',date)]);return r.fulfill({json:records.get(date)});}
 return r.fulfill({json:[]});});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/attendance.html');await page.waitForSelector('.worker-card');await page.waitForTimeout(450);
 const initialOverflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
 const date=await page.locator('#date').inputValue();
 async function open(index=0){const card=page.locator('.worker-card').nth(index);if(width<900)await card.locator('.card-options').click();await card.locator('.tmore').evaluate(el=>el.scrollIntoView({block:'center'}));await card.locator('.tmore').click();await card.locator('.start-edit').evaluate(el=>el.scrollIntoView({block:'center'}));await card.locator('.start-edit').click();await page.waitForFunction(()=>document.querySelector('#start-dialog').open);}
 assert.equal(await page.locator('.start-edit').count(),0);
 assert.equal(await page.locator('#morning-btn').count(),1);assert.equal(await page.locator('#submit-btn').count(),1);
 await open();const bounds=await page.locator('#start-dialog').boundingBox();assert(bounds.x>=0&&bounds.y>=0&&bounds.x+bounds.width<=width+1&&bounds.y+bounds.height<=900+1);
 assert.equal(await page.locator('#start-bulk-label').isVisible(),false);
 if(output)await page.screenshot({path:`${output}/dialog-${width}-${engine===webkit?'webkit':'chromium'}.png`});
 await page.locator('#start-time').fill('07:00');await page.locator('#start-save').click();await page.waitForFunction(()=>!document.querySelector('#start-dialog').open);
 assert.equal(calls[0][0].start_time,'07:00');assert.equal(Object.keys(calls[0][0]).sort().join(','),'allocation_id,edit_reason,start_time');
 await page.evaluate(()=>sessionStorage.clear());await page.reload();await page.waitForSelector('.worker-card');assert((await page.locator('.worker-card').first().textContent()).includes('start 07:00'),JSON.stringify({width,date,records:[...records],text:await page.locator('.worker-card').first().textContent()}));
 await page.locator('#date').fill('2026-10-02');await page.locator('#date').dispatchEvent('change');await page.waitForFunction(()=>document.querySelector('.worker-card')?.textContent.includes('2026-10-02-1'));
 assert((await page.locator('.worker-card').first().textContent()).includes('start 08:00'),JSON.stringify({width,date,text:await page.locator('.worker-card').first().innerText()}));
 await page.locator('#date').fill(date);await page.locator('#date').dispatchEvent('change');await page.waitForFunction(d=>document.querySelector('.worker-card')?.textContent.includes(d+'-1'),date);
 for(let i=0;i<2;i++){await page.locator('.sel-cb').nth(i).evaluate(el=>el.scrollIntoView({block:'center'}));await page.locator('.sel-cb').nth(i).check();}await open();assert(await page.locator('#start-bulk-label').isVisible());await page.locator('#start-bulk').check();await page.locator('#start-time').fill('06:30');await page.locator('#start-save').click();await page.waitForFunction(()=>!document.querySelector('#start-dialog').open);assert.equal(calls.at(-1).length,2);
 // Permission errors stay actionable and never enter the automatic retry queue.
 await open();mode='denied';await page.locator('#start-save').click();await page.waitForFunction(()=>document.querySelector('#start-error').textContent.includes('Month closed'));
 assert.equal(await page.evaluate(()=>SAVE_QUEUE.size),0);await page.locator('#start-cancel').click();mode='ok';
 // Network failure stays in the dialog without creating an endless retry queue.
 await open();mode='offline';await page.locator('#start-save').click();await page.waitForFunction(()=>document.querySelector('#start-error').textContent.includes('before retrying'));assert.equal(await page.evaluate(()=>SAVE_QUEUE.size),0);await page.locator('#start-cancel').click();mode='ok';
 // Submitted corrections require a reason, including when applying to a group.
 records.get(date)[0].submitted=true;await page.reload();await page.waitForSelector('.worker-card');await open();assert(await page.locator('#start-reason-wrap').isVisible());await page.locator('#start-reason').fill('Early work confirmed');await page.locator('#start-save').click();await page.waitForFunction(()=>!document.querySelector('#start-dialog').open);assert.equal(calls.at(-1)[0].edit_reason,'Early work confirmed');
 role='site_sup';await page.evaluate(()=>{localStorage.removeItem('vmms_me_cache_v1');sessionStorage.clear()});await page.reload();await page.waitForSelector('.worker-card');const card=page.locator('.worker-card').first();if(width<900)await card.locator('.card-options').click();await card.locator('.tmore').click();assert.equal(await page.locator('.start-edit').count(),0);
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);assert(overflow<=Math.max(0,initialOverflow)+1,'New horizontal overflow');if(overflow>1)console.log(`Existing page overflow at ${width}px: ${overflow}px (dialog bounds checked separately)`);assert.deepEqual(errors,[]);
 console.log(`PASS ${engine===webkit?'WebKit':'Chromium'} ${width}px: individual, bulk, refresh, date isolation, submitted reason, permissions, layout`);await browser.close();
}
})().catch(e=>{console.error(e);process.exit(1)});
