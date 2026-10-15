import { expect, test, type Page } from '@playwright/test'

async function signIn(page: Page) {
  await page.goto('/dashboard')
  await page.getByLabel('Email', { exact: true }).fill('browser@example.test')
  await page.getByLabel('Password', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
}

test('a missing page chunk refreshes once and preserves the authenticated account', async ({ page }) => {
  let attempts = 0
  let documents = 0
  page.on('request', request => { if (request.isNavigationRequest()) documents++ })
  await page.route(/\/assets\/Dashboard-[^/]+\.js(?:\?.*)?$/, route => {
    attempts++
    return attempts === 1 ? route.abort('failed') : route.continue()
  })
  await signIn(page)
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible()
  expect(attempts).toBe(2)
  expect(documents).toBe(2)
  expect((await (await page.request.get('/api/auth/me')).json()).role).toBe('owner')
})

test('a persistent page failure stops reloading and offers manual recovery', async ({ page }) => {
  let documents = 0
  page.on('request', request => { if (request.isNavigationRequest()) documents++ })
  const dashboard = /\/assets\/Dashboard-[^/]+\.js(?:\?.*)?$/
  await page.route(dashboard, route => route.abort('failed'))
  await signIn(page)
  await expect(page.getByRole('heading', { name: 'This page couldn’t load', exact: true })).toBeVisible()
  expect(documents).toBe(2)
  await expect(page.getByText('Unexpected Application Error!', { exact: true })).toHaveCount(0)
  await page.unroute(dashboard)
  await page.getByRole('button', { name: 'Refresh workspace', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible()
})
