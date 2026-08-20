import { expect, test } from '@playwright/test'

const csp = "default-src 'self'; script-src 'self'; style-src-elem 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; worker-src 'none'"

test('production build serves strict headers and immutable hashed assets', async ({ page, request }) => {
  const response = await page.goto('/')
  expect(response?.headers()['content-security-policy']).toBe(csp)
  expect(response?.headers()['cache-control']).toBe('private, no-cache')
  const source = await page.locator('script[src]').getAttribute('src')
  expect(source).toMatch(/^\/assets\/.*\.js$/)
  const asset = await request.get(source!)
  expect(asset.headers()['cache-control']).toBe('private, max-age=31536000, immutable')
})

test('query parameters cannot activate review resources or execution', async ({ page }) => {
  await page.goto('/?page=providers&scene=review&detail=provider')
  await expect(page.locator('body')).toContainText('Providers are unavailable')
  await expect(page.getByRole('dialog')).toHaveCount(0)

  await page.goto('/?page=chat&scene=working')
  await expect(page.locator('body')).toContainText('What can I help you with?')
  await expect(page.getByText('Reviewing likely matches')).toHaveCount(0)
})
