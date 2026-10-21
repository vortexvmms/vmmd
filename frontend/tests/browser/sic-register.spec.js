const {test,expect}=require('@playwright/test');
test.beforeEach(async({page})=>{await page.clock.setFixedTime(new Date('2026-10-21T08:00:00Z'))});
const SITE='10000000-0000-0000-0000-000000000001',WORKER='20000000-0000-0000-0000-000000000001',ADVARIO='10000000-0000-0000-0000-000000000002';
async function boot(page,role='admin',count=123,workerRows=null){await page.route('**/backend/assets/vortex-logo.png',r=>r.fulfill({contentType:'image/png',body:''}));let writes=[];let records=Array.from({length:count},(_,i)=>({id:'30000000-0000-0000-0000-'+String(i+1).padStart(12,'0'),worker_id:WORKER,site_id:i%2?ADVARIO:SITE,name:'Worker '+String(i+1).padStart(3,'0'),fin:'FIN'+(i+1),site_name:i%2?'ADVARIO':'CCP3',sic_date:'2026-01-01',validity_months:12,expiry_date:i%2?'2026-01-01':'2026-12-31',is_current:true,archived:false,remarks:'',override_reason:'',created_at:'2026-01-01T00:00:00Z',updated_at:'2026-01-01T00:00:00Z'}));
await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({access_token:'test',refresh_token:'test',expires_at:Date.now()+3600000})));
await page.route('**/api/v1/**',r=>r.fulfill({json:r.request().url().endsWith('/me')?{name:'QA User',role,user_id:'qa'}:[]}));
await page.route('**/rest/v1/**',async r=>{let u=new URL(r.request().url()),name=u.pathname.split('/').pop();if(name==='my_user_id')return r.fulfill({json:'qa'});if(name==='users')return r.fulfill({json:[{id:'qa',name:'QA User',role}]});if(name==='sic_save'){let data=r.request().postDataJSON();writes.push(data);let row={...records[0],...data.p_data,id:data.p_id||'new-'+records.length,name:(workerRows||[{id:WORKER,name:'Worker 001'}]).find(w=>w.id===data.p_data.worker_id)?.name||'Worker',site_name:data.p_data.site_id===ADVARIO?'ADVARIO':'CCP3',is_current:true,archived:false,updated_at:'2026-10-16T00:00:00Z',created_at:'2026-10-16T00:00:00Z'};if(data.p_renew)records.find(x=>x.id===data.p_renew).is_current=false;if(data.p_id)records.splice(records.findIndex(x=>x.id===data.p_id),1,row);else records.push(row);return r.fulfill({json:row})}if(name==='workers')return r.fulfill({json:workerRows||[{id:WORKER,name:'Worker 001',worker_code:'VEW001',fin:'FIN1',status:'active'}]});if(name==='sites')return r.fulfill({json:[{id:SITE,site_name:'CCP3',status:'active'},{id:ADVARIO,site_name:'ADVARIO',status:'archived'},{id:'40000000-0000-0000-0000-000000000001',site_name:'TUAS LOT',status:'active'},{id:'40000000-0000-0000-0000-000000000002',site_name:'TUAS LOT',status:'archived'}]});if(name==='site_supervisors')return r.fulfill({json:[{site_id:SITE}]});if(name==='sic_records')return r.fulfill({json:records});return r.fulfill({json:[]})});
await page.goto('/sic-register.html');await expect(page.locator('#notice')).toContainText('current SIC records');return {writes,records}}
async function openAttach(page){const menu=page.locator('#log-table .sic-row-menu').first();await menu.locator('summary').click();await menu.getByRole('button',{name:'Attach cards',exact:true}).click()}
async function exportAction(page,id){await page.locator('#export-menu').evaluate(el=>el.open=true);await page.locator('#'+id).click()}
async function openHistory(page){const menu=page.locator('#log-table .sic-row-menu').first();await menu.locator('summary').click();await menu.getByRole('button',{name:'History',exact:true}).click()}
test('compact navigation, responsive layout, filters and pagination',async({page,isMobile})=>{await boot(page);await expect(page.locator('#dash-context')).toContainText('123 SIC records');await page.getByRole('button',{name:'SIC Log',exact:true}).click();await expect(page.locator('#log-table tbody tr')).toHaveCount(50);await expect(page.locator('#row-count')).toContainText('123 matching');await page.getByRole('button',{name:'Next',exact:true}).click();await expect(page.locator('#page-number')).toContainText('Page 2 of 3');await page.locator('#search').fill('Worker 123');await expect(page.locator('#log-table tbody tr')).toHaveCount(1);await expect(page.locator('#row-count')).toContainText('1 matching');await expect(page.locator('#log-table')).toContainText('Worker 123');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();await page.getByRole('button',{name:'SIC Log',exact:true}).click();await openAttach(page);await expect(page.locator('#upload')).toBeVisible();await page.getByRole('button',{name:'New Entry',exact:true}).click();await expect(page.locator('#entry')).toBeVisible()});
test('renewal creates a new course and keeps historical entry',async({page})=>{const {writes,records}=await boot(page,'admin',1);await page.getByRole('button',{name:'SIC Log',exact:true}).click();await page.getByRole('button',{name:'Renew',exact:true}).click();await page.locator('#designation').fill('Welder');await page.locator('#sic-date').fill('2026-10-01');await page.locator('#sic-date').press('Tab');await expect(page.locator('#expiry')).toHaveValue('2027-09-30');await page.getByRole('button',{name:'Save',exact:true}).click();await expect(page.locator('#notice')).toContainText('SIC record and selected cards saved');expect(writes).toHaveLength(1);expect(writes[0].p_renew).toBe(records[0].id);expect(records[0].is_current).toBeFalsy();await openHistory(page);await expect(page.locator('#detail-body')).toContainText('Previous');await expect(page.locator('#detail-body')).toContainText('Current')});
test('site supervisor has read-only controls',async({page})=>{await boot(page,'site_sup',2);await expect(page.locator('#action-table [data-renew]')).toHaveCount(0);await page.getByRole('button',{name:'SIC Log',exact:true}).click();await expect(page.getByRole('button',{name:'Renew',exact:true})).toHaveCount(0);await page.getByRole('button',{name:'New Entry',exact:true}).click();await expect(page.locator('#save')).toBeHidden()});
test('direct PDF gets all matching rows beyond pagination',async({page})=>{await boot(page);await page.route('**/jspdf.umd.min.js',r=>r.fulfill({contentType:'text/javascript',body:`window.jspdf={jsPDF:class{static API={autoTable:true};constructor(){this.internal={getNumberOfPages:()=>1}}setFontSize(){}text(){}splitTextToSize(){return ['All rows']}addImage(){}autoTable(v){window.__pdfRows=v.body}setPage(){}save(n){window.__pdfName=n}}}` }));await page.getByRole('button',{name:'SIC Log',exact:true}).click();await exportAction(page,'pdf');await expect.poll(()=>page.evaluate(()=>window.__pdfRows?.length)).toBe(123);await page.locator('#search').fill('Worker 123');await exportAction(page,'pdf');await expect.poll(()=>page.evaluate(()=>window.__pdfRows?.length)).toBe(1);await page.locator('#export-menu').evaluate(el=>el.open=true);await page.locator('#export-scope').selectOption('all');await exportAction(page,'pdf');await expect.poll(()=>page.evaluate(()=>window.__pdfRows?.length)).toBe(123)});
test('invalid card format is rejected before upload',async({page})=>{await boot(page,'admin',1);await page.getByRole('button',{name:'SIC Log',exact:true}).click();await openAttach(page);await page.locator('#upload-files').setInputFiles({name:'invalid.pdf',mimeType:'application/pdf',buffer:Buffer.from('not a PDF')});await expect(page.locator('#notice')).toContainText('use a valid PDF, JPG or PNG')});

test('print layout removes desktop sidebar offsets and includes all rows',async({page})=>{await page.addInitScript(()=>{window.print=()=>{window.__printed=true}});await boot(page);await page.getByRole('button',{name:'SIC Log',exact:true}).click();await exportAction(page,'print');await expect.poll(()=>page.evaluate(()=>window.__printed)).toBeTruthy();await page.emulateMedia({media:'print'});await expect(page.locator('#print-sheet')).toBeVisible();await expect(page.locator('#print-sheet tbody tr')).toHaveCount(123);expect(await page.locator('body').evaluate(el=>getComputedStyle(el).marginLeft)).toBe('0px')});

test('archived Advario remains selectable for SIC entries',async({page})=>{await boot(page);await page.getByRole('button',{name:'New Entry',exact:true}).click();await expect(page.locator('#entry-site option').filter({hasText:'ADVARIO'})).toHaveCount(1);await page.locator('#entry-site').selectOption(ADVARIO);await expect(page.locator('#entry-site')).toHaveValue(ADVARIO)});
test('dashboard scope counts stay stable while status selections filter the action list',async({page})=>{
 await boot(page);await expect(page.locator('#summary button')).toHaveCount(4);await expect(page.locator('[data-stat="all"] b')).toHaveText('1');await expect(page.locator('#dash-context')).toContainText('123 SIC records');
 await expect(page.locator('#dash-status')).toHaveCount(0);await expect(page.locator('#dash-more-panel')).toBeHidden();await expect(page.locator('#dashboard')).not.toContainText('Recently added / renewed');
 await page.locator('[data-stat="expired"]').click();await expect(page.locator('#action-count')).toContainText('10 of 61');await expect(page.locator('[data-stat="valid"] b')).toHaveText('62');
 await page.locator('#dash-site').selectOption(ADVARIO);await expect(page.locator('#dash-context')).toContainText('61 SIC records');await expect(page.locator('#site-summary tbody tr')).toHaveCount(1);
 await page.locator('#dash-log').click();await expect(page.locator('#filter-site')).toHaveValue(ADVARIO);await expect(page.locator('#filter-status')).toHaveValue('Expired');await expect(page.locator('#row-count')).toContainText('61 matching records');
 await page.getByRole('button',{name:'Dashboard',exact:true}).click();await page.locator('#dash-more').click();await page.locator('#dash-expiry-from').fill('2026-02-01');await page.locator('#dash-expiry-from').press('Tab');await expect(page.locator('#dash-context')).toContainText('0 SIC records');await expect(page.locator('#dash-more')).toHaveText('More filters (1)');
 await page.locator('#dash-clear').click();await expect(page.locator('#dash-context')).toContainText('123 SIC records');await page.locator('#dash-search').fill('Worker 123');await expect(page.locator('#dash-context')).toContainText('1 SIC records');
});

test('SIC site lists omit the unused archived TUAS LOT duplicate',async({page})=>{await boot(page);await expect(page.locator('#dash-site option').filter({hasText:'TUAS LOT'})).toHaveCount(1);await expect(page.locator('#filter-site option').filter({hasText:'TUAS LOT'})).toHaveCount(1);await page.getByRole('button',{name:'New Entry',exact:true}).click();await expect(page.locator('#entry-site option').filter({hasText:'TUAS LOT'})).toHaveCount(1)});

test('card upload accepts an empty 201 attachment response without deleting or retrying',async({page})=>{
await boot(page,'admin',1);
let saves=0,deletes=0;
await page.route('**/storage/v1/object/sic-cards/**',r=>{if(r.request().method()==='DELETE')deletes++;return r.fulfill({json:{Key:'saved-card'}})});
await page.route('**/storage/v1/object/sic-cards',r=>{deletes++;return r.fulfill({json:[]})});
await page.route('**/rest/v1/sic_attachments',r=>{saves++;return r.fulfill({status:201,body:''})});
await page.getByRole('button',{name:'SIC Log',exact:true}).click();await openAttach(page);
await page.locator('#upload-record').selectOption('30000000-0000-0000-0000-000000000001');
await page.locator('#upload-files').setInputFiles({name:'card.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nTest SIC card')});
await page.locator('#upload-form button[type="submit"]').click();
await expect(page.locator('#upload-status')).toContainText('Cards uploaded successfully');
expect(saves).toBe(1);expect(deletes).toBe(0);
await expect(page.locator('#upload-preview .sic-preview')).toHaveCount(0);
});

async function cardEntry(page,texts){
  const state=await boot(page,'admin',0,[{id:WORKER,name:'TEST WORKER',worker_code:'VEW001',fin:'G1234567X',status:'active'},{id:'20000000-0000-0000-0000-000000000002',name:'SECOND WORKER',worker_code:'VEW002',fin:'M7654321Y',status:'active'}]);
  await page.evaluate(parts=>{window.SICCardReader.read=async()=>parts.map((text,fileIndex)=>({fileIndex,page:1,text,confidence:98,ocr:true}))},texts);
  await page.route('**/storage/v1/object/sic-cards/**',r=>r.fulfill({json:{Key:'saved'}}));
  await page.route('**/rest/v1/sic_attachments',r=>r.fulfill({status:201,body:''}));
  await page.getByRole('button',{name:'New Entry',exact:true}).click();
  return state;
}
const CARD='Name: TEST WORKER\nFIN: G1234567X\nDesignation: Welder\nSite: CCP3\nSIC Date: 01/10/2026\nValidity: 12 months\nExpiry Date: 31/08/2027\nCard No: SIC-123\nIssued by: SITE OFFICE';
const fakeCard=name=>({name,mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nSynthetic reader input')});
test('card autofill preserves printed expiry and requires review before saving',async({page},info)=>{
  const {writes}=await cardEntry(page,[CARD]);
  await page.locator('#entry-files').setInputFiles(fakeCard('front.pdf'));
  await expect(page.locator('#read-status')).toContainText('reading complete');
  await expect(page.locator('#worker-search')).toHaveValue('VEW001 · TEST WORKER · G1234567X');
  await expect(page.locator('#worker')).toHaveValue(WORKER);
  await expect(page.locator('#fin')).toHaveValue('G1234567X');
  await expect(page.locator('#entry-site')).toHaveValue(SITE);
  await expect(page.locator('#sic-date')).toHaveValue('2026-10-01');
  await expect(page.locator('#expiry')).toHaveValue('2027-08-31');
  await expect(page.locator('#expiry-source')).toContainText('Printed');
  await expect(page.locator('#override-wrap')).toBeVisible();
  await expect(page.locator('#remarks')).toHaveValue('Card reference: SIC-123\nIssuer: SITE OFFICE');
  await page.locator('#sic-date').fill('2026-09-01');await page.locator('#sic-date').press('Tab');
  await expect(page.locator('#expiry')).toHaveValue('2027-08-31');
  await page.locator('#save').click();await expect(page.locator('#entry-error')).toContainText('confirm');expect(writes).toHaveLength(0);
  await page.locator('#card-confirmed').check();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  await page.screenshot({path:info.outputPath('sic-autofill.png'),fullPage:true});
  await page.locator('#save').click();await expect(page.locator('#notice')).toContainText('selected cards saved');expect(writes).toHaveLength(1);expect(writes[0].p_data.expiry_date).toBe('2027-08-31');
});
test('multiple worker files stay as separate drafts and preserve edits when switching',async({page})=>{
  await cardEntry(page,[CARD,'Name: SECOND WORKER\nFIN: M7654321Y\nDesignation: Driver\nSite: ADVARIO\nInduction Date: 01/09/2026']);
  await page.locator('#entry-files').setInputFiles([fakeCard('one.pdf'),fakeCard('two.pdf')]);
  await expect(page.locator('#draft-count')).toContainText('2 entries');
  await page.locator('#entry-notes summary').click();await page.locator('#remarks').fill('Checked card one');
  await page.locator('#card-draft').selectOption('1');
  await expect(page.locator('#fin')).toHaveValue('M7654321Y');
  await expect(page.locator('#entry-site')).toHaveValue(ADVARIO);
  await expect(page.locator('#expiry-source')).toContainText('Calculated');
  await expect(page.locator('#entry-preview')).toContainText('two.pdf');
  await expect(page.locator('#entry-preview')).not.toContainText('one.pdf');
  await page.locator('#card-draft').selectOption('0');await expect(page.locator('#remarks')).toHaveValue('Checked card one');
});
test('late card result cannot overwrite the form after cancellation',async({page})=>{
  await cardEntry(page,[CARD]);
  await page.evaluate(()=>{window.SICCardReader.read=()=>new Promise(resolve=>window.finishReading=()=>resolve([{fileIndex:0,page:1,text:'FIN: G1234567X',ocr:true,confidence:99}]))});
  await page.locator('#entry-files').setInputFiles(fakeCard('slow.pdf'));
  await expect(page.locator('#cancel-read')).toBeVisible();
  await page.locator('#cancel-read').click();await page.locator('#fin').fill('MANUAL');
  await page.evaluate(()=>window.finishReading());await expect(page.locator('#fin')).toHaveValue('MANUAL');await expect(page.locator('#card-review')).toBeHidden();
});
test('compact manual entry keeps optional space collapsed and one navigation row',async({page,isMobile},info)=>{
  await boot(page,'admin',0);await page.getByRole('button',{name:'New Entry',exact:true}).click();
  await expect(page.locator('.sic-tabs button')).toHaveCount(3);await expect(page.locator('#remarks')).toBeHidden();await expect(page.locator('#override-wrap')).toBeHidden();
  const nav=await page.locator('.sic-navigation').boundingBox();expect(nav.height).toBeLessThan(60);
  await page.locator('#worker-search').fill('VEW001');await expect(page.locator('#worker')).toHaveValue(WORKER);await expect(page.locator('#fin')).toHaveValue('FIN1');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  await page.screenshot({path:info.outputPath('sic-compact.png'),fullPage:true});
});
test('saving a card batch advances drafts and attaches each worker file once',async({page})=>{
  const {writes}=await cardEntry(page,[CARD,'Name: SECOND WORKER\nFIN: M7654321Y\nDesignation: Driver\nSite: ADVARIO\nInduction Date: 01/09/2026']);
  let uploaded=0;await page.route('**/storage/v1/object/sic-cards/**',r=>{uploaded++;return r.fulfill({json:{Key:'saved'}})});
  await page.locator('#entry-files').setInputFiles([fakeCard('one.pdf'),fakeCard('two.pdf')]);
  await expect(page.locator('#draft-count')).toContainText('2 entries');await page.locator('#card-confirmed').check();await page.locator('#save').click();
  await expect(page.locator('#fin')).toHaveValue('M7654321Y');await expect(page.locator('#draft-count')).toContainText('1 entries');
  await page.locator('#card-confirmed').check();await page.locator('#save').click();await expect(page.locator('#notice')).toContainText('selected cards saved');
  expect(writes).toHaveLength(2);expect(writes.map(x=>x.p_data.fin)).toEqual(['G1234567X','M7654321Y']);expect(uploaded).toBe(2);await expect(page.locator('#refresh')).toBeEnabled();
});

test('dashboard shortcuts handle today, next seven days and stable overview counts',async({page},info)=>{
 await boot(page,'admin',0);
 const dates=['2026-10-11','2026-10-20','2026-10-21','2026-10-28','2026-11-20','2026-11-21','2026-12-20','2026-12-21'];
 const rows=dates.map((expiry_date,i)=>({id:'deadline-'+i,worker_id:WORKER,site_id:i<2?ADVARIO:SITE,name:'Due '+i,fin:'G1234567X',site_name:i<2?'ADVARIO':'CCP3',sic_date:'2026-01-01',expiry_date,validity_months:12,is_current:true,archived:false,created_at:'2026-10-01',updated_at:'2026-10-01'}));
 await page.route('**/rest/v1/sic_records?**',r=>r.fulfill({json:rows}));await page.locator('#refresh').click();
 await expect(page.locator('#dash-context')).toContainText('8 SIC records');await expect(page.locator('[data-stat="valid"] b')).toHaveText('3');await expect(page.locator('[data-stat="30"] b')).toHaveText('3');await expect(page.locator('[data-stat="expired"] b')).toHaveText('2');
 await expect(page.locator('#action-count')).toContainText('5 of 5');await expect(page.locator('#action-table tbody tr').first()).toContainText('10 days overdue');await expect(page.locator('#action-table')).toContainText('Expires today');
 await page.locator('[data-dash-view="7"]').click();await expect(page.locator('#action-count')).toContainText('2 of 2');await expect(page.locator('[data-stat="expired"] b')).toHaveText('2');
 await page.locator('[data-dash-view="60"]').click();await expect(page.locator('#action-count')).toContainText('5 of 5');
 await page.locator('#dash-log').click();await expect(page.locator('#expiry-from')).toHaveValue('2026-10-21');await expect(page.locator('#expiry-to')).toHaveValue('2026-12-20');await expect(page.locator('#row-count')).toContainText('5 matching records');
 await page.getByRole('button',{name:'Dashboard',exact:true}).click();await page.locator('[data-dash-view="urgent"]').click();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();await page.screenshot({path:info.outputPath('sic-dashboard.png'),fullPage:true,animations:'disabled'});
});
test('site summary opens exact matching rows and omits sites without records',async({page})=>{
 await boot(page);await expect(page.locator('#site-summary tbody tr')).toHaveCount(2);await expect(page.locator('#site-summary tbody tr').first()).toContainText('ADVARIO');await expect(page.locator('#site-summary')).not.toContainText('TUAS LOT');
 await page.locator('#dash-search').fill('Worker 002');await page.locator(`[data-site-id="${ADVARIO}"][data-site-view="expired"]`).click();
 await expect(page.locator('#filter-site')).toHaveValue(ADVARIO);await expect(page.locator('#filter-status')).toHaveValue('Expired');await expect(page.locator('#search')).toHaveValue('Worker 002');await expect(page.locator('#row-count')).toContainText('1 matching records');
});
test('dashboard supports direct renewal and original-card viewing with role-aware controls',async({page})=>{
 await boot(page,'admin',2);let read=false;
 await page.route('**/rest/v1/sic_attachments?**',r=>r.fulfill({json:[{id:'card-1',record_id:'30000000-0000-0000-0000-000000000002',object_key:'record/card',mime_type:'image/png',filename:'card.png'}]}));
 await page.route('**/storage/v1/object/authenticated/sic-cards/record/card',r=>{read=true;return r.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aH5sAAAAASUVORK5CYII=','base64')})});
 await page.locator('#refresh').click();await page.locator('#action-table').getByRole('button',{name:'View card',exact:true}).click();await expect(page.locator('#preview-dialog')).toBeVisible();expect(read).toBe(true);await page.locator('#close-preview').click();
 await page.locator('#action-table').getByRole('button',{name:'Renew',exact:true}).click();await expect(page.locator('#entry-title')).toContainText('Renew SIC');await expect(page.locator('#entry-site')).toHaveValue(ADVARIO);
});
test('refresh updates directory status and a failed refresh keeps the last complete snapshot',async({page})=>{
 await boot(page,'admin',2);await expect(page.locator('#dash-updated')).toContainText('SGT');const updated=await page.locator('#dash-updated').textContent();
 await page.route('**/rest/v1/workers?**',r=>r.fulfill({json:[{id:WORKER,name:'Worker 001',worker_code:'VEW001',fin:'FIN1',status:'inactive'}]}));await page.locator('#refresh').click();await expect(page.locator('#dash-context')).toContainText('0 SIC records');
 await page.locator('#dash-more').click();await page.locator('#dash-worker').selectOption('all');await expect(page.locator('#dash-context')).toContainText('2 SIC records');
 await page.route('**/rest/v1/sic_records?**',r=>r.fulfill({status:503,json:{message:'Temporary test failure'}}));await page.locator('#refresh').click();await expect(page.locator('#notice')).toHaveText('Temporary test failure');await expect(page.locator('#dash-context')).toContainText('2 SIC records');await expect(page.locator('#dash-updated')).toHaveText(updated);
});
test('recent activity is available from the log and orders the latest records first',async({page})=>{
 const {records}=await boot(page,'admin',2);records[1].created_at='2026-10-20';await page.locator('#refresh').click();await page.getByRole('button',{name:'SIC Log',exact:true}).click();await page.locator('#log-more').click();await page.locator('#sort').selectOption('created_at');await expect(page.locator('#sort')).toHaveValue('created_at');await expect(page.locator('#log-table tbody tr').first()).toContainText('Worker 002');
});

async function fillManualEntry(page){await page.getByRole('button',{name:'New Entry',exact:true}).click();await page.locator('#worker-search').fill('VEW001');await page.locator('#entry-site').selectOption(SITE);await page.locator('#sic-date').fill('2026-10-01');await page.locator('#sic-date').press('Tab')}
test('new entries require a listed designation or an explicit custom role',async({page},info)=>{
 const {writes}=await boot(page,'admin',0);await fillManualEntry(page);await expect(page.locator('#designation-options option')).toHaveCount(14);
 await page.locator('#save').click();expect(writes).toHaveLength(0);expect(await page.locator('#designation').evaluate(el=>el.validity.valueMissing)).toBe(true);
 await page.locator('#designation').fill('Other — specify');await expect(page.locator('#designation-other')).toBeVisible();await page.locator('#save').click();expect(writes).toHaveLength(0);
 await page.locator('#designation-other').fill('Pipe Fitter');await page.screenshot({path:info.outputPath('sic-designation-entry.png'),fullPage:true,animations:'disabled'});await page.locator('#save').click();await expect(page.locator('#notice')).toContainText('selected cards saved');expect(writes[0].p_data.designation).toBe('Pipe Fitter');await expect(page.locator('#log-table')).toContainText('Pipe Fitter');
});
test('designation accepts WSHC, Safety Supervisor and directly typed custom roles',async({page})=>{
 const {writes}=await boot(page,'admin',0);await fillManualEntry(page);await expect(page.locator('#designation-options option[value="WSHC"]')).toHaveCount(1);await expect(page.locator('#designation-options option[value="Safety Supervisor"]')).toHaveCount(1);await page.locator('#designation').fill('Marine Safety Coordinator');await page.locator('#save').click();await expect(page.locator('#notice')).toContainText('selected cards saved');expect(writes[0].p_data.designation).toBe('Marine Safety Coordinator');await expect(page.locator('#log-table')).toContainText('Marine Safety Coordinator');
});
test('editing legacy records keeps unknown designation until the user supplies one',async({page})=>{
 const {writes}=await boot(page,'admin',1);await page.getByRole('button',{name:'SIC Log',exact:true}).click();await expect(page.locator('#log-table')).toContainText('Not specified');const menu=page.locator('#log-table .sic-row-menu').first();await menu.locator('summary').click();await menu.getByRole('button',{name:'Edit',exact:true}).click();await expect(page.locator('#designation')).toHaveValue('');expect(await page.locator('#designation').evaluate(el=>el.required)).toBe(false);await page.locator('#save').click();await expect(page.locator('#notice')).toContainText('selected cards saved');expect(writes[0].p_data.designation).toBe(null);
});
test('renewal prefills designation and preserves the previous course role',async({page})=>{
 const {records,writes}=await boot(page,'admin',1);records[0].designation='Rigger & Signalman';await page.locator('#refresh').click();await page.getByRole('button',{name:'SIC Log',exact:true}).click();await page.getByRole('button',{name:'Renew',exact:true}).click();await expect(page.locator('#designation')).toHaveValue('Rigger & Signalman');await page.locator('#designation').fill('Driver');await page.locator('#sic-date').fill('2026-10-01');await page.locator('#sic-date').press('Tab');await page.locator('#save').click();await expect(page.locator('#notice')).toContainText('selected cards saved');expect(writes[0].p_data.designation).toBe('Driver');expect(records[0].designation).toBe('Rigger & Signalman');await openHistory(page);await expect(page.locator('#detail-body')).toContainText('Designation: Rigger & Signalman');await expect(page.locator('#detail-body')).toContainText('Designation: Driver');
});
test('log keeps advanced controls collapsed and supports designation filtering',async({page},info)=>{
 const {records}=await boot(page,'admin',3);records[1].designation='Welder';records[2].designation='Driver';await page.locator('#refresh').click();await page.getByRole('button',{name:'SIC Log',exact:true}).click();await expect(page.locator('#log-more-panel')).toBeHidden();await expect(page.locator('#export-menu')).not.toHaveAttribute('open','');await expect(page.locator('#log-table thead th')).toHaveCount(6);await expect(page.locator('#page-number')).toContainText('1–3 of 3');
 await page.locator('#log-more').click();await page.locator('#filter-designation').selectOption('value:Welder');await expect(page.locator('#row-count')).toContainText('1 matching records');await expect(page.locator('#log-table')).toContainText('Worker 002');await page.locator('#filter-designation').selectOption('missing');await expect(page.locator('#log-table')).toContainText('Worker 001');
 await page.locator('#clear-filters').click();await expect(page.locator('#log-more-panel')).toBeHidden();await expect(page.locator('#row-count')).toContainText('3 matching records');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();await page.screenshot({path:info.outputPath('sic-log.png'),fullPage:true,animations:'disabled'});
});
test('card autofill suggests explicit designation and preserves uncertain or conflicting roles',async({page})=>{
 await cardEntry(page,[CARD.replace('Designation: Welder','Designation: CS Supervisor')]);await page.locator('#entry-files').setInputFiles(fakeCard('role.pdf'));await expect(page.locator('#read-status')).toContainText('reading complete');await expect(page.locator('#designation')).toHaveValue('CS Supervisor');
});
test('actual PDF and Excel downloads include designation and preserve export scope',async({page},info)=>{
 test.skip(!process.env.SIC_EXPORT_SMOKE,'Explicit network export smoke test');test.setTimeout(120000);
 const {records}=await boot(page,'admin',123);records.forEach((r,i)=>r.designation=i%2?'Traffic Controller & Banksman':'Lorry Crane Operator');records[0].designation='=1+1';await page.locator('#refresh').click();await page.getByRole('button',{name:'SIC Log',exact:true}).click();
 await page.locator('#search').fill('Worker 123');await page.locator('#export-menu').evaluate(el=>el.open=true);await page.locator('#export-scope').selectOption('all');let download=page.waitForEvent('download');await exportAction(page,'pdf');await (await download).saveAs(info.outputPath('sic-designation.pdf'));
 download=page.waitForEvent('download');await exportAction(page,'excel');await (await download).saveAs(info.outputPath('sic-designation.xlsx'));
 await page.locator('#search').fill('Worker 002');await page.locator('#export-menu').evaluate(el=>el.open=true);await page.locator('#export-scope').selectOption('filtered');download=page.waitForEvent('download');await exportAction(page,'pdf');await (await download).saveAs(info.outputPath('sic-designation-filtered.pdf'));download=page.waitForEvent('download');await exportAction(page,'excel');await (await download).saveAs(info.outputPath('sic-designation-filtered.xlsx'));
});
