const { test, expect } = require('@playwright/test');

async function correctionFixture(page, { pending = false, status = 400, partial = true } = {}) {
  const record = {allocation_id:'a1',site_id:'s1',site_name:'SOIL BUILD TUAS',
    worker_name:'Udaiyappan Velusamy',worker_code:'VES002',marked:true,present:true,
    start_time:'08:00',end_time:'19:00',end_next_day:false,normal_hours:8,ot_hours:2,
    submitted:true,absence_type:'absent',shift_type:'day',
    partial_leave_type:partial?'al':null,leave_portion:partial?'second_half':null,leave_value:partial?0.5:0};
  const calls=[];
  await page.addInitScript(({pending}) => {
    localStorage.setItem('vmms_session',JSON.stringify({access_token:'test-token',refresh_token:'test-refresh',expires_at:Date.now()+3600000}));
    if(pending)localStorage.setItem('vcms_attendance_pending_v1',JSON.stringify([{changes:{allocation_id:'a1',present:false,edit_reason:'Correction'},work_date:'2026-09-23',site_id:'s1'}]));
  },{pending});
  await page.route('**/api/v1/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/me'))return route.fulfill({json:{name:'Test Administrator',role:'admin',user_id:'u1'}});
    if(path.endsWith('/attendance/batch')){
      const changes=route.request().postDataJSON().changes;calls.push(changes);
      if(pending&&(status!==500||calls.length===1))return route.fulfill({json:{ok:false,results:[{allocation_id:'a1',ok:false,status,detail:status===400?'Partial leave requires a present worker and a half-day period':'Save rejected'}]}});
      Object.assign(record,changes[0]);record.normal_hours=record.present?7:0;record.ot_hours=0;
      return route.fulfill({json:{ok:true,results:[{allocation_id:'a1',ok:true,normal_hours:record.normal_hours,ot_hours:record.ot_hours,day_type:'WD'}]}});
    }
    if(path.endsWith('/attendance'))return route.fulfill({json:[record]});
    return route.fulfill({json:[]});
  });
  await page.goto('/attendance.html');
  await expect(page.getByText('Udaiyappan Velusamy',{exact:true})).toBeVisible();
  return { record, calls };
}

async function openCorrection(page, testInfo) {
  const card=page.locator('.worker-card');
  if(testInfo.project.name==='mobile-safari')await card.getByRole('button',{name:'Options',exact:true}).click();
  await card.getByRole('button',{name:'More',exact:true}).click();
  await card.getByRole('button',{name:'Edit Work Start Time',exact:true}).click();
  await expect(page.locator('#start-dialog')).toBeVisible();
}

test('submitted partial leave allows start correction and retains end time and AL',async ({page},testInfo)=>{
  const {record,calls}=await correctionFixture(page);
  await openCorrection(page,testInfo);
  await expect(page.locator('#start-reason-wrap')).toBeVisible();
  await page.locator('#start-time').fill('11:00');
  await page.locator('#start-reason').fill('Actual work began at 11 AM');
  await page.locator('#start-save').click();
  await expect(page.locator('#start-dialog')).not.toBeVisible();
  expect(calls[0][0]).toEqual({allocation_id:'a1',start_time:'11:00',edit_reason:'Actual work began at 11 AM'});
  expect(record.end_time).toBe('19:00');expect(record.partial_leave_type).toBe('al');expect(record.leave_value).toBe(0.5);
  await page.reload();
  await expect(page.getByText('VES002 · start 11:00',{exact:true})).toBeVisible();
  if(testInfo.project.name==='mobile-safari')await page.getByRole('button',{name:'Options',exact:true}).click();
  await expect(page.getByText('Worked 11:00–19:00 · Afternoon AL (0.5 day)',{exact:true})).toBeVisible();
});

for(const status of [400,403,404,422])test(`rejected attendance ${status} restores the saved card and unblocks start editing`,async ({page},testInfo)=>{
  const {calls}=await correctionFixture(page,{pending:true,status});
  await expect(page.locator('#sync-state')).toContainText('saved attendance restored');
  await expect(page.locator('.present-cb')).toBeChecked();
  await expect(page.locator('.worker-card')).not.toHaveClass(/worker-saving/);
  expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('vcms_attendance_pending_v1')))).toEqual([]);
  expect(calls).toHaveLength(1);
  await openCorrection(page,testInfo);
  await expect(page.locator('#start-time')).toHaveValue('08:00');
  await page.locator('#start-cancel').click();
});

test('transient attendance failures retain pending changes and retry normally',async ({page})=>{
  const {calls}=await correctionFixture(page,{pending:true,status:500,partial:false});
  await expect(page.locator('#sync-state')).toContainText('need retry');
  expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('vcms_attendance_pending_v1')).length)).toBe(1);
  await expect(page.locator('#sync-state')).toContainText('All changes saved',{timeout:10000});
  expect(calls).toHaveLength(2);
  await expect(page.locator('.present-cb')).not.toBeChecked();
  await expect(page.locator('.worker-card')).not.toHaveClass(/worker-saving/);
});
