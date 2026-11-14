const {test,expect}=require('@playwright/test');
async function fixture(page,role='admin',pending=false){
 await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',refresh_token:'test',expires_at:Date.now()+3600000})));
 const writes=[];
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(),u=new URL(req.url()),p=u.pathname;
  if(p.endsWith('/me'))return route.fulfill({json:{role,name:'Test Manager',user_id:'u1'}});
  if(p.endsWith('/dashboard'))return route.fulfill({json:{date:u.searchParams.get('date'),scoped:role==='site_sup',total_workers:3,on_leave:1,total_sites:1,today_allocated:3,today_mc:1,today_al:0,today_ul:0,month_normal_hours:24,month_ot_hours:6,morning_pending:pending?['ACTIVE SITE']:[],morning_completed:pending?[]:['ACTIVE SITE'],evening_pending:pending?['ACTIVE SITE']:[],evening_completed:pending?[]:['ACTIVE SITE'],site_summary:[{site_name:'ACTIVE SITE',today:2,month_nh:16,month_ot:4,site_active:true},{site_name:'OLD SITE',today:1,month_nh:8,month_ot:2,site_active:false}],leave_leaders:[{name:'Test Worker',code:'W01',mc:1,al:0,ul:0,total:1}]}});
  if(p.endsWith('/workers'))return route.fulfill({json:[{id:'w1',name:'Test Worker',worker_code:'W01',status:'active'}]});
  if(p.endsWith('/todos/t1')){writes.push(req.postDataJSON());return route.fulfill({json:{ok:true}});}
  if(p.endsWith('/todos'))return route.fulfill({json:[{id:'t1',text:'Review allocations',done:false,quadrant:'q1',due_date:'2026-11-03'}]});
  return route.fulfill({json:[]});
 });return writes;
}
test('previous blue home retains its cards, tables and six shortcuts',async({page})=>{
 await fixture(page);await page.goto('/home.html');
 await expect(page.locator('body')).toHaveClass(/legacy-blue-home/);await expect(page.locator('#kpis>.kpi')).toHaveCount(10);
 await expect(page.locator('.quick-actions a')).toHaveCount(6);await expect(page.locator('.quick-actions a[href^="pcs-"]')).toHaveCount(0);
 await expect(page.locator('#sites')).toContainText('ACTIVE SITE');await expect(page.locator('#home-leave-leaders')).toContainText('Test Worker');
 await expect(page.locator('link[href*="home-command-centre"]')).toHaveCount(0);
 const header=page.locator('#vcms-app-header:visible,header.brand:visible').first();await expect(header).toBeVisible();
 const channels=await header.evaluate(el=>{const c=getComputedStyle(el),s=c.backgroundImage==='none'?c.backgroundColor:c.backgroundImage;const m=s.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);return m?m.slice(1).map(Number):[];});
 expect(channels).toHaveLength(3);expect(channels[2]).toBeGreaterThan(channels[0]+50);expect(channels[2]).toBeGreaterThan(channels[1]+50);
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
test('legacy tasks keep the scroll-overlap fix and KPI details work',async({page},info)=>{
 test.skip(info.project.name!=='desktop-chromium','Desktop details and task column');await fixture(page);await page.goto('/home.html');
 await expect(page.locator('#tasks-body')).toContainText('Review allocations');
 await page.locator('.kpi').filter({hasText:'Active workers'}).click();await expect(page.locator('#kpi-modal-list')).toContainText('Test Worker');await page.keyboard.press('Escape');
 await page.evaluate(()=>window.scrollTo(0,500));
 const layout=await page.evaluate(()=>{const t=document.querySelector('.tasks'),s=document.querySelector('.desk-stack');return {position:getComputedStyle(t).position,gap:s.getBoundingClientRect().top-t.getBoundingClientRect().bottom};});
 expect(layout.position).toBe('static');expect(layout.gap).toBeGreaterThanOrEqual(0);
});
test('supervisor phone keeps its original lightweight home menu',async({page},info)=>{
 test.skip(info.project.name!=='mobile-safari','Supervisor phone');await fixture(page,'site_sup');await page.goto('/home.html');
 await expect(page.locator('.mnav a[href="attendance.html"]')).toBeVisible();await expect(page.locator('#kpis')).toBeHidden();await expect(page.locator('.tasks')).toBeHidden();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});

test('sidebar groups renamed pages without adding supervisor links',async({page},info)=>{
 await fixture(page,'site_sup');await page.goto('/home.html');
 const mobile=info.project.name==='mobile-safari';
 const menu=page.locator(mobile?'#mnav':'#vcms-app-nav');
 const safety=mobile?menu.locator('.msec').filter({hasText:'Safety & Training'}):menu.getByRole('button',{name:/Safety & Training/});
 await expect(safety).toBeVisible();
 if(!mobile)await safety.click();
 await expect(menu.locator('a[href="worker-cards.html"]')).toHaveText('Training Records');
 await expect(menu.locator('a[href="sic-register.html"]')).toHaveText('Site Induction Register (SIC)');
 await expect(menu.locator('a[href="attendance.html"]')).toHaveText('Mark Attendance');
 await expect(menu.locator('a[href="verify.html"],a[href="users.html"]')).toHaveCount(0);
});
