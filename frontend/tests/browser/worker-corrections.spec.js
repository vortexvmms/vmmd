const {test, expect} = require('@playwright/test');

async function fixture(page, role = 'admin') {
  const state = {row: {id: 'worker-1', worker_code: 'OLD01', name: 'Original Name', status: 'active'}, writes: []};
  await page.addInitScript(() => {
    localStorage.setItem('vmms_session', JSON.stringify({access_token: 'test', expires_at: Date.now() + 3600000}));
    localStorage.setItem('vmms_ref_cache', JSON.stringify({'/api/v1/workers': {
      t: Date.now(), b: JSON.stringify([{id: 'worker-1', worker_code: 'STALE', name: 'Stale Name', status: 'active'}])
    }}));
  });
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith('/me')) return route.fulfill({json: {role, name: 'Test User', user_id: 'user-1'}});
    if (request.method() === 'PATCH') {
      expect(path).toBe('/api/v1/workers/worker-1');
      const body = request.postDataJSON();
      state.writes.push(body);
      if (body.worker_code === 'TAKEN') return route.fulfill({status: 409, json: {detail: 'Worker ID TAKEN already exists'}});
      Object.assign(state.row, body);
      return route.fulfill({json: state.row});
    }
    if (path.endsWith('/workers')) return route.fulfill({json: [state.row]});
    return route.fulfill({json: []});
  });
  await page.goto('/workers.html');
  await expect(page.locator('#count')).toContainText('1 shown');
  return state;
}

async function openEditor(page, isMobile) {
  if (isMobile) await page.locator('#list > div').first().click();
  else await page.getByRole('button', {name: 'Edit', exact: true}).click();
  await expect(page.locator('#modal')).toBeVisible();
}

test('correct worker ID and name; current values survive a reload despite cached data', async ({page, isMobile}) => {
  const state = await fixture(page);
  await openEditor(page, isMobile);
  await expect(page.locator('#m-code')).toBeEnabled();
  await expect(page.locator('#m-code')).toHaveValue('OLD01');
  await expect(page.locator('#m-name')).toBeEnabled();
  await page.locator('#m-code').fill(' emp-050 ');
  await page.locator('#m-name').fill(' Corrected Name ');
  await page.locator('#m-save').click();
  await expect(page.locator('#modal')).toBeHidden();
  expect(state.writes).toEqual([{worker_code: 'EMP-050', name: 'Corrected Name', status: 'active'}]);
  await page.reload();
  await expect(page.locator('#count')).toContainText('1 shown');
  await openEditor(page, isMobile);
  await expect(page.locator('#m-code')).toHaveValue('EMP-050');
  await expect(page.locator('#m-name')).toHaveValue('Corrected Name');
});

test('duplicate ID keeps the dialog open and preserves the saved worker', async ({page, isMobile}) => {
  const state = await fixture(page);
  await openEditor(page, isMobile);
  await page.locator('#m-code').fill('TAKEN');
  await page.locator('#m-save').click();
  await expect(page.locator('#m-error')).toHaveText('Worker ID TAKEN already exists');
  await expect(page.locator('#modal')).toBeVisible();
  await expect(page.locator('#m-save')).toBeEnabled();
  expect(state.row.worker_code).toBe('OLD01');
});

test('blank ID or name cannot be saved', async ({page, isMobile}) => {
  const state = await fixture(page);
  await openEditor(page, isMobile);
  for (const field of ['#m-code', '#m-name']) {
    await page.locator(field).fill('   ');
    await page.locator('#m-save').click();
    await expect(page.locator('#m-error')).toHaveText('Worker ID and name are required');
    expect(state.writes).toHaveLength(0);
    await page.locator(field).fill('Restored');
  }
});

test('supervisors see workers without editing controls', async ({page, isMobile}) => {
  await fixture(page, 'site_sup');
  await expect(page.getByRole('button', {name: 'Edit', exact: true})).toHaveCount(0);
  if (isMobile) await page.locator('#list > div').first().click();
  await expect(page.locator('#modal')).toBeHidden();
});
