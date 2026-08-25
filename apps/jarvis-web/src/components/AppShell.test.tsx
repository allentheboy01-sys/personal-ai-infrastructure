import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppShell } from './AppShell'
import { reviewModeEnabled } from './reviewMode'

class MockEventSource {
  static CLOSED = 2
  static instances: MockEventSource[] = []
  readyState = 1
  onerror: (() => void) | null = null
  listeners = new Map<string, EventListener>()
  constructor(public url: string) { MockEventSource.instances.push(this) }
  addEventListener(type: string, listener: EventListener) { this.listeners.set(type, listener) }
  close() { this.readyState = MockEventSource.CLOSED }
  emit(type: string, payload: object) { this.listeners.get(type)?.({ data: JSON.stringify(payload) } as unknown as Event) }
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
    MockEventSource.instances = []
    window.history.replaceState(null, '', '/')
  })

  it('keeps the complete canonical conversation history available to the sidebar', async () => {
    const summaries = Array.from({ length: 24 }, (_, index) => ({
      ...summaryA,
      id: `stored-conversation-${index + 1}`,
      title: `Stored Conversation ${index + 1}`,
    }))
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === '/api/v1/conversations') return new Response(JSON.stringify(summaries), { status: 200 })
      throw new Error(`unexpected fetch ${String(input)}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    window.history.replaceState(null, '', '/?page=chat')

    render(<AppShell />)

    expect(await screen.findAllByRole('button', { name: /^Stored Conversation \d+/ })).toHaveLength(24)
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

  it('keeps a background running Conversation marked until its exact Turn terminates', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/v1/conversations') return new Response(JSON.stringify([summaryA, summaryB]), { status: 200 })
      if (url === '/api/v1/conversations/conversation-a') return new Response(JSON.stringify(detail(summaryA, 'History A')), { status: 200 })
      if (url === '/api/v1/conversations/conversation-b') return new Response(JSON.stringify(detail(summaryB as typeof summaryA, 'History B')), { status: 200 })
      if (url === '/api/v1/turns/turn-a') return new Response(JSON.stringify({ id: 'turn-a', conversation_id: 'conversation-a', user_message_id: 'user-a', assistant_message_id: null, status: 'running', started_at: '2026-08-22T00:00:00Z', completed_at: null, error_code: null, sequence: 1, phase: 'searching', provisional_text: null }), { status: 200 })
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    window.history.replaceState(null, '', '/?page=chat&conversation=conversation-a&turn=turn-a')

    render(<AppShell />)
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    expect(await screen.findByRole('button', { name: /conversation a.*running/i })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /message b/i }))
    await screen.findByText('History B')
    expect(screen.getByRole('button', { name: /conversation a.*running/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /message b/i })).not.toHaveAccessibleName(/running/i)

    await userEvent.click(screen.getByRole('button', { name: /conversation a.*running/i }))
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(2))
    act(() => MockEventSource.instances[1].emit('turn.completed', { turn_id: 'turn-a', sequence: 2, type: 'turn.completed' }))
    await waitFor(() => expect(screen.getByRole('button', { name: /conversation a/i })).not.toHaveAccessibleName(/running/i))
  })

  it('auto-opens the desktop Work Panel on the first real tool event', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/v1/conversations' && !init?.method) return new Response('[]', { status: 200 })
      if (url === '/api/v1/conversations' && init?.method === 'POST') return new Response(JSON.stringify(summaryB), { status: 201 })
      if (url === '/api/v1/conversations/conversation-b/turns') return new Response(JSON.stringify({ turn_id: 'turn-tool' }), { status: 201 })
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    vi.stubGlobal('crypto', { randomUUID: () => 'local-tool' })
    window.history.replaceState(null, '', '/?page=chat')

    render(<AppShell />)
    await userEvent.type(screen.getByLabelText('Message Jarvis'), 'Use a tool{enter}')
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    const stream = MockEventSource.instances[0]
    act(() => stream.emit('turn.started', { turn_id: 'turn-tool', sequence: 1, type: 'turn.started' }))
    act(() => stream.emit('phase.changed', { turn_id: 'turn-tool', sequence: 2, type: 'phase.changed', phase: 'searching' }))
    expect(screen.queryByText('Search personal resources')).not.toBeInTheDocument()
    act(() => stream.emit('tool.started', { turn_id: 'turn-tool', sequence: 3, type: 'tool.started', operation_id: 1, category: 'pdi', capability: 'search_personal_resources' }))

    expect(await screen.findByText('Search personal resources')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Work', level: 2 })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()
  })

  it('does not auto-open for a no-tool answer', async () => {
    const completed = { ...summaryB, messages: [
      { id: 'user-b', role: 'user', body: 'No tool', created_at: summaryB.created_at, resource_refs: [], resources: [] },
      { id: 'assistant-b', role: 'assistant', body: 'Done', created_at: summaryB.created_at, resource_refs: [], resources: [] },
    ] }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/v1/conversations' && !init?.method) return new Response('[]', { status: 200 })
      if (url === '/api/v1/conversations' && init?.method === 'POST') return new Response(JSON.stringify(summaryB), { status: 201 })
      if (url === '/api/v1/conversations/conversation-b/turns') return new Response(JSON.stringify({ turn_id: 'turn-simple' }), { status: 201 })
      if (url === '/api/v1/conversations/conversation-b') return new Response(JSON.stringify(completed), { status: 200 })
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    vi.stubGlobal('crypto', { randomUUID: () => 'local-simple' })

    render(<AppShell />)
    await userEvent.type(screen.getByLabelText('Message Jarvis'), 'No tool{enter}')
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    const stream = MockEventSource.instances[0]
    act(() => stream.emit('turn.started', { turn_id: 'turn-simple', sequence: 1, type: 'turn.started' }))
    act(() => stream.emit('phase.changed', { turn_id: 'turn-simple', sequence: 2, type: 'phase.changed', phase: 'composing' }))
    act(() => stream.emit('turn.completed', { turn_id: 'turn-simple', sequence: 3, type: 'turn.completed' }))

    await screen.findByText('Done')
    expect(screen.queryByText('Work completed')).not.toBeInTheDocument()
  })

  it('keeps mobile tool activity closed until the user opens it', async () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/v1/conversations' && !init?.method) return new Response('[]', { status: 200 })
      if (url === '/api/v1/conversations' && init?.method === 'POST') return new Response(JSON.stringify(summaryB), { status: 201 })
      if (url === '/api/v1/conversations/conversation-b/turns') return new Response(JSON.stringify({ turn_id: 'turn-mobile' }), { status: 201 })
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    vi.stubGlobal('crypto', { randomUUID: () => 'local-mobile' })

    render(<AppShell />)
    await userEvent.type(screen.getByLabelText('Message Jarvis'), 'Mobile tool{enter}')
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    act(() => MockEventSource.instances[0].emit('tool.started', { turn_id: 'turn-mobile', sequence: 1, type: 'tool.started', operation_id: 1, category: 'exec', capability: 'run_python' }))

    expect(screen.queryByRole('dialog', { name: 'Work' })).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/Working through the calculation|Analyzing the data/))
    await userEvent.click(screen.getByRole('button', { name: 'Open work panel' }))
    const dialog = screen.getByRole('dialog', { name: 'Work' })
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveTextContent('Run Python')
  })

  it('wires Work Panel Stop to synchronous cancellation and shows Stopping', async () => {
    let resolveCancel!: (response: Response) => void
    const cancelResponse = new Promise<Response>((resolve) => { resolveCancel = resolve })
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/v1/conversations' && !init?.method) return new Response('[]', { status: 200 })
      if (url === '/api/v1/conversations' && init?.method === 'POST') return new Response(JSON.stringify(summaryB), { status: 201 })
      if (url === '/api/v1/conversations/conversation-b/turns') return new Response(JSON.stringify({ turn_id: 'turn-stop' }), { status: 201 })
      if (url === '/api/v1/turns/turn-stop/cancel') return cancelResponse
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    vi.stubGlobal('crypto', { randomUUID: () => 'local-stop' })

    render(<AppShell />)
    await userEvent.type(screen.getByLabelText('Message Jarvis'), 'Stop this{enter}')
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    const stream = MockEventSource.instances[0]
    act(() => stream.emit('tool.started', { turn_id: 'turn-stop', sequence: 1, type: 'tool.started', operation_id: 1, category: 'exec', capability: 'run_python' }))
    const stop = await screen.findByRole('button', { name: 'Stop' })
    await userEvent.click(stop)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/turns/turn-stop/cancel', expect.objectContaining({ method: 'POST' }))
    expect(screen.getByRole('button', { name: 'Stopping' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Stopping response' })).toBeDisabled()

    resolveCancel(new Response(JSON.stringify({ status: 'cancelled' }), { status: 200 }))
    act(() => stream.emit('turn.cancelled', { turn_id: 'turn-stop', sequence: 2, type: 'turn.cancelled' }))
    await waitFor(() => expect(screen.getAllByText('Cancelled').length).toBeGreaterThan(0))
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument()
  })
})
