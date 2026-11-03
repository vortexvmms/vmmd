const {test,expect}=require('@playwright/test');
async function fixture(page,role='admin'){
 await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',refresh_token:'test',expires_at:Date.now()+3600000})));
 const writes=[];
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(),u=new URL(req.url()),p=u.pathname;
  if(p.endsWith('/me'))return route.fulfill({json:{role,name:'Test Manager',user_id:'u1'}});
  if(p.endsWith('/dashboard'))return route.fulfill({json:{date:u.searchParams.get('date'),scoped:role==='site_sup',total_workers:3,on_leave:1,total_sites:1,today_allocated:3,today_mc:1,today_al:0,today_ul:0,month_normal_hours:24,month_ot_hours:6,morning_pending:[],morning_completed:['ACTIVE SITE'],evening_pending:[],evening_completed:['ACTIVE SITE'],site_summary:[{site_name:'ACTIVE SITE',today:2,month_nh:16,month_ot:4,site_active:true},{site_name:'OLD SITE',today:1,month_nh:8,month_ot:2,site_active:false}],leave_leaders:[{name:'Test Worker',code:'W01',mc:1,al:0,ul:0,total:1}]}});
  if(p.endsWith('/workers'))return route.fulfill({json:[{id:'w1',name:'Test Worker',worker_code:'W01',status:'active'}]});
  if(p.endsWith('/todos/t1')){writes.push(req.postDataJSON());return route.fulfill({json:{ok:true}});}
  if(p.endsWith('/todos'))return route.fulfill({json:[{id:'t1',text:'Review allocations',done:false,quadrant:'q1',due_date:'2026-11-03'}]});
  return route.fulfill({json:[]});
 });return writes;
}
test('Command Centre keeps both tables, filters totals and removes PCS shortcuts',async({page})=>{
 await fixture(page);await page.goto('/home.html');
 await expect(page.locator('#kpis .kpi')).toHaveCount(10);
 await expect(page.locator('.quick-actions a')).toHaveCount(6);
 await expect(page.locator('.quick-actions a[href^="pcs-"]')).toHaveCount(0);
 await expect(page.locator('.home-sites-panel table')).toBeVisible();
 await expect(page.locator('.home-leave-section table')).toBeVisible();
 await expect(page.locator('#home-leave-leaders')).toContainText('Test Worker');
 await page.locator('#home-site-search').fill('OLD');
 await expect(page.locator('#sites tr')).toHaveCount(1);
 await expect(page.locator('#sites')).toContainText('Historical');
 await expect(page.locator('#sites-foot td').first()).toHaveText('1');
 await page.locator('#home-site-search').fill('');await page.locator('#home-site-status').selectOption('active');
 await expect(page.locator('#sites')).not.toContainText('OLD SITE');
 await expect(page.locator('#sites-foot td').first()).toHaveText('2');
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
test('task rail stays in flow when scrolling and KPI detail actions still work',async({page},info)=>{
 test.skip(info.project.name!=='desktop-chromium','Desktop task rail and KPI details');
 const writes=await fixture(page);await page.goto('/home.html');await expect(page.locator('#tasks-body')).toContainText('Review allocations');
 await page.locator('.kpi[data-kind="workers"]').click();await expect(page.locator('#kpi-modal')).toHaveClass(/open/);await expect(page.locator('#kpi-modal-list')).toContainText('Test Worker');await page.keyboard.press('Escape');
 await page.evaluate(()=>window.scrollTo(0,500));
 const layout=await page.evaluate(()=>{const task=document.querySelector('.tasks'),next=document.querySelector('.desk-stack'),r=task.getBoundingClientRect(),n=next.getBoundingClientRect();return{position:getComputedStyle(task).position,gap:n.top-r.bottom,overflow:document.documentElement.scrollWidth>innerWidth};});
 expect(layout.position).toBe('static');expect(layout.gap).toBeGreaterThanOrEqual(0);expect(layout.overflow).toBe(false);
 await page.locator('.tcheck').check();await expect.poll(()=>writes.length).toBe(1);expect(writes[0]).toEqual({done:true});
});
test('supervisor phone retains the lightweight role-scoped landing page',async({page},info)=>{
 test.skip(info.project.name!=='mobile-safari','Supervisor phone landing');await fixture(page,'site_sup');await page.goto('/home.html');
 await expect(page.locator('.mnav')).toBeVisible();await expect(page.locator('#kpis')).toBeHidden();await expect(page.locator('.home-task-rail')).toBeHidden();
 await expect(page.locator('.mnav a[href="attendance.html"]')).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
