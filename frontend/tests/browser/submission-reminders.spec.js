const {test,expect}=require('@playwright/test');
async function fixture(page,{missing=false,fail=false}={}){
 const rows=[{allocation_id:'a1',site_id:'s1',site_name:'TEST SITE',worker_name:'Test Worker',worker_code:'T01',marked:true,present:true,start_time:'08:00',end_time:missing?null:'17:00',normal_hours:8,ot_hours:0,submitted:false,shift_type:'day'},
 {allocation_id:'a2',site_id:'s2',site_name:'OTHER SITE',worker_name:'Other Worker',worker_code:'T02',marked:true,present:true,start_time:'08:00',end_time:null,normal_hours:0,ot_hours:0,submitted:false,shift_type:'day'}];
 const submissions=[];
 await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',refresh_token:'test',expires_at:Date.now()+3600000})));
 await page.route('**/api/v1/**',async route=>{
 const url=new URL(route.request().url()),path=url.pathname;
 if(path.endsWith('/me'))return route.fulfill({json:{role:'admin',name:'Test',user_id:'u1'}});
 if(path.endsWith('/attendance/submit')){submissions.push(route.request().postDataJSON());if(fail)return route.fulfill({status:500,json:{detail:'Submission unavailable'}});rows.filter(x=>x.site_id==='s1').forEach(x=>x.submitted=true);return route.fulfill({json:{ok:true,submitted:1}});}
 if(path.endsWith('/attendance/batch')){const changes=route.request().postDataJSON().changes;changes.forEach(c=>Object.assign(rows.find(x=>x.allocation_id===c.allocation_id),c));return route.fulfill({json:{results:changes.map(c=>({allocation_id:c.allocation_id,ok:true,normal_hours:8,ot_hours:0}))}});}
 if(path.endsWith('/attendance'))return route.fulfill({json:rows});
 if(path.endsWith('/dashboard'))return route.fulfill({json:{date:url.searchParams.get('date'),total_workers:2,total_sites:2,today_allocated:2,morning_pending:[],morning_completed:['TEST SITE','OTHER SITE'],evening_pending:['TEST SITE','OTHER SITE'],evening_completed:[],site_summary:[]}});
 return route.fulfill({json:[]});
 });
 return {rows,submissions};
}
test('saved end times need explicit submission; submit from leave dialog completes correct date/site',async({page})=>{
 const {submissions}=await fixture(page);
 await page.goto('/attendance.html?date=2026-09-30&site_id=s1');
 await expect(page.locator('#completion-panel')).toContainText('All end times saved');
 await expect(page.locator('#completion-footer')).toContainText('Submit to finish');
 if(process.env.VCMS_REVIEW_OUTPUT)await page.screenshot({path:process.env.VCMS_REVIEW_OUTPUT+'/'+test.info().project.name+'-ready.png'});
 expect(submissions).toHaveLength(0);
 await page.locator('a[href="home.html"]').first().click();
 await expect(page.locator('#leave-dialog')).toBeVisible();
 if(process.env.VCMS_REVIEW_OUTPUT)await page.screenshot({path:process.env.VCMS_REVIEW_OUTPUT+'/'+test.info().project.name+'-leave.png'});
 await page.locator('#leave-stay').click();
 await expect(page).toHaveURL(/attendance/);
 await page.locator('a[href="home.html"]').first().click();
 page.once('dialog',d=>d.accept());
 await page.locator('#leave-submit').click();
 await expect(page).toHaveURL(/home.html/);
 expect(submissions).toEqual([{work_date:'2026-09-30',site_id:'s1',stage:'evening'}]);
});
test('final confirmed save reveals completion prompt',async({page},info)=>{
 await fixture(page,{missing:true});await page.goto('/attendance.html');
 await expect(page.locator('#completion-panel')).toContainText('1 worker(s) remaining');
 const card=page.locator('.worker-card').first();
 await card.getByRole('button',{name:'5PM',exact:true}).click();
 await expect(page.locator('#completion-panel')).toContainText('All end times saved');
});
test('submission failure retains page and reminder',async({page})=>{
 const {submissions}=await fixture(page,{fail:true});await page.goto('/attendance.html');
 await expect(page.locator('#completion-panel')).toContainText('All end times saved');
 await page.locator('a[href="home.html"]').first().click();page.once('dialog',d=>d.accept());await page.locator('#leave-submit').click();
 await expect(page.locator('#leave-copy')).toContainText('not confirmed');await expect(page).toHaveURL(/attendance/);expect(submissions).toHaveLength(1);
});
test('switching sites prompts before losing review context',async({page})=>{
 await fixture(page);await page.goto('/attendance.html');await expect(page.locator('#completion-panel')).toContainText('All end times saved');
 await page.locator('#site').selectOption('s2');await expect(page.locator('#leave-dialog')).toBeVisible();await expect(page.locator('#site')).toHaveValue('s1');
 await page.locator('#leave-anyway').click();await expect(page.locator('#site')).toHaveValue('s2');await expect(page.locator('#completion-panel')).toContainText('1 worker(s) remaining');
});
test('Home separates ready sites and links to exact date/site',async({page})=>{
 await fixture(page);await page.goto('/home.html');
 await expect(page.locator('#ready-submissions')).toContainText('TEST SITE');
 await expect(page.locator('#ready-submissions')).not.toContainText('OTHER SITE');
 await page.locator('#ready-submissions a').click();await expect(page.locator('#site')).toHaveValue('s1');await expect(page.locator('#completion-panel')).toContainText('All end times saved');
});

test('unmarked and syncing attendance cannot be ready; submitted sites disappear',async({page})=>{
 const {rows}=await fixture(page);rows[0].marked=false;await page.goto('/attendance.html');
 await expect(page.locator('#completion-panel')).toContainText('attendance marking');
 const checks=await page.evaluate(()=>{
  const base={marked:true,present:true,end_time:'17:00',submitted:false};
  return [VCMSAttendanceCompletion.status([base],true).ready,
    VCMSAttendanceCompletion.status([{...base,submitted:true}],false).ready,
    VCMSAttendanceCompletion.status([],false).ready,
    VCMSAttendanceCompletion.status([{...base,present:false,end_time:null}],false).ready];
 });
 expect(checks).toEqual([false,false,false,true]);
});
test('leave without submitting navigates without an extra browser warning',async({page})=>{
 const {submissions}=await fixture(page);await page.goto('/attendance.html');await expect(page.locator('#completion-panel')).toContainText('All end times saved');
 let dialogs=0;page.on('dialog',async d=>{dialogs++;await d.dismiss()});
 await page.locator('a[href="home.html"]').first().click();await page.locator('#leave-anyway').click();
 await expect(page).toHaveURL(/home.html/);expect(dialogs).toBe(0);expect(submissions).toHaveLength(0);
});
