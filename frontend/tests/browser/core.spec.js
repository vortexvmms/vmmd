const { test, expect } = require('@playwright/test');

async function signedIn(page) {
  await page.addInitScript(() => localStorage.setItem('vmms_session', JSON.stringify({
    access_token: 'test-token', refresh_token: 'test-refresh', expires_at: Date.now() + 3600000
  })));
  await page.route('https://vmms-backend-sg.onrender.com/api/v1/me', r => r.fulfill({ json: {
    name: 'Test Supervisor', role: 'site_sup', user_id: 'u1', menu: null
  }}));
}

test('login has no horizontal overflow', async ({ page }) => {
  await page.goto('/login.html');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
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
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
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
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
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
