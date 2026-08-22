import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppShell } from './AppShell'
import { reviewModeEnabled } from './reviewMode'

class MockEventSource {
  static CLOSED = 2
  readyState = 1
  onerror: (() => void) | null = null
  listeners = new Map<string, EventListener>()
  constructor(public url: string) {}
  addEventListener(type: string, listener: EventListener) { this.listeners.set(type, listener) }
  close() { this.readyState = MockEventSource.CLOSED }
}

const summaryA = { id: 'conversation-a', title: 'Conversation A', created_at: '2026-08-22T00:00:00Z', updated_at: '2026-08-22T00:00:00Z', archived_at: null }
const summaryB = { id: 'conversation-b', title: 'Message B', created_at: '2026-08-22T00:01:00Z', updated_at: '2026-08-22T00:01:00Z', archived_at: null }
const detail = (summary: typeof summaryA, body: string) => ({ ...summary, messages: [{ id: `message-${summary.id}`, role: 'user', body, created_at: summary.created_at, resource_refs: [], resources: [] }] })

describe('production review isolation', () => {
  it('requires the dedicated review build as well as a scene', () => {
    expect(reviewModeEnabled(false, true)).toBe(false)
    expect(reviewModeEnabled(true, false)).toBe(false)
    expect(reviewModeEnabled(true, true)).toBe(true)
  })
})

describe('canonical conversation shell', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.history.replaceState(null, '', '/')
  })

  it('opens real Recent history and creates a distinct conversation after New', async () => {
    let recent = [summaryA]
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/v1/conversations' && !init?.method) return new Response(JSON.stringify(recent), { status: 200 })
      if (url === '/api/v1/conversations/conversation-a') return new Response(JSON.stringify(detail(summaryA, 'History A')), { status: 200 })
      if (url === '/api/v1/conversations' && init?.method === 'POST') { recent = [summaryB, summaryA]; return new Response(JSON.stringify(summaryB), { status: 201 }) }
      if (url === '/api/v1/conversations/conversation-b/turns') return new Response(JSON.stringify({ turn_id: 'turn-b' }), { status: 201 })
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    vi.stubGlobal('crypto', { randomUUID: () => 'local-b' })
    window.history.replaceState(null, '', '/?page=chat')

    render(<AppShell />)
    await userEvent.click(await screen.findByRole('button', { name: /conversation a/i }))
    expect(await screen.findByText('History A')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Conversation A', level: 1 })).toBeInTheDocument()
    expect(window.location.search).toBe('?page=chat&conversation=conversation-a')

    await userEvent.click(screen.getByRole('button', { name: 'New conversation' }))
    expect(screen.queryByText('History A')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'What can I help you with?' })).toBeInTheDocument()
    expect(window.location.search).toBe('?page=chat')
    await userEvent.type(screen.getByLabelText('Message Jarvis'), 'Message B{enter}')

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/conversations/conversation-b/turns', expect.objectContaining({ method: 'POST' })))
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/v1/conversations/conversation-a/turns')).toBe(false)
    expect(window.location.search).toContain('conversation=conversation-b')
    await waitFor(() => expect(screen.getAllByText('Message B').length).toBeGreaterThanOrEqual(2))
  })

  it('restores the exact conversation from the URL on reload', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/v1/conversations') return new Response(JSON.stringify([summaryB, summaryA]), { status: 200 })
      if (url === '/api/v1/conversations/conversation-b') return new Response(JSON.stringify(detail(summaryB as typeof summaryA, 'History B')), { status: 200 })
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    window.history.replaceState(null, '', '/?page=chat&conversation=conversation-b')

    render(<AppShell />)
    expect(await screen.findByText('History B')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Message B', level: 1 })).toBeInTheDocument()

    window.history.pushState(null, '', '/?page=chat')
    fireEvent.popState(window)
    expect(await screen.findByRole('heading', { name: 'What can I help you with?' })).toBeInTheDocument()
    expect(screen.queryByText('History B')).not.toBeInTheDocument()
  })
})
