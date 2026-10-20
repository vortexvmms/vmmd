const {test, expect} = require('@playwright/test');

async function fixture(page, {unmarked = false} = {}) {
  const rows = Array.from({length:24}, (_, i) => ({
    allocation_id:'a'+i, site_id:'s1', site_name:'PCS-M&P',
    worker_name:'Sample Worker '+(i+1), worker_code:'EMP-'+i,
    marked:!unmarked, present:!unmarked&&i<22, start_time:'08:00',
    end_time:null, normal_hours:0, ot_hours:0, submitted:false,
    shift_type:'day', absence_type:i<22?'absent':'al',
  }));
  const writes = [];
  await page.addInitScript(() => localStorage.setItem('vmms_session', JSON.stringify({
    access_token:'test', expires_at:Date.now()+3600000,
  })));
  await page.route('**/api/v1/**', async route => {
    const req=route.request(), path=new URL(req.url()).pathname;
    if (path.endsWith('/me')) return route.fulfill({json:{role:'admin', name:'Test Administrator', user_id:'u1'}});
    if (path.endsWith('/sites')) return route.fulfill({json:[{id:'s1', site_name:'PCS-M&P', status:'active'}]});
    if (path.endsWith('/attendance/bulk_end')) {
      const payload=req.postDataJSON(); writes.push(payload);
      rows.filter(row=>payload.allocation_ids.includes(row.allocation_id))
        .forEach(row=>Object.assign(row,{end_time:payload.end_time,end_next_day:payload.end_next_day}));
      return route.fulfill({json:{ok:true, updated:payload.allocation_ids.length}});
    }
    if (path.endsWith('/attendance')) return route.fulfill({json:rows});
    return route.fulfill({json:[]});
  });
  await page.goto('/attendance.html?date=2026-10-20&site_id=s1');
  await expect(page.locator('.worker-card').first()).toBeVisible();
  return {rows,writes};
}

test('wide desktop uses one top row and one bottom row with full-width cards', async ({page,isMobile}) => {
  test.skip(isMobile, 'Desktop workspace only');
  await page.setViewportSize({width:1663,height:900});
  await fixture(page);
  await expect(page.locator('#att-kpis')).toBeVisible();
  const layout=await page.evaluate(()=>{
    const box=s=>document.querySelector(s).getBoundingClientRect();
    const footer=box('#att-actions');
    return {
      firstCardTop:box('.worker-card').top,
      footerHeight:footer.height,
      visibleCards:[...document.querySelectorAll('.worker-card')].filter(n=>n.getBoundingClientRect().bottom<=footer.top).length,
      headerCenters:['#date','#site','#att-kpis'].map(s=>box(s).top+box(s).height/2),
      footerCenters:['.att-action-status','#bulkbar','.att-submit-actions'].map(s=>box(s).top+box(s).height/2),
    };
  });
  expect(layout.firstCardTop).toBeLessThan(280);
  expect(layout.footerHeight).toBeLessThan(80);
  expect(layout.visibleCards).toBeGreaterThanOrEqual(12);
  expect(Math.max(...layout.headerCenters)-Math.min(...layout.headerCenters)).toBeLessThan(3);
  expect(Math.max(...layout.footerCenters)-Math.min(...layout.footerCenters)).toBeLessThan(3);
});

test('desktop controls fit narrower screens and the last worker remains reachable', async ({page,isMobile}) => {
  test.skip(isMobile, 'Desktop workspace only');
  await fixture(page, {unmarked:true});
  for (const width of [900,1024,1280,1366,1920]) {
    await page.setViewportSize({width,height:900});
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
    const controls=page.locator('#date,#site,#morningbar button,#bulk-time,#morning-btn,#submit-btn');
    for (const control of await controls.all()) {
      const bounds=await control.boundingBox();
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x+bounds.width).toBeLessThanOrEqual(width+1);
    }
  }
  await page.locator('#addbtn').scrollIntoViewIfNeeded();
  const gap=await page.evaluate(()=>document.getElementById('att-actions').getBoundingClientRect().top-document.getElementById('addbtn').getBoundingClientRect().bottom);
  expect(gap).toBeGreaterThanOrEqual(8);
});

test('footer bulk, group and custom times keep their existing date/site scope', async ({page,isMobile}) => {
  test.skip(isMobile, 'Desktop footer only');
  const {writes}=await fixture(page);
  await page.locator('#bulkbar').getByRole('button',{name:'5 PM',exact:true}).click();
  await expect.poll(()=>writes.length).toBe(1);
  expect(writes[0]).toMatchObject({work_date:'2026-10-20',site_id:'s1',end_time:'17:00'});
  expect(writes[0].allocation_ids).toHaveLength(22);
  await page.locator('#att-bulk-options summary').click();
  await page.getByRole('button',{name:'Select all present',exact:true}).click();
  await expect(page.locator('#groupbar')).toBeVisible();
  await expect(page.locator('#bulkbar')).toBeHidden();
  await expect(page.locator('#groupcount')).toHaveText('22');
  await page.locator('#gcustom').click();
  await page.locator('#group-time').fill('18:30');
  await page.locator('#group-time').dispatchEvent('change');
  await expect.poll(()=>writes.length).toBe(2);
  expect(writes[1]).toMatchObject({work_date:'2026-10-20',site_id:'s1',end_time:'18:30'});
  expect(writes[1].allocation_ids).toHaveLength(22);
});

test('resizing restores phone controls without duplication or losing selected workers', async ({page,isMobile}) => {
  test.skip(isMobile, 'Resize from a desktop session');
  await fixture(page);
  await page.locator('.sel-cb').first().check();
  await expect(page.locator('#groupcount')).toHaveText('1');
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('body')).not.toHaveClass(/att-compact-desktop/);
  await expect(page.locator('.att-tools>#bulkbar')).toHaveCount(1);
  await expect(page.locator('body>#groupbar')).toHaveCount(1);
  await expect(page.locator('header>.vcms-page-toolbar')).toHaveCount(1);
  await expect(page.locator('#groupcount')).toHaveText('1');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.setViewportSize({width:1663,height:900});
  await expect(page.locator('#att-footer-tools>#groupbar')).toHaveCount(1);
  await expect(page.locator('#groupcount')).toHaveText('1');
  for (const id of ['date','site','bulkbar','bulk-time','groupbar','att-kpis']) {
    await expect(page.locator('#'+id)).toHaveCount(1);
  }
});

test('phone keeps the original tool order and desktop options stay hidden', async ({page,isMobile}) => {
  test.skip(!isMobile, 'Phone layout only');
  await fixture(page);
  await expect(page.locator('.att-tools>#bulkbar')).toBeVisible();
  await expect(page.locator('#att-footer-tools')).toBeHidden();
  await expect(page.locator('#att-kpis')).toBeHidden();
  await expect(page.locator('header>.vcms-page-toolbar')).toHaveCount(1);
  await expect(page.locator('#att-bulk-options')).toHaveCount(0);
});
