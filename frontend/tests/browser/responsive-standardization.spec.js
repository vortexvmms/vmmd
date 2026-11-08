const { test, expect } = require('@playwright/test');

// Responsive smoke tests for shared VCMS components. Authentication is mocked;
// no production records or Supabase data are modified.
async function signedIn(page) {
  await page.addInitScript(() => localStorage.setItem('vmms_session', JSON.stringify({
    access_token: 'test-token', refresh_token: 'test-refresh', expires_at: Date.now() + 3600000
  })));
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/me', r => r.fulfill({ json: {
    name: 'Test Supervisor', role: 'admin', user_id: 'u1', menu: null
  }}));
}

test('shared header has readable title and touch-friendly back navigation', async ({ page }) => {
  await signedIn(page);
  await page.goto('/whatsapp.html');
  await expect(page.locator('.vcms-page-header__title h1')).toBeVisible();
  const metrics = await page.evaluate(() => {
    const h = document.querySelector('.vcms-page-header__title h1');
    const back = document.querySelector('.vcms-page-header__back');
    const css = getComputedStyle(h);
    return { color: css.color, height: back.getBoundingClientRect().height, width: back.getBoundingClientRect().width,
      overflow: document.documentElement.scrollWidth > innerWidth + 1 };
  });
  expect(metrics.color).toBe('rgb(255, 255, 255)');
  expect(metrics.height).toBeGreaterThanOrEqual(44);
  expect(metrics.width).toBeGreaterThanOrEqual(44);
  expect(metrics.overflow).toBeFalsy();
});

test('floating Home button never covers a shared mobile action bar', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-safari', 'Mobile overlap only');
  await signedIn(page);
  await page.goto('/allocation.html');
  await expect(page.locator('.vcms-mobile-actions')).toHaveCount(1);
  await expect(page.locator('#vmms-home-fab')).toHaveCount(0);
});

test('desktop shared header keeps title and page actions inside viewport', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Desktop layout only');
  await signedIn(page);
  await page.goto('/whatsapp.html');
  const bounds = await page.evaluate(() => {
    const header = document.querySelector('.vcms-page-header');
    const r = header.getBoundingClientRect();
    return { left:r.left,right:r.right,width:innerWidth };
  });
  expect(bounds.left).toBeGreaterThanOrEqual(0);
  expect(bounds.right).toBeLessThanOrEqual(bounds.width+1);
});

test('end-time verification exports and filters fit mobile viewport', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-safari', 'Mobile viewport only');
  await signedIn(page);
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/sites*', r => r.fulfill({ json: [] }));
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/attendance*', r => r.fulfill({ json: [] }));
  await page.goto('/verify.html');
  const layout = await page.evaluate(() => {
    const header = document.querySelector('header.no-print');
    const actions = [...header.querySelectorAll('.verify-export-actions button')];
    const inputs = [...header.querySelectorAll('#date,#site,#search')];
    return { viewport: innerWidth, headerRight: header.getBoundingClientRect().right,
      controls: [...actions,...inputs].map(e => ({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right,height:e.getBoundingClientRect().height})),
      tableScroll: getComputedStyle(document.querySelector('main .sheet')).overflowX };
  });
  expect(layout.headerRight).toBeLessThanOrEqual(layout.viewport+1);
  for (const c of layout.controls) {
    expect(c.left).toBeGreaterThanOrEqual(-1);
    expect(c.right).toBeLessThanOrEqual(layout.viewport+1);
    expect(c.height).toBeGreaterThanOrEqual(40);
  }
  expect(layout.tableScroll).toBe('auto');
});
