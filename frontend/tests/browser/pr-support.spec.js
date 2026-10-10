const { test, expect } = require('@playwright/test');
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAGQAAAAeCAIAAABVOSykAAABTUlEQVR4nO1Z2w5CIQwD4///Mj6cSAiYXbshCX0wMcazWruVS22tlQsZXrsJnIQrlgJXLAWuWApEiVW/CHo+Ube/whEiVr5GY904vSp26TBSbK09bxNWJ73uU2uigaqCdNbI+KGYs4iblBoJFKjFYGKtjNeP4OhjcVSnA64XQKxxkBOM4SCKrtUhaeOdWRLG8MklKer/ygqXs4QMgjJE9VhISxqdpY0biLn87nCmpMVZa+qx8JsL0kfOlFSL5SFtawE68gww66UQi049Fs5+xw4+W0pKZxaEtGpyBcnkqSJyFop3ctJLoGpJxlnwTRZrrjSZfhal61LOMqQeC+F/k3wzIExJSqy4zfBKCB55BrC/l5lZEbyJnfb2qyaawDuNx4Raaz/wKn8gkwR7zuCnI7ojlCq7nHWcTA92OusspcrGq7DjlCr33lCFK5YCH45rAiDj+/z6AAAAAElFTkSuQmCC', 'base64');
const entry = { id:'40000000-0000-0000-0000-000000000001', site_name:'PCS', project_code:'PCS', project:'PCS project', pm_hod:'Teo Zheng Liang', manager_director:'Ramasamy Ramesh Kumar' };

async function setup(page, role='admin') {
  await page.addInitScript(() => localStorage.setItem('vmms_session', JSON.stringify({access_token:'test-token',refresh_token:'test-refresh',expires_at:Date.now()+3600000})));
  await page.route('**/api/v1/me', r => r.fulfill({json:{name:'Test Requester',role,user_id:'u1',menu:null}}));
  await page.route('**/api/v1/pr/directory', r => r.fulfill({json:[entry]}));
  await page.route('**/api/v1/pr/list', r => r.fulfill({json:[]}));
  await page.route('**/api/v1/pr/next-number?*', r => r.fulfill({json:{next:'PCS-0242'}}));
  await page.context().route('https://www.vortex.sg/images/Vortex-Logo_Type.png', r=>r.fulfill({contentType:'image/png',body:PNG}));
  // Keep print dialogs from blocking tests; preserve the real preview window.
  await page.addInitScript(() => {
    const open = window.open.bind(window);
    window.open = (...args) => { const preview=open(...args); if(preview)preview.print=()=>{preview.printCalls=(preview.printCalls||0)+1;}; return preview; };
  });
}

test('directory saves defaults and offers new names without losing the other approver', async ({page}) => {
  await setup(page);
  const changes=[];
  await page.route('**/api/v1/pr/directory/'+entry.id, r => {
    const body=r.request().postDataJSON();changes.push(body);
    return r.fulfill({json:{...entry,...body}});
  });
  await page.goto('/pr-directory.html');
  const pm=page.locator('select[data-field="pm_hod"]');
  const md=page.locator('select[data-field="manager_director"]');
  await expect(pm).toHaveValue(entry.pm_hod);
  await expect(md).toHaveValue(entry.manager_director);
  await pm.selectOption('Ramasamy Ramesh Kumar');
  await expect.poll(()=>changes.length).toBe(1);
  expect(changes[0]).toEqual({pm_hod:'Ramasamy Ramesh Kumar',manager_director:'Ramasamy Ramesh Kumar'});
  page.once('dialog', dialog=>dialog.accept('New Approver'));
  await md.selectOption('__add_pr_name__');
  await expect.poll(()=>changes.length).toBe(2);
  expect(changes[1]).toEqual({pm_hod:'Ramasamy Ramesh Kumar',manager_director:'New Approver'});
  await expect(md).toHaveValue('New Approver');
  page.once('dialog', dialog=>dialog.dismiss());
  await md.selectOption('__add_pr_name__');
  await expect(md).toHaveValue('New Approver');
  expect(changes.length).toBe(2);
});

test('failed default update restores the saved selection', async ({page})=>{
  await setup(page);
  await page.route('**/api/v1/pr/directory/'+entry.id, r=>r.fulfill({status:503,json:{detail:'Unavailable'}}));
  await page.goto('/pr-directory.html');
  const pm=page.locator('select[data-field="pm_hod"]');
  await expect(pm).toHaveValue(entry.pm_hod);
  await pm.selectOption('Ramasamy Ramesh Kumar');
  await expect(pm).toHaveValue(entry.pm_hod);
  await expect(pm).toBeEnabled();
});

test('historical spellings produce only two names and custom additions are unique', async ({page})=>{
  await setup(page);
  await page.route('**/api/v1/pr/directory',r=>r.fulfill({json:[
    {...entry,pm_hod:'Teo Zheng Lian',manager_director:'Ramasamy Rameshkumar'},
    {...entry,id:'another',pm_hod:'Teo Zheng Liang',manager_director:'Ramasamy RameshKumar'},
    {...entry,id:'third',pm_hod:'Ramesh Kumar',manager_director:'Ramasamy Ramesh kumar'}
  ]}));
  await page.goto('/pr-directory.html');
  const select=page.locator('select[data-field="pm_hod"]').first();
  await expect(select).toHaveValue('Teo Zheng Liang');
  expect(await select.locator('option').allTextContents()).toEqual(['Select name…','Ramasamy Ramesh Kumar','Teo Zheng Liang','Add name…']);
  await expect(page.locator('select[data-field="manager_director"]').first()).toHaveValue('Ramasamy Ramesh Kumar');
  await page.evaluate(()=>{VCMS_PR.remember(' New  Approver ');VCMS_PR.remember('new approver');VCMS_PR.refreshChoices();});
  expect(await select.locator('option').allTextContents()).toEqual(['Select name…','Ramasamy Ramesh Kumar','Teo Zheng Liang','New Approver','Add name…']);
  page.once('dialog',d=>d.dismiss());
  await select.selectOption('__add_pr_name__');
  await expect(select).toHaveValue('Teo Zheng Liang');
});

test('PR embeds a delayed signature before printing and includes both default approvers', async ({page}, info)=>{
  await setup(page);
  await page.addInitScript(()=>localStorage.setItem('vcms_my_signature','https://media.example.com/signatures/test.png'));
  let requested=false;
  await page.route('**/api/v1/pr/signature-image?*', async r=>{
    requested=true;await new Promise(resolve=>setTimeout(resolve,700));
    await r.fulfill({contentType:'image/png',body:PNG});
  });
  await page.goto('/pr-new.html');
  await expect(page.locator('#f-site option')).toHaveCount(2);
  await page.locator('#f-site').selectOption('PCS');
  await expect(page.locator('#f-prno')).toHaveValue('PCS-0242');
  const popupEvent=page.waitForEvent('popup');
  await page.getByRole('button',{name:'Print / PDF',exact:true}).click();
  const popup=await popupEvent;
  await expect.poll(()=>requested).toBeTruthy();
  await expect(popup.locator('body')).toContainText('Preparing PR');
  await popup.locator('.logo').evaluate((image,src)=>image.src=src,'data:image/png;base64,'+PNG.toString('base64'));
  await expect(popup.locator('#print-ready')).toBeEnabled();
  const signature=popup.getByAltText('Requester signature');
  await expect(signature).toHaveAttribute('src',/^data:image\/png;base64,/);
  expect(await signature.evaluate(img=>img.complete&&img.naturalWidth>0)).toBeTruthy();
  await expect(popup.locator('.foot')).toContainText(entry.pm_hod);
  await expect(popup.locator('.foot')).toContainText(entry.manager_director);
  await expect.poll(()=>popup.evaluate(()=>window.printCalls)).toBe(1);
  if(info.project.name==='desktop-chromium'){
    await popup.pdf({path:info.outputPath('pr-signature.pdf'),format:'A4',landscape:true});
    await popup.screenshot({path:info.outputPath('pr-preview.png'),fullPage:true});
  }
});

test('missing remote signature stops printing with a replacement instruction', async ({page})=>{
  await setup(page);
  await page.addInitScript(()=>localStorage.setItem('vcms_my_signature','https://media.example.com/signatures/missing.png'));
  await page.route('**/api/v1/pr/signature-image?*', r=>r.fulfill({status:422,json:{detail:'Unavailable'}}));
  await page.goto('/pr-new.html');
  await expect(page.locator('#f-site option')).toHaveCount(2);
  const popupEvent=page.waitForEvent('popup');
  await page.getByRole('button',{name:'Print / PDF',exact:true}).click();
  const popup=await popupEvent;
  await expect(popup.locator('body')).toContainText('Upload your signature again before printing');
  expect(await popup.evaluate(()=>window.printCalls||0)).toBe(0);
});

test('replacement signature is stored as a self-contained image', async ({page})=>{
  await setup(page);
  await page.goto('/pr-new.html');
  await page.locator('#pr-signature-file').setInputFiles({name:'signature.png',mimeType:'image/png',buffer:PNG});
  await expect.poll(()=>page.evaluate(()=>localStorage.getItem('vcms_my_signature'))).toMatch(/^data:image\/png;base64,/);
});
