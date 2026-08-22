import { expect, test, type Page, type Route } from '@playwright/test'

const conversation = {
  id: 'conversation-work',
  title: 'Synthetic work',
  created_at: '2026-08-22T00:00:00Z',
  updated_at: '2026-08-22T00:00:01Z',
  archived_at: null,
}

async function installWorkApi(page: Page) {
  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/v1/conversations' && request.method() === 'GET') return route.fulfill({ json: [] })
    if (path === '/api/v1/conversations' && request.method() === 'POST') return route.fulfill({ status: 201, json: conversation })
    if (path === '/api/v1/conversations/conversation-work/turns') return route.fulfill({ status: 201, json: { turn_id: 'turn-work' } })
    if (path === '/api/v1/turns/turn-work/events') return route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'id: 1\nevent: turn.started\ndata: {"turn_id":"turn-work","sequence":1,"type":"turn.started"}\n\n',
        'id: 2\nevent: phase.changed\ndata: {"turn_id":"turn-work","sequence":2,"type":"phase.changed","phase":"computing"}\n\n',
        'id: 3\nevent: tool.started\ndata: {"turn_id":"turn-work","sequence":3,"type":"tool.started","operation_id":1,"category":"exec","capability":"run_python"}\n\n',
        'id: 4\nevent: tool.completed\ndata: {"turn_id":"turn-work","sequence":4,"type":"tool.completed","operation_id":1,"category":"exec","capability":"run_python","duration_ms":12}\n\n',
        'id: 5\nevent: turn.completed\ndata: {"turn_id":"turn-work","sequence":5,"type":"turn.completed"}\n\n',
      ].join(''),
    })
    if (path === '/api/v1/conversations/conversation-work' && request.method() === 'GET') return route.fulfill({ json: { ...conversation, messages: [] } })
    return route.fulfill({ status: 404, json: { detail: 'not_found' } })
  })
}

test('real tool activity opens calmly on desktop and stays manual on mobile', async ({ page, isMobile }) => {
  await installWorkApi(page)
  await page.goto('/?page=chat')
  await page.getByLabel('Message Jarvis').fill('Use the safe execution path')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByRole('button', { name: 'Open work panel' })).toBeVisible()

  if (isMobile) {
    await expect(page.getByRole('dialog', { name: 'Work' })).toHaveCount(0)
    await page.getByRole('button', { name: 'Open work panel' }).click()
    await expect(page.getByRole('dialog', { name: 'Work' })).toBeVisible()
  }

  const workPanel = page.locator('.work-panel:visible')
  const operation = workPanel.getByRole('listitem').filter({ hasText: 'Run Python' })
  await expect(operation).toBeVisible()
  await expect(operation).toContainText('Finished · 12 ms')
  await expect(workPanel.getByText('Work completed')).toBeVisible()
  await expect(workPanel.getByText(/successful/i)).toHaveCount(0)
})
