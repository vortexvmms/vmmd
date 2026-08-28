const { test, expect } = require('@playwright/test');

async function signedIn(page, role = 'site_sup') {
  await page.addInitScript(() => localStorage.setItem('vmms_session', JSON.stringify({
    access_token: 'test-token', refresh_token: 'test-refresh', expires_at: Date.now() + 3600000
  })));
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/me', r => r.fulfill({ json: {
    name: role === 'admin' ? 'Test Administrator' : 'Test Supervisor', role, user_id: 'u1', menu: null
  }}));
}

test('login has no horizontal overflow', async ({ page }) => {
  await page.goto('/login.html');
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
});

test('shared UI presents consistent connection errors', async ({ page }) => {
  await signedIn(page);
  await page.goto('/home.html');
  const result = await page.evaluate(async () => {
    window.vmmsApi = async () => { throw new TypeError('Failed to fetch'); };
    try { await window.VCMS_UI.requestJSON('/api/v1/test'); } catch (_) {}
    return document.querySelector('#vcms-toast')?.textContent;
  });
  expect(result).toContain('Could not connect');
});

test('attendance header remains aligned without horizontal overflow', async ({ page }) => {
  await signedIn(page);
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/sites*', r => r.fulfill({ json: [{ id:'s1', site_name:'LOGISTICS' }] }));
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/attendance*', r => r.fulfill({ json: { allocations: [], summary: {} } }));
  await page.goto('/attendance.html');
  await expect(page.locator('h1')).toContainText('Attendance');
  const controls = page.locator('header input#date, header select#site');
  await expect(controls).toHaveCount(2);
  const heights = await controls.evaluateAll(nodes => nodes.map(n => Math.round(n.getBoundingClientRect().height)));
  expect(Math.abs(heights[0] - heights[1])).toBeLessThanOrEqual(2);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
});

test('retired worker-card pages are not published', async ({ request }) => {
  for (const path of ['/cards.html', '/worker-cards.html', '/training-matrix.html']) {
    expect((await request.get(path)).status()).toBe(404);
  }
});

test('appearance variables apply without changing semantic safety colours', async ({ page }) => {
  await page.goto('/login.html');
  const values = await page.evaluate(() => {
    VCMS_APPEARANCE.setBrand({ preset: 'blue', primary: '#1565C0' });
    const style = getComputedStyle(document.documentElement);
    return {
      brand: style.getPropertyValue('--vcms-brand').trim(),
      danger: style.getPropertyValue('--vcms-danger').trim(),
      mode: document.documentElement.getAttribute('data-theme')
    };
  });
  expect(values.brand).toBe('#1565C0');
  expect(values.danger).toBe('#B91C1C');
  expect(['light','dark','contrast']).toContain(values.mode);
});

test('management pages receive the shared desktop system', async ({ page }) => {
  await signedIn(page);
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/workers*', r => r.fulfill({ json: [] }));
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/allocations*', r => r.fulfill({ json: [] }));
  await page.goto('/workers.html');
  await expect(page.locator('body')).toHaveClass(/vcms-standard-page/);
  await expect(page.locator('body > header.vcms-legacy-header')).toHaveCount(1);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
});

test('Home and management pages use the same visible desktop shell', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Desktop shell only');
  await signedIn(page);
  const empty = route => route.fulfill({ json: [] });
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/workers*', empty);
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/allocations*', empty);
  await page.goto('/workers.html');
  await expect(page.locator('#vcms-app-header')).toBeVisible();
  await expect(page.locator('#vcms-app-rail')).toBeVisible();
  await expect(page.locator('#vcms-greeting')).toContainText(/Good/);
  await expect(page.locator('#vcms-user-name')).toHaveText('Test Supervisor');
  await expect(page.locator('#vcms-role-chip')).toHaveText('Site Supervisor');
  await page.locator('#vcms-rail-toggle').click();
  await expect(page.locator('body')).toHaveClass(/vcms-rail-mini/);
  await expect.poll(() => page.locator('#vcms-app-rail').evaluate(el => Math.round(el.getBoundingClientRect().width))).toBe(72);

  await page.goto('/home.html');
  await expect(page.locator('#vcms-app-header')).toBeVisible();
  await expect(page.locator('#vcms-app-rail')).toBeVisible();
  await expect(page.locator('body > header.brand')).toBeHidden();
  await expect(page.locator('body > .layout > aside.side')).toBeHidden();
  await expect(page.locator('#vcms-app-header:visible')).toHaveCount(1);
});

test('shared desktop shell is not added to supervisor phone pages', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-safari', 'Phone workflow only');
  await signedIn(page);
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/sites*', r => r.fulfill({ json: [{ id:'s1', site_name:'LOGISTICS' }] }));
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/attendance*', r => r.fulfill({ json: { allocations: [], summary: {} } }));
  await page.goto('/attendance.html');
  await expect(page.locator('#vcms-app-header')).toHaveCount(0);
  await expect(page.locator('#vcms-app-rail')).toHaveCount(0);
  await expect(page.locator('body > header')).toBeVisible();
});

test('DPR readiness uses a dedicated desktop column without covering the form', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Desktop layout only');
  await signedIn(page, 'admin');
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/sites*', r => r.fulfill({ json: [{ id:'s1', site_name:'LOGISTICS' }] }));
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/workers*', r => r.fulfill({ json: [] }));
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/dpr/projects*', r => r.fulfill({ json: [] }));
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/dpr/reminders*', r => r.fulfill({ json: [] }));
  await page.route(/https:\/\/vmms-backend-sg\.onrender\.com\/api\/v1\/dpr\?.*/, r => r.fulfill({ json: {} }));
  await page.goto('/dpr.html');
  await expect(page.locator('#dpr-progress')).toBeVisible();
  const boxes = await page.evaluate(() => {
    const content = document.getElementById('dpr-content').getBoundingClientRect();
    const progress = document.getElementById('dpr-progress').getBoundingClientRect();
    return { contentRight: content.right, progressLeft: progress.left };
  });
  expect(boxes.progressLeft).toBeGreaterThanOrEqual(boxes.contentRight + 12);
});

test('Resource Summary desktop controls are compact and aligned', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Desktop layout only');
  await signedIn(page, 'admin');
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/sites*', r => r.fulfill({ json: [{ id:'s1', site_name:'LOGISTICS' }] }));
  await page.goto('/resource-summary.html');
  const metrics = await page.evaluate(() => {
    const site = document.getElementById('f-site').getBoundingClientRect();
    const month = document.getElementById('f-month').getBoundingClientRect();
    const load = document.querySelector('.rs-filter-grid > button').getBoundingClientRect();
    const print = document.getElementById('b-print').getBoundingClientRect();
    return { siteTop:site.top, monthTop:month.top, loadTop:load.top, loadWidth:load.width, printWidth:print.width };
  });
  expect(Math.abs(metrics.siteTop - metrics.monthTop)).toBeLessThanOrEqual(2);
  expect(Math.abs(metrics.siteTop - metrics.loadTop)).toBeLessThanOrEqual(30);
  expect(metrics.loadWidth).toBeLessThanOrEqual(180);
  expect(metrics.printWidth).toBeLessThanOrEqual(200);
});

test('Site Board loads selected-site DPRs and searches the report table', async ({ page }) => {
  await signedIn(page, 'admin');
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/sites*', r => r.fulfill({ json: [{ id:'s1', site_name:'LOGISTICS' }] }));
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/site-progress*', r => r.fulfill({ json:{
    today:'2026-08-28', site_id:'s1', partial:false,
    summary:{ reports:2, reported_days:2, latest_manpower:7, photos:1 },
    trend:[{ date:'2026-08-27', manpower:6 },{ date:'2026-08-28', manpower:7 }],
    reports:[
      { id:'d1',date:'2026-08-28',location:'DTSS2-T08',item_of_work:'Tunnel repair',description:'Grouting at shaft wall',prepared_by:'Rajesh',manpower:7,photo_count:1,photo:{url:'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==',caption:'Grouting'} },
      { id:'d2',date:'2026-08-27',location:'Store',item_of_work:'Delivery',description:'Material unloading',prepared_by:'Prakash',manpower:6,photo_count:0,photo:null }
    ]
  }}));
  await page.goto('/site-dashboard.html');
  await page.locator('#f-site').selectOption('s1');
  await expect(page.locator('#k-reports')).toHaveText('2');
  await expect(page.locator('#report-rows tr')).toHaveCount(2);
  await page.locator('#search').fill('grouting');
  await expect(page.locator('#report-rows tr')).toHaveCount(1);
  await expect(page.locator('#report-rows')).toContainText('DTSS2-T08');
  await expect(page.locator('#report-rows .sb-photo')).toHaveCount(1);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
});

test('all visible form controls have an accessible name', async ({ page }) => {
  await page.goto('/login.html');
  const unnamed = await page.locator('input:visible,select:visible,textarea:visible').evaluateAll(nodes =>
    nodes.filter(n => {
      const id = n.getAttribute('id');
      const explicitLabel = id && document.querySelector(`label[for="${CSS.escape(id)}"]`);
      return !n.getAttribute('aria-label') &&
        !n.getAttribute('aria-labelledby') &&
        !n.closest('label') &&
        !explicitLabel;
    }).length);
  expect(unnamed).toBe(0);
});
