import { expect, test } from '@playwright/test'
import path from 'node:path'

const review = (name: string) => path.resolve('review/screenshots', name)

test.describe('deterministic visual review', () => {
  test('desktop New Chat', async ({ page, isMobile }) => {
    test.skip(isMobile)
    await page.goto('/?page=chat&scene=home')
    await expect(page.getByRole('heading', { name: 'What can I help you with?' })).toBeVisible()
    await page.screenshot({ path: review('desktop-new-chat.png'), fullPage: true })
  })

  test('desktop Conversation and Resources', async ({ page, isMobile }) => {
    test.skip(isMobile)
    await page.goto('/?page=chat&scene=conversation')
    await expect(page.getByText(/review converged on three ideas/i)).toBeVisible()
    await page.screenshot({ path: review('desktop-conversation-resources.png'), fullPage: true })
  })

  test('desktop Agent Working and Work Panel', async ({ page, isMobile }) => {
    test.skip(isMobile)
    await page.goto('/?page=chat&scene=working')
    await expect(page.getByRole('status')).toContainText(/Checking the details|Reviewing the response/)
    await page.screenshot({ path: review('desktop-agent-working.png'), fullPage: true })
  })

  test('desktop Providers', async ({ page, isMobile }) => {
    test.skip(isMobile)
    await page.goto('/?page=providers&scene=review')
    await expect(page.getByRole('heading', { name: 'Providers', level: 2, exact: true })).toBeVisible()
    await page.screenshot({ path: review('desktop-providers.png'), fullPage: true })
  })

  test('mobile Chat', async ({ page, isMobile }) => {
    test.skip(!isMobile)
    await page.goto('/?page=chat&scene=conversation')
    await expect(page.getByLabel('Message Jarvis')).toBeVisible()
    await page.screenshot({ path: review('mobile-chat.png'), fullPage: true })
  })

  test('mobile Resource Detail', async ({ page, isMobile }) => {
    test.skip(!isMobile)
    await page.goto('/?page=resources&detail=image&scene=review')
    await expect(page.getByRole('dialog', { name: 'Resource detail' })).toBeVisible()
    await page.screenshot({ path: review('mobile-resource-detail.png'), fullPage: true })
  })

  test('mobile Providers', async ({ page, isMobile }) => {
    test.skip(!isMobile)
    await page.goto('/?page=providers&scene=review')
    await expect(page.getByRole('heading', { name: 'Providers', level: 2, exact: true })).toBeVisible()
    await page.screenshot({ path: review('mobile-providers.png'), fullPage: true })
  })
})
