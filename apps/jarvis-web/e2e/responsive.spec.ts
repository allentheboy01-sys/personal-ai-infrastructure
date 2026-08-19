import { expect, test } from '@playwright/test'

test('primary navigation and core landmarks are keyboard reachable', async ({ page }) => {
  await page.goto('/?page=chat&scene=home')
  await expect(page.getByRole('heading', { name: 'What can I help you with?' })).toBeVisible()
  await expect(page.getByLabel('Message Jarvis')).toBeVisible()
  await page.keyboard.press('Tab')
  await expect(page.locator(':focus')).toBeVisible()
})

test('mobile uses a drawer and has no horizontal overflow', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'mobile-only behavior')
  await page.goto('/?page=providers')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await expect(page.getByRole('dialog', { name: 'Navigation' })).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(overflow).toBe(false)
})

test('resource detail is a full-screen accessible dialog on mobile', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'mobile-only behavior')
  await page.goto('/?page=resources&detail=message')
  const detail = page.getByRole('dialog', { name: 'Resource detail' })
  await expect(detail).toBeVisible()
  await expect(detail.getByText(/message body is unavailable/i)).toBeVisible()
})
