import { expect, test, type Page, type Route } from '@playwright/test'

const summaryA = { id: 'conversation-a', title: 'Canonical A', created_at: '2026-08-22T00:00:00Z', updated_at: '2026-08-22T00:00:00Z', archived_at: null }
const summaryB = { id: 'conversation-b', title: 'Second canonical', created_at: '2026-08-22T00:01:00Z', updated_at: '2026-08-22T00:01:00Z', archived_at: null }
const message = (id: string, role: 'user' | 'assistant', body: string) => ({ id, role, body, created_at: '2026-08-22T00:00:00Z', resource_refs: [], resources: [] })

async function installConversationApi(page: Page) {
  let recent = [summaryA]
  let detailB = { ...summaryB, messages: [] as ReturnType<typeof message>[] }
  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/v1/conversations' && request.method() === 'GET') return route.fulfill({ json: recent })
    if (path === '/api/v1/conversations/conversation-a' && request.method() === 'GET') return route.fulfill({ json: { ...summaryA, messages: [message('user-a', 'user', 'History A'), message('assistant-a', 'assistant', '**Bold answer**\n\n## Canonical heading\n\n`inline`')] } })
    if (path === '/api/v1/conversations' && request.method() === 'POST') { recent = [summaryB, summaryA]; return route.fulfill({ status: 201, json: summaryB }) }
    if (path === '/api/v1/conversations/conversation-b/turns' && request.method() === 'POST') { detailB = { ...summaryB, messages: [message('user-b', 'user', 'Message B'), message('assistant-b', 'assistant', 'Canonical B response')] }; return route.fulfill({ status: 201, json: { turn_id: 'turn-b' } }) }
    if (path === '/api/v1/turns/turn-b/events') return route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'id: 1\nevent: turn.started\ndata: {"turn_id":"turn-b","sequence":1,"type":"turn.started"}\n\nid: 2\nevent: turn.completed\ndata: {"turn_id":"turn-b","sequence":2,"type":"turn.completed"}\n\n' })
    if (path === '/api/v1/conversations/conversation-b' && request.method() === 'GET') return route.fulfill({ json: detailB })
    return route.fulfill({ status: 404, json: { detail: 'not_found' } })
  })
}

async function openNavigation(page: Page, isMobile: boolean) {
  if (isMobile) await page.getByRole('button', { name: 'Open navigation' }).click()
}

test('real Recent, New conversation, canonical history and Markdown stay coherent', async ({ page, isMobile }) => {
  await installConversationApi(page)
  await page.goto('/?page=chat')
  await openNavigation(page, isMobile)
  await page.getByRole('button', { name: /canonical a/i }).click()

  await expect(page.getByRole('heading', { name: 'Canonical A', level: 1 })).toBeVisible()
  await expect(page.getByText('History A')).toBeVisible()
  await expect(page.getByText('Bold answer')).toHaveJSProperty('tagName', 'STRONG')
  await expect(page.getByRole('heading', { name: 'Canonical heading', level: 2 })).toBeVisible()
  await expect(page).toHaveURL(/conversation=conversation-a/)

  await openNavigation(page, isMobile)
  await page.getByRole('button', { name: 'New conversation' }).click()
  await expect(page.getByRole('heading', { name: 'What can I help you with?' })).toBeVisible()
  await expect(page).not.toHaveURL(/conversation=/)
  await page.getByLabel('Message Jarvis').fill('Message B')
  await page.getByRole('button', { name: 'Send message' }).click()

  await expect(page.getByText('Canonical B response')).toBeVisible()
  await expect(page.getByText('History A')).toHaveCount(0)
  await expect(page).toHaveURL(/conversation=conversation-b/)
  await openNavigation(page, isMobile)
  await expect(page.getByRole('button', { name: /second canonical/i })).toBeVisible()
})

test('image detail lightbox works on responsive layouts', async ({ page }) => {
  await page.goto('/?page=resources&detail=image&scene=review')
  await page.getByRole('button', { name: 'Enlarge Morning lake' }).click()
  await expect(page.getByRole('dialog', { name: 'Morning lake' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: 'Morning lake' })).toHaveCount(0)
})
