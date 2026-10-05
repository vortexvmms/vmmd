const {test,expect}=require('@playwright/test');
const pcs={effective_from:'2026-10-05',start_time:'07:00',lunch_start:'11:30',lunch_end:'12:00',end_time:'16:30',weekday_basic_hours:8,saturday_basic_hours:4,saturday_rule:'first_hours',lunch_rule:'overlap'};
async function fixture(page){
 const writes=[];
 await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',refresh_token:'test',expires_at:Date.now()+3600000})));
 await page.route('**/api/v1/**',async r=>{
 const p=new URL(r.request().url()).pathname;
 if(p.endsWith('/me'))return r.fulfill({json:{role:'admin',name:'Test',user_id:'u1'}});
 if(r.request().method()!=='GET'){writes.push(r.request().postDataJSON());return r.fulfill({json:{ok:true}});}
 if(p.endsWith('/sites'))return r.fulfill({json:[{id:'s1',site_code:'PCS-GBM',site_name:'PCS-GBM',status:'active',supervisors:[],work_schedules:[pcs]},{id:'s2',site_code:'OTHER',site_name:'OTHER',status:'active',supervisors:[],work_schedules:[]}]});
 if(p.endsWith('/attendance'))return r.fulfill({json:[{allocation_id:'a1',site_id:'s1',site_name:'PCS-GBM',worker_name:'Test Worker',worker_code:'QA01',marked:true,present:true,start_time:'07:00',default_start_time:'07:00',scheduled_end_time:'16:30',end_time:null,normal_hours:0,ot_hours:0,submitted:false,shift_type:'day'}]});
 return r.fulfill({json:[]});
 });return writes;
}
test('new sites inherit defaults; editing a name does not overwrite schedule',async({page})=>{
 const writes=await fixture(page);await page.goto('/sites.html');await page.locator('#fab').click();
 await expect(page.locator('#schedule-start_time')).toHaveValue('08:00');await expect(page.locator('#schedule-lunch_start')).toHaveValue('12:00');await expect(page.locator('#schedule-lunch_end')).toHaveValue('13:00');await expect(page.locator('#schedule-end_time')).toHaveValue('17:00');
 await page.locator('#m-code').fill('NEW');await page.locator('#m-name').fill('NEW');await page.locator('#m-save').click();await expect(page.locator('#modal')).toBeHidden();expect(writes[0].work_schedule).toBeUndefined();
 await page.getByText('PCS-GBM',{exact:true}).click();await expect(page.locator('#schedule-start_time')).toHaveValue('07:00');await page.locator('#m-name').fill('PCS-GBM RENAMED');await page.locator('#m-save').click();await expect(page.locator('#modal')).toBeHidden();expect(writes[1].work_schedule).toBeUndefined();
});
test('site rules can be edited without horizontal overflow',async({page},info)=>{
 const writes=await fixture(page);await page.goto('/sites.html');await page.getByText('OTHER',{exact:true}).click();
 await page.locator('#schedule-start_time').fill('07:00');await page.locator('#schedule-lunch_start').fill('11:30');await page.locator('#schedule-lunch_end').fill('12:00');await page.locator('#schedule-end_time').fill('16:30');await page.locator('#schedule-saturday_rule').selectOption('first_hours');await page.locator('#schedule-lunch_rule').selectOption('overlap');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:info.outputPath('site-schedule-settings.png'),fullPage:true});
 await page.locator('#m-save').click();await expect(page.locator('#modal')).toBeHidden();expect(writes[0].work_schedule.start_time).toBe('07:00');expect(writes[0].work_schedule.saturday_rule).toBe('first_hours');
});
test('attendance day mode uses site start and offers scheduled finish',async({page},info)=>{
 const writes=await fixture(page);await page.goto('/attendance.html?date=2026-10-05&site_id=s1');await expect(page.locator('.worker-card')).toHaveCount(1);if(info.project.name==='mobile-safari'){await expect(page.locator('.quick-time[data-t="16:30"]')).toBeVisible();await page.locator('.card-options').click();}else{await expect(page.locator('.tchip[data-t="16:30"]')).toBeVisible();}await page.locator('.mode-day').click();await expect.poll(()=>writes.length).toBeGreaterThan(0);expect(writes[0].changes[0].start_time).toBe('07:00');
});
