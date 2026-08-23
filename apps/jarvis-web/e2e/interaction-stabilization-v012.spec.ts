import { expect, test } from '@playwright/test'

const burstConversation = {
  id: 'conversation-burst',
  title: 'Progress replay validation',
  created_at: '2026-08-23T00:00:00Z',
  updated_at: '2026-08-23T00:00:01Z',
  archived_at: null,
}

const burstMessage = (id: string, role: 'user' | 'assistant', body: string) => ({
  id,
  role,
  body,
  created_at: '2026-08-23T00:00:01Z',
  resource_refs: [],
  resources: [],
})

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

test('rapid replayed progress receives a browser paint without delaying terminal output', async ({ page }) => {
  let eventRequestCount = 0
  let terminalFulfilledAt = 0
  let terminal = false

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/v1/conversations' && request.method() === 'GET') return route.fulfill({ json: [] })
    if (path === '/api/v1/conversations' && request.method() === 'POST') return route.fulfill({ status: 201, json: burstConversation })
    if (path === '/api/v1/conversations/conversation-burst/turns') return route.fulfill({ status: 201, json: { turn_id: 'turn-burst' } })
    if (path === '/api/v1/conversations/conversation-burst') return route.fulfill({
      json: {
        ...burstConversation,
        messages: terminal
          ? [burstMessage('user-burst', 'user', 'Find synthetic resources'), burstMessage('assistant-burst', 'assistant', 'Canonical final response')]
          : [],
      },
    })
    if (path === '/api/v1/turns/turn-burst') return route.fulfill({
      json: {
        id: 'turn-burst', conversation_id: 'conversation-burst', user_message_id: 'user-burst', assistant_message_id: null,
        status: 'running', started_at: '2026-08-23T00:00:00Z', completed_at: null, error_code: null,
        sequence: 5, phase: 'composing', provisional_text: null,
      },
    })
    if (path === '/api/v1/turns/turn-burst/events') {
      eventRequestCount += 1
      if (eventRequestCount === 1) return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          'retry: 50\n\n',
          'id: 1\nevent: turn.started\ndata: {"turn_id":"turn-burst","sequence":1,"type":"turn.started"}\n\n',
          'id: 2\nevent: phase.changed\ndata: {"turn_id":"turn-burst","sequence":2,"type":"phase.changed","phase":"searching"}\n\n',
          'id: 3\nevent: tool.started\ndata: {"turn_id":"turn-burst","sequence":3,"type":"tool.started","operation_id":1,"category":"pdi","capability":"search_personal_resources","arguments":"private-argument","resource_refs":["pdi:resource:private"]}\n\n',
          'id: 4\nevent: tool.completed\ndata: {"turn_id":"turn-burst","sequence":4,"type":"tool.completed","operation_id":1,"category":"pdi","capability":"search_personal_resources","duration_ms":7,"result":"private-result"}\n\n',
          'id: 5\nevent: phase.changed\ndata: {"turn_id":"turn-burst","sequence":5,"type":"phase.changed","phase":"composing"}\n\n',
        ].join(''),
      })
      await new Promise((resolve) => setTimeout(resolve, 1600))
      terminal = true
      terminalFulfilledAt = Date.now()
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'id: 6\nevent: turn.completed\ndata: {"turn_id":"turn-burst","sequence":6,"type":"turn.completed"}\n\n',
      })
    }
    return route.fulfill({ status: 404, json: { detail: 'not_found' } })
  })

  await page.goto('/?page=chat')
  await page.getByLabel('Message Jarvis').fill('Find synthetic resources')
  await page.getByRole('button', { name: 'Send message' }).click()

  const status = page.getByRole('status')
  await expect(status).toContainText(/Searching your resources|Looking through your information/)
  const searchingObservedAt = await page.evaluate(() => performance.now())
  const paintedText = await status.evaluate(async (element) => {
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
    return element.textContent
  })
  expect(paintedText).toMatch(/Searching your resources|Looking through your information/)
  await expect(status).toContainText(/Composing an answer|Organizing the response/)
  const composingObservedAt = await page.evaluate(() => performance.now())
  expect(composingObservedAt - searchingObservedAt).toBeGreaterThan(150)
  await expect(status).toContainText(/1s/)

  await expect(page.getByText('Canonical final response')).toBeVisible()
  expect(Date.now() - terminalFulfilledAt).toBeLessThan(1000)
  await expect(status).toHaveCount(0)
  await expect(page.getByText(/private-argument|private-result|pdi:resource:private/)).toHaveCount(0)
  await expect(page.getByText(/found|successful/i)).toHaveCount(0)
})
