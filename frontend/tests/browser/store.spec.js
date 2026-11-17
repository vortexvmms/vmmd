const {test,expect} = require('@playwright/test');

test('Store stays responsive while moving equipment and reviewing site stock', async ({page})=>{
  await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({
    access_token:'test',refresh_token:'test',expires_at:Date.now()+3600000,
  })));
  const received=[];
  const item={id:'40000000-0000-0000-0000-000000000001',code:'TEST-1',name:'Equipment for layout verification',
    category:'Tool',site_id:null,location:'Main Store',quantity:3,condition:'Good'};
  await page.route('**/api/v1/store/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/register')) return route.fulfill({json:{stock:[item],can_move:true,can_manage_drivers:true,
      locations:[{id:'30000000-0000-0000-0000-000000000001',name:'Test site'}],
      supervisors:[{id:'10000000-0000-0000-0000-000000000001',name:'Test supervisor'}],drivers:[],reminders:[],photos_enabled:true}});
    if(path.endsWith('/movements') && route.request().method()==='POST'){
      received.push(route.request().postDataJSON());
      item.quantity=2;
      return route.fulfill({status:201,json:{id:received.at(-1).id}});
    }
    if(path.endsWith('/photos')) return route.fulfill({json:[]});
    return route.fulfill({json:{rows:[],has_more:false}});
  });
  await page.goto('/store.html');
  await expect(page.locator('#add-asset')).toBeEnabled();
  await expect(page.getByRole('heading',{name:'Equipment Store',exact:true})).toHaveCSS('color','rgb(255, 255, 255)');
  const toolbarButtons = await page.locator('.store-hero button').evaluateAll(buttons =>
    buttons.map(button => {
      const {top,right}=button.getBoundingClientRect();
      return {top,right};
    })
  );
  expect(toolbarButtons).toHaveLength(4);
  expect(new Set(toolbarButtons.map(button => Math.round(button.top))).size).toBe(1);
  expect(toolbarButtons.at(-1).right).toBeLessThanOrEqual(await page.evaluate(()=>window.innerWidth));
  const fits=()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth);
  expect(await fits()).toBe(true);
  await page.getByRole('button',{name:'Equipment Register',exact:true}).click();
  expect(await fits()).toBe(true);
  await page.getByRole('button',{name:'Move',exact:true}).click();
  await page.getByLabel('Move to').selectOption({label:'Test site'});
  await page.getByLabel('Received by').selectOption({label:'Test supervisor'});
  await page.locator('#move-form input[name=quantity]').fill('1');
  await page.getByRole('button',{name:'Record movement',exact:true}).click();
  const photo=page.getByRole('dialog',{name:'Record photos'});
  await expect(photo).toBeVisible();
  await expect(photo.getByRole('button',{name:'Camera',exact:true})).toBeVisible();
  await expect(photo.getByRole('button',{name:'Files',exact:true})).toBeVisible();
  await expect(photo.getByRole('button',{name:'Paste photo',exact:true})).toBeVisible();
  expect(received).toHaveLength(1);
  expect(received[0].quantity).toBe(1);
  expect(received[0].from_site).toBeNull();
  expect(await fits()).toBe(true);
  await photo.getByRole('button',{name:'Close',exact:true}).click();
  await page.getByRole('button',{name:'Movement Log',exact:true}).click();
  await expect(page.locator('#movement-count')).toContainText('No movements');
  expect(await fits()).toBe(true);
});

test('Add equipment stages photos, saves a manual code and can archive the record', async ({page})=>{
  await page.addInitScript(()=>localStorage.setItem('vmms_session',JSON.stringify({
    access_token:'test',refresh_token:'test',expires_at:Date.now()+3600000,
  })));
  const site={id:'30000000-0000-0000-0000-000000000002',name:'Test site'};
  const stock=[], created=[], photos=[];
  await page.route('**/api/v1/store/**',async route=>{
    const request=route.request(), url=new URL(request.url()), path=url.pathname;
    if(path.endsWith('/register')) return route.fulfill({json:{stock,can_move:true,can_archive:true,
      locations:[site],supervisors:[],drivers:[],reminders:[],photos_enabled:true}});
    if(path.endsWith('/assets') && request.method()==='POST'){
      const record=request.postDataJSON();
      created.push(record);
      stock.push({...record.asset,id:record.id,site_id:record.site,location:site.name,quantity:record.quantity});
      return route.fulfill({status:201,json:{id:record.id}});
    }
    if(path.endsWith('/archive')){
      const [record]=stock.splice(0);
      return route.fulfill({json:{id:record.id}});
    }
    if(path.endsWith('/photos')) return route.fulfill({json:photos.map(({id})=>({id}))});
    if(path.includes('/photos/')){
      const id=path.split('/').at(-1);
      if(request.method()==='PUT'){
        expect(url.searchParams.get('asset')).toBe(created[0].id);
        photos.push({id,body:request.postDataBuffer()});
        return route.fulfill({status:201,json:{id}});
      }
      return route.fulfill({contentType:'image/jpeg',body:photos.find(photo=>photo.id===id).body});
    }
    return route.fulfill({json:{rows:[],has_more:false}});
  });
  await page.goto('/store.html');
  await page.getByRole('button',{name:'Add equipment',exact:true}).click();
  const form=page.getByRole('dialog',{name:'Add equipment'});
  await expect(form.getByRole('button',{name:'Camera'})).toBeVisible();
  await expect(form.getByRole('button',{name:'Upload files'})).toBeVisible();
  await expect(form.getByRole('button',{name:'Paste photo'})).toBeVisible();
  await expect(form.getByLabel('Asset code')).toHaveValue('');
  await form.getByLabel('Asset code').fill('EQ-MANUAL-1');
  await form.getByLabel('Description').fill('Test loader');
  await form.getByLabel('Current Store / Site').selectOption({label:'Main Store'});
  await form.getByLabel('Current Store / Site').selectOption({label:site.name});
  await form.getByLabel('Ownership').selectOption({label:'Rental'});
  await form.getByText('Specifications, service dates & remarks').click();
  await form.getByLabel('Last maintenance / repair').fill('2026-11-10');
  const png=await page.evaluate(()=>document.createElement('canvas').toDataURL('image/png').split(',')[1]);
  await form.locator('[data-file-input]').setInputFiles({name:'equipment.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});
  await expect(form.getByRole('img',{name:'equipment.png',exact:true})).toBeVisible();
  expect(photos).toHaveLength(0);
  await form.getByRole('button',{name:'Save equipment'}).click();
  await expect(form).toBeHidden();
  expect(created).toHaveLength(1);
  expect(created[0]).toMatchObject({site:site.id,asset:{code:'EQ-MANUAL-1',ownership:'Rental',last_maintenance:'2026-11-10',last_repair:null}});
  expect(photos).toHaveLength(1);
  await page.getByRole('button',{name:'Equipment Register',exact:true}).click();
  await page.getByRole('button',{name:'Photos',exact:true}).click();
  const gallery=page.getByRole('dialog',{name:'Record photos'});
  await expect(gallery.getByRole('img',{name:'Equipment or handover photo'})).toBeVisible();
  await gallery.getByRole('button',{name:'Close'}).click();
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'Archive',exact:true}).click();
  await expect(page.getByText('EQ-MANUAL-1 archived.')).toBeVisible();
  await expect(page.locator('#stock-count')).toHaveText('No matching equipment.');
});
