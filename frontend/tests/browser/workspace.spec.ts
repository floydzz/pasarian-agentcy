import { expect, test, type Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/dashboard')
  await page.getByLabel('Email', { exact: true }).fill('browser@example.test')
  await page.getByLabel('Password', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible()
}

test('protected pages, navigation, calendar and interrupted panels stay usable', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await login(page)
  const readiness = await page.request.get('/api/ready')
  expect(readiness.headers()['content-type']).toContain('application/json')
  const unknown = await page.request.get('/api/missing-endpoint')
  expect(unknown.status()).toBe(404)
  expect((await unknown.json()).code).toBe('not_found')
  for (const path of ['/chat', '/calendar', '/campaigns', '/trends', '/progress', '/publish', '/brand', '/agents', '/account', '/dashboard']) {
    await page.goto(path)
    await expect(page.locator('#main-content')).toBeVisible()
    await expect(page.getByText('Loading workspace…')).toHaveCount(0)
    if (path === '/calendar') await expect(page.locator('.fc')).toBeVisible()
    const sizes = await page.evaluate(() => ({ body: document.documentElement.scrollWidth, viewport: innerWidth, main: document.querySelector('#main-content')?.getBoundingClientRect().width }))
    expect(sizes.body).toBeLessThanOrEqual(sizes.viewport + 1)
    expect(sizes.main).toBeGreaterThan(200)
  }
  if (test.info().project.name !== 'mobile') {
    for (let index = 0; index < 3; index++) {
      await page.getByRole('button', { name: 'Open marketing strategist' }).click()
      const close = page.getByRole('button', { name: /Close marketing chat/ })
      await expect(close).toBeVisible()
      await close.click()
    }
  }
  await page.goto('/account')
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('campaign filters persist and a failed load is not an empty workspace', async ({ page }) => {
  await login(page)
  await page.goto('/campaigns?q=Browser&filter=draft')
  await expect(page.getByRole('searchbox')).toHaveValue('Browser')
  await expect(page.getByText('Browser campaign', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('searchbox')).toHaveValue('Browser')
  await page.route('**/api/campaign-directory?**', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Directory temporarily unavailable', code: 'unavailable', retryable: true }) }))
  await page.goto('/campaigns?q=failed-request')
  await expect(page.getByRole('button', { name: 'Retry loading campaigns' })).toBeVisible()
  await expect(page.getByText('Your campaign directory is empty.')).toHaveCount(0)
  await page.unroute('**/api/campaign-directory?**')
})

test('a saved AI job survives navigation and keeps approval gates', async ({ page }) => {
  await login(page)
  const csrf = (await (await page.request.get('/api/auth/me')).json()).csrf_token
  const created = await page.request.post('/api/campaigns', { headers: { 'X-CSRF-Token': csrf }, data: { name: `Recovery ${test.info().project.name}`, brief: 'Promote the approved Starter bundle to Malaysian shoppers.' } })
  expect(created.status()).toBe(201)
  const campaign = await created.json()
  await page.goto(`/campaigns/${campaign.id}`)
  await page.getByRole('link', { name: 'Plan campaign concepts', exact: true }).click()
  // Leave the console while the worker owns the job; it must still persist.
  await expect.poll(async () => (await (await page.request.get('/api/jobs?limit=30')).json()).some((row: { path: string }) => row.path === `/campaigns/${campaign.id}/plan/stream`)).toBe(true)
  await page.goto('/calendar')
  await expect.poll(async () => (await (await page.request.get(`/api/campaigns/${campaign.id}`)).json()).status, { timeout: 45000 }).toBe('pending_plan_approval')
  await page.goto('/progress')
  await expect(page.getByRole('heading', { name: 'Saved AI jobs' })).toBeVisible()
  const refused = await page.request.post(`/api/campaigns/${campaign.id}/approve`, { headers: { 'X-CSRF-Token': csrf } })
  expect(refused.status()).toBe(409)
  await page.goto(`/campaigns/${campaign.id}`)
  await expect(page.getByRole('link', { name: 'Review concepts', exact: true })).toBeVisible()
  await page.getByLabel('Spend', { exact: true }).fill('100')
  await page.getByLabel('Revenue', { exact: true }).fill('400')
  await page.getByRole('button', { name: 'Save results', exact: true }).click()
  await expect(page.getByText(/Results saved/)).toBeVisible()
  await expect(page.getByText(/ROAS 4.00×/)).toBeVisible()
})

test('calendar proposal becomes a reviewed campaign and approved publishing package', async ({ page }) => {
  test.skip(test.info().project.name !== 'desktop', 'Full production journey runs once; responsive navigation is checked in every project.')
  test.setTimeout(120000)
  await login(page)
  await page.goto('/calendar')
  await page.getByRole('button', { name: 'Plan with AI', exact: true }).click()
  await page.getByRole('button', { name: 'Next 90 days', exact: true }).click()
  await page.getByRole('button', { name: 'Prepare AI proposal', exact: true }).click()
  await page.getByRole('button', { name: 'Accept and save to calendar', exact: true }).click({ timeout: 45000 })
  await page.getByRole('button', { name: 'Create campaign', exact: true }).click()
  await expect(page).toHaveURL(/\/campaigns\/\d+$/)
  await page.getByRole('link', { name: 'Plan campaign concepts', exact: true }).click()
  await page.getByRole('button', { name: 'Approve', exact: true }).first().click({ timeout: 45000 })
  await page.getByRole('button', { name: /Release the plan/ }).click()
  await page.getByRole('button', { name: /Run the crew/ }).click()
  await page.getByRole('button', { name: /^Render ·/ }).click({ timeout: 45000 })
  await page.getByRole('button', { name: 'Approve', exact: true }).first().click({ timeout: 45000 })
  await page.getByRole('button', { name: /Ship these/ }).click()
  await page.getByRole('button', { name: 'Open Publish', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Publish', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Download media', exact: true }).first()).toBeVisible()
})

test('returning to a campaign restores its reading position', async ({ page }) => {
  await login(page)
  const csrf = (await (await page.request.get('/api/auth/me')).json()).csrf_token
  const response = await page.request.post('/api/campaigns', { headers: { 'X-CSRF-Token': csrf }, data: { name: 'Reading position', brief: 'An editable brief for the scroll restoration journey.' } })
  const campaign = await response.json()
  await page.goto(`/campaigns/${campaign.id}`)
  await expect(page.getByRole('heading', { name: 'Campaign results' })).toBeVisible()
  const scroller = page.locator('#main-content > .quiet-scroll')
  await scroller.evaluate(element => { element.scrollTop = 450 })
  await expect.poll(() => scroller.evaluate(element => element.scrollTop)).toBeGreaterThan(350)
  const navigation = page.getByRole('navigation', { name: test.info().project.name === 'mobile' ? 'Mobile shortcuts' : 'Main navigation', exact: true })
  await navigation.getByRole('link', { name: 'Chat', exact: true }).click()
  await expect(page.getByLabel('Message the strategist')).toBeVisible()
  await page.goBack()
  await expect.poll(() => scroller.evaluate(element => element.scrollTop)).toBeGreaterThan(350)
})
