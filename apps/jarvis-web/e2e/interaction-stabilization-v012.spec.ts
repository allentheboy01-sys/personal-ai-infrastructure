import { expect, test } from '@playwright/test'

const conversation = {
  id: 'conversation-scroll',
  title: 'Scroll validation',
  created_at: '2026-08-23T00:00:00Z',
  updated_at: '2026-08-23T00:00:00Z',
  archived_at: null,
  messages: Array.from({ length: 60 }, (_, index) => ({
    id: `message-${index}`,
    role: index % 2 ? 'assistant' : 'user',
    body: `Browser geometry message ${index + 1}`,
    created_at: '2026-08-23T00:00:00Z',
    resource_refs: [],
    resources: [],
  })),
}

test('Jump retains pinned ownership across smooth-scroll content growth', async ({ page }) => {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/conversations') return route.fulfill({ json: [conversation] })
    if (path === '/api/v1/conversations/conversation-scroll') return route.fulfill({ json: conversation })
    return route.fulfill({ status: 404, json: { detail: 'not_found' } })
  })
  await page.goto('/?page=chat&conversation=conversation-scroll')
  await expect(page.getByText('Browser geometry message 60')).toBeVisible()

  const scroll = page.locator('.chat-scroll')
  await scroll.evaluate((element) => { element.scrollTop = 0; element.dispatchEvent(new Event('scroll')) })
  await page.locator('.chat-content').evaluate((content) => {
    const growth = document.createElement('div')
    growth.style.height = '120px'
    growth.setAttribute('data-validation-growth', 'before-jump')
    content.append(growth)
  })
  const jump = page.getByRole('button', { name: 'Jump to latest' })
  await expect(jump).toBeVisible()

  await page.evaluate(() => {
    window.setTimeout(() => {
      const content = document.querySelector('.chat-content')
      const growth = document.createElement('div')
      growth.style.height = '240px'
      growth.setAttribute('data-validation-growth', 'during-jump')
      content?.append(growth)
    }, 40)
  })
  await jump.click()
  await page.waitForTimeout(1000)
  const distanceAfterJump = await scroll.evaluate((element) => element.scrollHeight - element.scrollTop - element.clientHeight)
  expect(distanceAfterJump).toBeLessThanOrEqual(110)

  await page.locator('.chat-content').evaluate((content) => {
    const growth = document.createElement('div')
    growth.style.height = '180px'
    growth.setAttribute('data-validation-growth', 'after-jump')
    content.append(growth)
  })
  await expect.poll(() => scroll.evaluate((element) => element.scrollHeight - element.scrollTop - element.clientHeight)).toBeLessThanOrEqual(110)
})
