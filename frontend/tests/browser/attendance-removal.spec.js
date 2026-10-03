const {test,expect}=require('@playwright/test');
async function fixture(page,{error=null,marked=true}={}){
 const rows=[{allocation_id:'40000000-0000-0000-0000-000000000001',site_id:'s1',site_name:'TEST SITE',worker_name:'Extra Worker',worker_code:'QA01',marked,present:marked,start_time:'08:00',end_time:marked?'17:00':null,normal_hours:marked?8:0,ot_hours:0,submitted:marked,shift_type:'day',allocation_updated_at:'2026-10-01T00:00:00Z',attendance_updated_at:marked?'2026-10-01T00:00:00Z':null},
 {allocation_id:'40000000-0000-0000-0000-000000000002',site_id:'s1',site_name:'TEST SITE',worker_name:'Keep Worker',worker_code:'QA02',marked:true,present:true,start_time:'08:00',end_time:'17:00',normal_hours:8,ot_hours:0,submitted:false,shift_type:'day',allocation_updated_at:'2026-10-01T00:00:00Z',attendance_updated_at:'2026-10-01T00:00:00Z'}];
 const removals=[];
 await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',refresh_token:'test',expires_at:Date.now()+3600000})));
 await page.route('**/api/v1/**',async route=>{
 const path=new URL(route.request().url()).pathname;
 if(path.endsWith('/me'))return route.fulfill({json:{role:'admin',name:'Test',user_id:'u1'}});
 if(path.endsWith('/attendance/remove')){removals.push(route.request().postDataJSON());if(error)return route.fulfill({status:403,json:{detail:error}});rows.splice(0,1);return route.fulfill({json:{ok:true}});}
 if(path.endsWith('/attendance'))return route.fulfill({json:rows});
 if(path.endsWith('/dashboard'))return route.fulfill({json:{today_allocated:rows.length,total_workers:2,total_sites:1,morning_pending:[],morning_completed:['TEST SITE'],evening_pending:['TEST SITE'],evening_completed:[],site_summary:[]}});
 return route.fulfill({json:[]});
 });
 await page.goto('/attendance.html?date=2026-10-03&site_id=s1');await expect(page.locator('.worker-card')).toHaveCount(2);
 return removals;
}
test('remove only selected day, with reason and recorded hours review; refresh totals and cache',async({page},info)=>{
 const removals=await fixture(page);
 await page.getByRole('button',{name:'Remove from this day',exact:true}).first().click();
 await expect(page.locator('#remove-context')).toHaveText('2026-10-03 · TEST SITE');
 await expect(page.locator('#remove-record')).toContainText('Normal 8h');
 await expect(page.locator('#remove-record')).toContainText('Submitted');
 await page.locator('#remove-confirm').click();expect(removals).toHaveLength(0);
 await page.locator('#remove-reason').selectOption('not_scheduled');
 if(process.env.VCMS_REVIEW_OUTPUT)await page.screenshot({path:process.env.VCMS_REVIEW_OUTPUT+'/'+info.project.name+'-remove-day.png'});
 await page.locator('#remove-confirm').click();
 await expect(page.locator('#remove-dialog')).not.toBeVisible();await expect(page.locator('.worker-card')).toHaveCount(1);
 await expect(page.locator('#summary')).toContainText('1 allocated');await expect(page.locator('#hours-total')).toContainText('Normal 8.0h');
 expect(removals[0]).toEqual({allocation_id:'40000000-0000-0000-0000-000000000001',reason:'not_scheduled',allocation_updated_at:'2026-10-01T00:00:00Z',attendance_updated_at:'2026-10-01T00:00:00Z'});
 const cached=await page.evaluate(()=>JSON.parse(localStorage.getItem('vcms_att_day_2026-10-03')));expect(cached).toHaveLength(1);expect(cached[0].worker_code).toBe('QA02');
});
test('keep worker makes no changes',async({page})=>{
 const removals=await fixture(page);await page.locator('.remove-day').first().click();await page.locator('#remove-cancel').click();await expect(page.locator('.worker-card')).toHaveCount(2);expect(removals).toHaveLength(0);
});
test('payroll denial keeps worker and explains failure',async({page})=>{
 const removals=await fixture(page,{error:'Month closed by payroll. This day cannot be removed.'});await page.locator('.remove-day').first().click();await page.locator('#remove-reason').selectOption('allocated_by_mistake');await page.locator('#remove-confirm').click();await expect(page.locator('#remove-error')).toContainText('Month closed');await expect(page.locator('.worker-card')).toHaveCount(2);expect(removals).toHaveLength(1);
});
test('unmarked worker can be removed without creating an absence',async({page})=>{
 const removals=await fixture(page,{marked:false});await page.locator('.remove-day').first().click();await expect(page.locator('#remove-record')).toContainText('No attendance');await page.locator('#remove-reason').selectOption('allocated_by_mistake');await page.locator('#remove-confirm').click();await expect(page.locator('.worker-card')).toHaveCount(1);expect(removals[0].attendance_updated_at).toBeNull();
});
