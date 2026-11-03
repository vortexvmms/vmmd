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
 const before=await page.locator('.tasks').evaluate(el=>el.getBoundingClientRect().top);
 await page.evaluate(()=>window.scrollTo(0,500));
 const layout=await page.evaluate(()=>{const task=document.querySelector('.tasks');return{position:getComputedStyle(task).position,top:task.getBoundingClientRect().top,railCards:document.querySelectorAll('.home-task-rail>.tasks,.home-task-rail>.desk-stack').length,overflow:document.documentElement.scrollWidth>innerWidth};});
 expect(layout.position).toBe('static');expect(layout.top).toBeLessThan(before);expect(layout.railCards).toBe(1);expect(layout.overflow).toBe(false);
 await page.locator('.tcheck').check();await expect.poll(()=>writes.length).toBe(1);expect(writes[0]).toEqual({done:true});
});
test('supervisor phone retains the lightweight role-scoped landing page',async({page},info)=>{
 test.skip(info.project.name!=='mobile-safari','Supervisor phone landing');await fixture(page,'site_sup');await page.goto('/home.html');
 await expect(page.locator('.mnav')).toBeVisible();await expect(page.locator('#kpis')).toBeHidden();await expect(page.locator('.home-task-rail')).toBeHidden();
 await expect(page.locator('.mnav a[href="attendance.html"]')).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});

test('home removes repeated chrome and keeps readable labels',async({page},info)=>{
 test.skip(info.project.name!=='desktop-chromium','Desktop header contrast');await fixture(page);await page.goto('/home.html');
 await expect(page.locator('.home-heading h1')).toHaveCount(1);await expect(page.locator('#subgreet')).not.toContainText('YOUR SITE OVERVIEW');
 await expect(page.locator('#vcms-view-role')).toBeVisible();await expect(page.locator('#vcms-role-chip')).toBeHidden();await expect(page.locator('.vcms-app-title')).toBeHidden();
 await expect(page.locator('.kpi .d').first()).toBeHidden();await expect(page.locator('#home-submission-details')).not.toHaveAttribute('open','');
 await page.locator('#home-submission-details summary').click();await expect(page.locator('#desk-morning')).toBeVisible();
 const ratios=await page.evaluate(()=>{const lum=c=>{const rgb=c.match(/[0-9.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4)});return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];};const ratio=(a,b)=>(Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);const label=getComputedStyle(document.querySelector('.kpi .l')),head=getComputedStyle(document.querySelector('table.dt thead th'));return [ratio(label.color,'rgb(255,255,255)'),ratio(head.color,head.backgroundColor)];});
 ratios.forEach(r=>expect(r).toBeGreaterThanOrEqual(4.5));
});
test('pending submissions expand details automatically',async({page},info)=>{
 test.skip(info.project.name!=='desktop-chromium','Desktop submission details');await fixture(page,'admin',true);await page.goto('/home.html');
 await expect(page.locator('#home-submission-details')).toHaveAttribute('open','');await expect(page.locator('#desk-m-copy')).toBeVisible();await expect(page.locator('#exceptions')).toContainText('pending');
});
