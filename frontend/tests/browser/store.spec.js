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
