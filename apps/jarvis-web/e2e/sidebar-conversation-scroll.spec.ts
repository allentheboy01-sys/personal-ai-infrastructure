import { expect, test, type Locator, type Page, type Route } from '@playwright/test'

const history = Array.from({ length: 48 }, (_, index) => ({
  id: `conversation-${index + 1}`,
  title: index === 20 ? `Conversation ${index + 1} with a deliberately long title that must never widen the sidebar` : `Conversation ${index + 1}`,
  created_at: '2026-08-25T00:00:00Z',
  updated_at: `2026-08-25T00:${String(index).padStart(2, '0')}:00Z`,
  archived_at: null,
}))

const message = (id: string, role: 'user' | 'assistant', body: string) => ({
  id,
  role,
  body,
  created_at: '2026-08-25T00:00:00Z',
  resource_refs: [],
  resources: [],
})

async function installLongHistory(page: Page) {
  let summaries = [...history]
  let newConversationComplete = false
  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/v1/conversations' && request.method() === 'GET') return route.fulfill({ json: summaries })
    if (path === '/api/v1/conversations' && request.method() === 'POST') {
      const created = { ...history[0], id: 'conversation-new', title: 'Inserted Conversation', updated_at: '2026-08-25T01:00:00Z' }
      summaries = [created, ...summaries]
      return route.fulfill({ status: 201, json: created })
    }
    if (path === '/api/v1/conversations/conversation-new/turns' && request.method() === 'POST') {
      newConversationComplete = true
      return route.fulfill({ status: 201, json: { turn_id: 'turn-new' } })
    }
    if (path === '/api/v1/turns/turn-new/events') return route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'id: 1\nevent: turn.started\ndata: {"turn_id":"turn-new","sequence":1,"type":"turn.started"}\n\n',
        'id: 2\nevent: turn.completed\ndata: {"turn_id":"turn-new","sequence":2,"type":"turn.completed"}\n\n',
      ].join(''),
    })
    const match = path.match(/^\/api\/v1\/conversations\/(conversation-(?:\d+|new))$/)
    if (match) {
      const summary = summaries.find((item) => item.id === match[1])!
      const messages = summary.id === 'conversation-new'
        ? newConversationComplete ? [message('new-user', 'user', 'Create a synthetic conversation'), message('new-assistant', 'assistant', 'Created')] : []
        : Array.from({ length: 60 }, (_, index) => message(`${summary.id}-message-${index}`, index % 2 ? 'assistant' : 'user', `History ${index + 1} for ${summary.title}`))
      return route.fulfill({ json: { ...summary, messages } })
    }
    return route.fulfill({ status: 404, json: { detail: 'not_found' } })
  })
}

async function navigation(page: Page, isMobile: boolean) {
  if (isMobile && await page.getByRole('dialog', { name: 'Navigation' }).count() === 0) {
    await page.getByRole('button', { name: 'Open navigation' }).click()
  }
  return isMobile ? page.getByRole('dialog', { name: 'Navigation' }) : page.locator('.desktop-sidebar')
}

async function wheelToEdge(page: Page, list: Locator, direction: 1 | -1) {
  const box = await list.boundingBox()
  if (!box) throw new Error('conversation_list_missing')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  for (let index = 0; index < 12; index += 1) {
    await page.mouse.wheel(0, direction * 700)
    await page.waitForTimeout(20)
  }
  await expect.poll(() => list.evaluate((element, down) => down
    ? element.scrollHeight - element.clientHeight - element.scrollTop
    : element.scrollTop, direction > 0)).toBeLessThanOrEqual(2)
}

test('wheel reaches the complete conversation history and preserves independent scroll ownership', async ({ page, isMobile }) => {
  await installLongHistory(page)
  await page.goto('/?page=chat')
  const nav = await navigation(page, isMobile)
  const list = nav.getByTestId('conversation-list')
  const rows = list.locator('button')
  await expect(rows).toHaveCount(48)

  const geometry = await list.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }))
  expect(geometry.scrollHeight).toBeGreaterThan(geometry.clientHeight)
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth + 1)
  const last = nav.getByRole('button', { name: /^Conversation 48\b/ })
  await expect(last).not.toBeInViewport()

  const pageTop = await page.evaluate(() => document.scrollingElement?.scrollTop ?? 0)
  await wheelToEdge(page, list, 1)
  await expect(last).toBeInViewport()
  expect(await page.evaluate(() => document.scrollingElement?.scrollTop ?? 0)).toBe(pageTop)
  await last.click()
  await expect(page).toHaveURL(/conversation=conversation-48/)
  await expect(page.getByText('History 60 for Conversation 48')).toBeVisible()

  const navAtBottom = await navigation(page, isMobile)
  await expect(navAtBottom.getByRole('button', { name: /^Conversation 48\b/ })).toHaveAttribute('aria-current', 'page')
  const listAtBottom = navAtBottom.getByTestId('conversation-list')
  await wheelToEdge(page, listAtBottom, -1)
  const first = navAtBottom.getByRole('button', { name: /^Conversation 1\b/ })
  await expect(first).toBeInViewport()
  await first.click()
  await expect(page).toHaveURL(/conversation=conversation-1/)
  await expect(page.getByText('History 60 for Conversation 1')).toBeVisible()

  await page.goBack()
  await expect(page).toHaveURL(/conversation=conversation-48/)
  await page.goForward()
  await expect(page).toHaveURL(/conversation=conversation-1/)

  const chat = page.locator('.chat-scroll')
  await chat.evaluate((element) => { element.scrollTop = 120 })
  const chatTop = await chat.evaluate((element) => element.scrollTop)
  const navForOwnership = await navigation(page, isMobile)
  await wheelToEdge(page, navForOwnership.getByTestId('conversation-list'), 1)
  expect(await chat.evaluate((element) => element.scrollTop)).toBe(chatTop)

  await navForOwnership.getByRole('button', { name: 'New conversation' }).click()
  await page.getByLabel('Message Jarvis').fill('Create a synthetic conversation')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page).toHaveURL(/conversation=conversation-new(?!.*turn=)/, { timeout: 10_000 })
  const navAfterInsert = await navigation(page, isMobile)
  const listAfterInsert = navAfterInsert.getByTestId('conversation-list')
  await expect(listAfterInsert.locator('button')).toHaveCount(49)
  await wheelToEdge(page, listAfterInsert, 1)
  await expect(navAfterInsert.getByRole('button', { name: /^Conversation 48\b/ })).toBeInViewport()
})

test('short desktop viewport keeps an off-screen selected conversation reachable without clipping', async ({ page, isMobile }) => {
  test.skip(isMobile, 'short desktop-height regression')
  await page.setViewportSize({ width: 1280, height: 520 })
  await installLongHistory(page)
  await page.goto('/?page=chat&conversation=conversation-48')
  const nav = await navigation(page, false)
  const list = nav.getByTestId('conversation-list')
  const selected = nav.getByRole('button', { name: /^Conversation 48\b/ })
  await expect(selected).toHaveAttribute('aria-current', 'page')
  await expect(selected).toBeInViewport()
  const geometry = await list.evaluate((element) => ({ clientHeight: element.clientHeight, scrollHeight: element.scrollHeight }))
  expect(geometry.scrollHeight).toBeGreaterThan(geometry.clientHeight * 8)
  await wheelToEdge(page, list, -1)
  await expect(nav.getByRole('button', { name: /^Conversation 1\b/ })).toBeInViewport()
})
