const {test,expect}=require('@playwright/test');
const client='11111111-1111-4111-8111-111111111111',provider='22222222-2222-4222-8222-222222222222',driver='33333333-3333-4333-8333-333333333333',id='44444444-4444-4444-8444-444444444444';
const rules=[{id,client_id:client,client:{name:'CLIENT A'},site_name:'SITE A',billing_mode:'day',transport_rate:100,ot_rate:120,break_minutes:60,effective_from:'2026-01-01',active:true},{id:'55555555-5555-4555-8555-555555555555',client_id:client,client:{name:'CLIENT A'},site_name:'SITE A',billing_mode:'night',transport_rate:110,ot_rate:130,break_minutes:0,effective_from:'2026-01-01',active:true},{id:'66666666-6666-4666-8666-666666666666',client_id:client,client:{name:'CLIENT A'},site_name:'SITE A',billing_mode:'trip',transport_rate:85,ot_rate:null,break_minutes:0,effective_from:'2026-01-01',active:true}];
async function fixture(page){
 const writes=[],exports=[];
 await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',refresh_token:'test',expires_at:Date.now()+3600000})));
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(),url=new URL(req.url()),p=url.pathname;
  if(p.endsWith('/me'))return route.fulfill({json:{role:'admin',name:'Test Admin',user_id:'u1'}});
  if(p.includes('/export/')){exports.push(url);return route.fulfill({body:'export file',contentType:'application/octet-stream'});}
  if(req.method()!=='GET'){writes.push({path:p,data:req.postDataJSON()});return route.fulfill({json:{id,ok:true}});}
  if(p.endsWith('/setup'))return route.fulfill({json:{can_manage:true,clients:[{id:client,name:'CLIENT A'}],providers:[{id:provider,name:'VORTEX'}],work_types:[{id:'day',name:'Day Work'},{id:'night',name:'Night Work'},{id:'trip',name:'Trip Work'}],drivers:[{id:driver,name:'Driver One',phone:'6599999999',provider_id:provider,truck_no:'XF1'}]}});
  if(p.endsWith('/rate-rules'))return route.fulfill({json:rules});
  if(p.endsWith('/trips'))return route.fulfill({json:[{id,client_id:client,client:{name:'CLIENT A'},provider_id:provider,provider:{name:'VORTEX'},work_type_id:'day',billing_mode:'day',site_name:'SITE A',trip_date:'2026-09-30',trip_sheet_no:'S1',do_no:'DO1',truck_no:'XF1',start_time:'07:00',end_time:'20:00',normal_hours:10,ot_hours:2,total_hours:12,break_minutes:60,transport_rate:100,ot_rate:120,transport_amount:1240,quantity:1}]});
  return route.fulfill({json:[]});
 });return {writes,exports};
}
test('register removes requested columns and manual settings stay in edit popup',async({page},info)=>{
 const {writes}=await fixture(page);await page.goto('/tipper-trucks.html');await page.getByRole('button',{name:'Trip Register',exact:true}).click();
 const table=page.locator('#register');await expect(table.getByRole('columnheader',{name:'Trip Sheet',exact:true})).toHaveCount(0);for(const label of ['Material','Qty','Driver','Source'])await expect(table.getByRole('columnheader',{name:label,exact:true})).toHaveCount(0);
 await expect(table.getByRole('columnheader',{name:'Total Hours'})).toBeVisible();await expect(page.locator('#edit-dialog')).not.toBeVisible();await page.getByRole('button',{name:'Edit',exact:true}).click();
 const form=page.locator('#edit-form');await form.locator('[name="break_minutes"]').fill('0');await expect(page.locator('#edit-preview')).toContainText('OT 3.00 h');await expect(page.locator('#edit-preview')).toContainText('1,360.00');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:info.outputPath('tipper-edit-popup.png'),fullPage:true});
 await page.getByRole('button',{name:'Save Trip',exact:true}).click();await expect(page.locator('#edit-dialog')).not.toBeVisible();expect(writes[0].data.break_minutes).toBe(0);expect(writes[0].path).toContain('/trips/');
});
test('client site rules apply; overnight timing and trip billing preview',async({page})=>{
 await fixture(page);await page.goto('/tipper-trucks.html');await page.getByRole('button',{name:'Record Trip',exact:true}).first().click();await page.locator('#new-trip').click();const f=page.locator('#edit-form');
 await f.locator('[name="client_id"]').selectOption(client);await f.locator('[name="site_name"]').fill('SITE A');await f.locator('[name="site_name"]').dispatchEvent('change');await f.locator('[name="billing_mode"]').selectOption('night');
 await expect(f.locator('[name="transport_rate"]')).toHaveValue('110');await expect(f.locator('[name="break_minutes"]')).toHaveValue('0');await f.locator('[name="start_time"]').fill('19:00');await f.locator('[name="end_time"]').fill('07:00');await expect(page.locator('#edit-preview')).toContainText('Total 12.00 h');await expect(page.locator('#edit-preview')).toContainText('1,360.00');
 await f.locator('[name="billing_mode"]').selectOption('trip');await f.locator('[name="quantity"]').fill('3');await expect(page.locator('#edit-preview')).toContainText('255.00');await expect(f.locator('[name="start_time"]')).not.toBeVisible();
});
test('exports share inclusive date range and work type filters',async({page})=>{
 const {exports}=await fixture(page);await page.goto('/tipper-trucks.html');await page.getByRole('button',{name:'Monthly TRP',exact:true}).click();await page.locator('#period-mode').selectOption('range');await page.locator('#date-from').fill('2026-09-01');await page.locator('#date-to').fill('2026-09-30');await page.locator('#work-filter').selectOption('day-night');await page.locator('#report-client').selectOption(client);
 await page.locator('#report-csv').click();await expect.poll(()=>exports.length).toBe(1);await page.locator('#documents-pdf').click();await expect.poll(()=>exports.length).toBe(2);
 for(const url of exports){expect(url.searchParams.get('date_from')).toBe('2026-09-01');expect(url.searchParams.get('date_to')).toBe('2026-09-30');expect(url.searchParams.get('work_type')).toBe('day-night');expect(url.searchParams.get('client_id')).toBe(client);}
});
test('common link selects driver and shows only date status summary',async({page},info)=>{
 const requests=[];await page.route('**/api/v1/equipment/tipper/driver/**',async route=>{const req=route.request(),p=new URL(req.url()).pathname;requests.push(req.headers());if(p.endsWith('/setup'))return route.fulfill({json:req.headers()['x-tipper-driver']?{driver:{id:driver,name:'Driver One',truck_no:'XF1'},sites:rules}:{choose_driver:true,drivers:[{id:driver,name:'Driver One'}]}});return route.fulfill({json:[{date:'2026-09-30',approved:1,pending:0,rejected:0},{date:'2026-10-01',approved:0,pending:1,rejected:0}]});});
 await page.goto('/driver-upload.html#'+'a'.repeat(43));await page.locator('#driver-select').selectOption(driver);await page.locator('#driver-continue').click();await expect(page.locator('#history-lines')).toContainText('2026-09-30 · 1 Approved');await expect(page.locator('#history-lines')).toContainText('2026-10-01 · 1 Pending Review');
 expect(requests.some(r=>r['x-tipper-driver']===driver)).toBe(true);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:info.outputPath('driver-mobile-status.png'),fullPage:true});
});
test('next day upload keeps printed work date and requires driver check before submit',async({page})=>{
 let submitted=null;await page.route('**/api/v1/equipment/tipper/driver/**',async route=>{const req=route.request(),p=new URL(req.url()).pathname;
 if(p.endsWith('/setup'))return route.fulfill({json:{driver:{id:driver,name:'Driver One'},sites:rules}});
 if(p.endsWith('/status'))return route.fulfill({json:[]});
 if(p.endsWith('/preview'))return route.fulfill({json:{id,status:'draft',fields:{trip_date:'2026-09-30',do_no:'DO1',truck_no:'XF1',start_time:'07:00',end_time:'18:00',work_type:'Day Work'},warnings:[],quality_warnings:[],confidence:90}});
 submitted=req.postDataJSON();return route.fulfill({json:{id,status:'pending'}});
 });await page.goto('/driver-upload.html#'+'a'.repeat(43));await page.locator('#site').selectOption(client+'|SITE A');await page.locator('#file').setInputFiles({name:'sheet.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF test fixture')});await page.locator('#photo-checked').check();await page.locator('#read').click();await expect(page.locator('#confirm-form [name="trip_date"]')).toHaveValue('2026-09-30');await page.locator('#confirm-form [name="checked"]').check();await page.locator('#submit').click();await expect(page.locator('#status')).toContainText('Submitted successfully');expect(submitted.trip_date).toBe('2026-09-30');expect(submitted.checked).toBe(true);
});
test('OCR photo quality warning requires retake rather than driver submit',async({page})=>{
 await page.route('**/api/v1/equipment/tipper/driver/**',async r=>{const p=new URL(r.request().url()).pathname;if(p.endsWith('/setup'))return r.fulfill({json:{driver:{id:driver,name:'Driver One'},sites:rules}});if(p.endsWith('/preview'))return r.fulfill({json:{id,status:'draft',fields:{trip_date:'2026-09-30'},quality_warnings:['DO number is cropped'],warnings:[]}});return r.fulfill({json:[]});});
 await page.goto('/driver-upload.html#'+'a'.repeat(43));await page.locator('#site').selectOption(client+'|SITE A');await page.locator('#file').setInputFiles({name:'sheet.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF fixture')});await page.locator('#photo-checked').check();await page.locator('#read').click();await expect(page.locator('#submit')).toBeDisabled();await expect(page.locator('#ocr-warnings')).toContainText('cropped');
});
