import { expect, test, type Page, type Route } from '@playwright/test'

const conversation = {
  id: 'conversation-citations',
  title: 'Synthetic citation rendering',
  created_at: '2026-08-25T00:00:00Z',
  updated_at: '2026-08-25T00:00:01Z',
  archived_at: null,
  messages: [
    {
      id: 'assistant-citations',
      role: 'assistant',
      body: '根据资料，来源如下：\n\nhttps://source-a.example/path\n\n以及 https://source-b.example/path。',
      created_at: '2026-08-25T00:00:01Z',
      resource_refs: [],
      resources: [],
    },
  ],
}

async function installCitationApi(page: Page) {
  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/v1/conversations' && request.method() === 'GET') return route.fulfill({ json: [conversation] })
    if (path === '/api/v1/conversations/conversation-citations' && request.method() === 'GET') return route.fulfill({ json: conversation })
    return route.fulfill({ status: 404, json: { detail: 'not_found' } })
  })
}

test('bare Chinese-answer source URLs become safe clickable links', async ({ page }) => {
  await installCitationApi(page)
  await page.context().route('https://source-a.example/**', (route) => route.fulfill({ contentType: 'text/plain', body: 'synthetic public source' }))
  await page.goto('/?page=chat&conversation=conversation-citations')

  const sourceA = page.getByRole('link', { name: 'https://source-a.example/path' })
  const sourceB = page.getByRole('link', { name: 'https://source-b.example/path' })
  await expect(sourceA).toHaveAttribute('href', 'https://source-a.example/path')
  await expect(sourceB).toHaveAttribute('href', 'https://source-b.example/path')
  for (const link of [sourceA, sourceB]) {
    await expect(link).toHaveAttribute('target', '_blank')
    await expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  }
  await expect(page.locator('.assistant-message a')).toHaveCount(2)
  const [opened] = await Promise.all([page.waitForEvent('popup'), sourceA.click()])
  await opened.waitForLoadState()
  expect(opened.url()).toBe('https://source-a.example/path')
  await opened.close()
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', await page.locator('body').evaluate((body) => body.clientWidth))
})
