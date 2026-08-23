import { expect, test, type Page, type Route } from '@playwright/test'

const summaries = Array.from({ length: 10 }, (_, index) => ({
  id: `conversation-${index + 1}`,
  title: index === 8 ? 'A deliberately long Conversation title that must stay inside the sidebar' : `Conversation ${index + 1}`,
  created_at: '2026-08-23T00:00:00Z',
  updated_at: `2026-08-23T00:${String(index).padStart(2, '0')}:00Z`,
  archived_at: null,
}))

const message = (id: string, body: string) => ({
  id,
  role: 'user' as const,
  body,
  created_at: '2026-08-23T00:00:00Z',
  resource_refs: [],
  resources: [],
})

async function installConversationApi(page: Page) {
  let turnStatus: 'running' | 'completed' = 'running'
  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/v1/conversations') return route.fulfill({ json: summaries })
    if (path === '/api/v1/turns/turn-1') return route.fulfill({
      json: {
        id: 'turn-1', conversation_id: 'conversation-1', user_message_id: 'message-1', assistant_message_id: null,
        status: turnStatus, started_at: '2026-08-23T00:00:00Z', completed_at: turnStatus === 'completed' ? '2026-08-23T00:01:00Z' : null,
        error_code: null, sequence: 2, phase: 'searching', provisional_text: null,
      },
    })
    if (path === '/api/v1/turns/turn-1/events') return route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'retry: 10000\n\n',
        'id: 1\nevent: turn.started\ndata: {"turn_id":"turn-1","sequence":1,"type":"turn.started"}\n\n',
        'id: 2\nevent: phase.changed\ndata: {"turn_id":"turn-1","sequence":2,"type":"phase.changed","phase":"searching"}\n\n',
      ].join(''),
    })
    const match = path.match(/^\/api\/v1\/conversations\/(conversation-\d+)$/)
    if (match) {
      const summary = summaries.find((item) => item.id === match[1])!
      return route.fulfill({ json: { ...summary, messages: [message(`message-${summary.id}`, `History for ${summary.title}`)] } })
    }
    return route.fulfill({ status: 404, json: { detail: 'not_found' } })
  })
  return { completeTurn: () => { turnStatus = 'completed' as const } }
}

async function openNavigation(page: Page, isMobile: boolean) {
  if (isMobile) await page.getByRole('button', { name: 'Open navigation' }).click()
}

test('Conversation list scrolls independently and active Turn markers remain Conversation-scoped', async ({ page, isMobile }) => {
  await page.setViewportSize(isMobile ? { width: 390, height: 600 } : { width: 1280, height: 600 })
  const api = await installConversationApi(page)
  await page.goto('/?page=chat&conversation=conversation-1&turn=turn-1')
  await openNavigation(page, isMobile)

  const navigation = isMobile ? page.getByRole('dialog', { name: 'Navigation' }) : page.locator('.desktop-sidebar')
  const list = navigation.getByTestId('conversation-list')
  const newConversation = navigation.getByRole('button', { name: 'New conversation' })
  await expect(list).toBeVisible()
  await expect(navigation.getByRole('button', { name: /Conversation 1.*Running/i })).toBeVisible()
  await expect(page.getByRole('status')).toContainText(/Searching your resources|Looking through your information/)

  const geometry = await list.evaluate((element) => ({ clientHeight: element.clientHeight, scrollHeight: element.scrollHeight, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }))
  expect(geometry.scrollHeight).toBeGreaterThan(geometry.clientHeight)
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth + 1)
  const topBefore = (await newConversation.boundingBox())!.y
  await list.evaluate((element) => { element.scrollTop = element.scrollHeight })
  await expect.poll(() => list.evaluate((element) => element.scrollTop)).toBeGreaterThan(0)
  expect((await newConversation.boundingBox())!.y).toBeCloseTo(topBefore, 0)

  const longTitle = navigation.getByRole('button', { name: /A deliberately long Conversation title/i })
  await expect(longTitle).toBeVisible()
  const titleOverflow = await longTitle.locator('.conversation-title').evaluate((element) => ({ scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }))
  expect(titleOverflow.scrollWidth).toBeGreaterThan(titleOverflow.clientWidth)

  const backgroundTarget = navigation.getByRole('button', { name: /Conversation 10/i })
  await backgroundTarget.click()
  await expect(page.getByText('History for Conversation 10')).toBeVisible()

  await openNavigation(page, isMobile)
  await expect(navigation.getByRole('button', { name: /Conversation 1.*Running/i })).toBeVisible()
  await expect(navigation.getByRole('button', { name: /Conversation 10/i })).toHaveAttribute('aria-current', 'page')
  await expect(navigation.getByRole('button', { name: /Conversation 10/i })).not.toHaveAccessibleName(/Running/i)

  await navigation.getByRole('button', { name: /Conversation 1.*Running/i }).click()
  await expect(page.getByRole('status')).toContainText(/Searching your resources|Looking through your information/)
  await openNavigation(page, isMobile)
  await expect(navigation.getByRole('button', { name: /Conversation 1.*Running/i })).toHaveAttribute('aria-current', 'page')

  await navigation.getByRole('button', { name: /Conversation 10/i }).click()
  api.completeTurn()
  await openNavigation(page, isMobile)
  await navigation.getByRole('button', { name: /Conversation 1.*Running/i }).click()
  await expect(page.getByText('History for Conversation 1')).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
  await openNavigation(page, isMobile)
  await expect(navigation.getByRole('button', { name: /^Conversation 1\b/i })).not.toHaveAccessibleName(/Running/i)
})
