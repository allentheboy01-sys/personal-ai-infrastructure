import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useJarvisChat } from './useJarvisChat'

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

const canonical = {
  id: 'conversation-1', title: 'Hello', created_at: '2026-08-19T00:00:00Z', updated_at: '2026-08-19T00:00:01Z', archived_at: null,
  messages: [
    { id: 'user-1', role: 'user', body: 'Hello', created_at: '2026-08-19T00:00:00Z', resource_refs: [], resources: [] },
    { id: 'assistant-1', role: 'assistant', body: 'Canonical response', created_at: '2026-08-19T00:00:01Z', resource_refs: [], resources: [] },
  ],
}

const runningTurn = (id: string, conversationId: string, phase = 'thinking') => ({
  id, conversation_id: conversationId, user_message_id: `user-${id}`, assistant_message_id: null, status: 'running',
  started_at: '2026-08-19T00:00:00Z', completed_at: null, error_code: null, sequence: 1, phase, provisional_text: null,
})

function Harness({ conversationId = null, turnId = null }: { conversationId?: string | null; turnId?: string | null }) {
  const chat = useJarvisChat(conversationId, turnId)
  return <div>
    <button onClick={() => void chat.submit('Hello')}>Submit</button>
    <button onClick={() => void chat.submit('Message B')}>Submit B</button>
    <button onClick={chat.resetConversation}>New</button>
    <button onClick={() => void chat.selectConversation('conversation-a')}>Open A</button>
    <button onClick={() => void chat.selectConversation('conversation-b')}>Open B</button>
    <button onClick={() => void chat.cancel()}>Stop current</button>
    <span data-testid="running-status">{chat.running ? 'running' : 'idle'}</span>
    <span data-testid="conversation-id">{chat.conversationId ?? 'none'}</span>
    <span data-testid="conversation-title">{chat.conversationTitle ?? 'untitled'}</span>
    <span data-testid="trace-status">{chat.executionTrace?.status ?? 'none'}</span>
    <span data-testid="active-turn">{chat.activeTurnId ?? 'none'}</span>
    <span data-testid="progress-state">{chat.progress ?? 'none'}</span>
    <span>{chat.cancelling ? 'stopping' : 'not-stopping'}</span>
    {chat.executionTrace?.steps.map((step) => <span key={step.id}>{step.label}:{step.detail}</span>)}
    {chat.messages.map((message) => <p key={message.id}>{message.body}</p>)}
  </div>
}

describe('persistent Chat boundary', () => {
  afterEach(() => { vi.unstubAllGlobals(); MockEventSource.instances = [] })

  it('streams through the mock runtime boundary and reloads canonical messages', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...canonical, messages: undefined }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ turn_id: 'turn-1' }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(canonical), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(canonical), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    vi.stubGlobal('crypto', { randomUUID: () => 'local-1' })

    const first = render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }))
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    const stream = MockEventSource.instances[0]
    expect(stream.url).toBe('/api/v1/turns/turn-1/events')
    act(() => stream.emit('message.delta', { turn_id: 'turn-1', sequence: 5, type: 'message.delta', delta: 'Draft' }))
    expect(screen.getByText('Draft')).toBeInTheDocument()
    act(() => stream.emit('turn.completed', { turn_id: 'turn-1', sequence: 6, type: 'turn.completed' }))
    await screen.findByText('Canonical response')
    expect(screen.getByText('idle')).toBeInTheDocument()
    expect(screen.getByTestId('progress-state')).toHaveTextContent('none')
    first.unmount()

    render(<Harness conversationId="conversation-1" />)
    await screen.findByText('Canonical response')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/conversations/conversation-1', { cache: 'no-store' })
  })

  it('reconnects an active turn after refresh without cancelling it', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/v1/conversations/conversation-1') return new Response(JSON.stringify({ ...canonical, messages: canonical.messages.slice(0, 1) }), { status: 200 })
      if (url === '/api/v1/turns/turn-active') return new Response(JSON.stringify(runningTurn('turn-active', 'conversation-1', 'searching')), { status: 200 })
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    render(<Harness conversationId="conversation-1" turnId="turn-active" />)
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    expect(MockEventSource.instances[0].url).toBe('/api/v1/turns/turn-active/events')
    expect(screen.getByTestId('running-status')).toHaveTextContent('running')
    expect(screen.getByTestId('progress-state')).toHaveTextContent('searching')
  })

  it('keeps a Turn running across Conversation navigation and reconnects on return', async () => {
    const detailA = { ...canonical, id: 'conversation-a', title: 'Conversation A', messages: canonical.messages.slice(0, 1) }
    const detailB = { ...canonical, id: 'conversation-b', title: 'Conversation B', messages: [{ ...canonical.messages[0], id: 'user-b', body: 'History B' }] }
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/v1/conversations/conversation-a') return new Response(JSON.stringify(detailA), { status: 200 })
      if (url === '/api/v1/conversations/conversation-b') return new Response(JSON.stringify(detailB), { status: 200 })
      if (url === '/api/v1/turns/turn-a') return new Response(JSON.stringify(runningTurn('turn-a', 'conversation-a')), { status: 200 })
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)

    render(<Harness conversationId="conversation-a" turnId="turn-a" />)
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    const firstStream = MockEventSource.instances[0]
    fireEvent.click(screen.getByRole('button', { name: 'Open B' }))
    await screen.findByText('History B')

    expect(firstStream.readyState).toBe(MockEventSource.CLOSED)
    expect(screen.getByTestId('running-status')).toHaveTextContent('idle')
    expect(screen.getByTestId('progress-state')).toHaveTextContent('none')
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/cancel'))).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'Open A' }))
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(2))
    expect(MockEventSource.instances[1].url).toBe('/api/v1/turns/turn-a/events')
    expect(screen.getByTestId('running-status')).toHaveTextContent('running')
    expect(screen.getByTestId('active-turn')).toHaveTextContent('turn-a')
    expect(screen.getByTestId('progress-state')).toHaveTextContent('processing')
    expect(window.location.search).toContain('turn=turn-a')
  })

  it('reloads canonical completion when a background Turn finishes while another Conversation is viewed', async () => {
    let turnStatus = 'running'
    const runningA = { ...canonical, id: 'conversation-a', title: 'Conversation A', messages: canonical.messages.slice(0, 1) }
    const completedA = { ...canonical, id: 'conversation-a', title: 'Conversation A' }
    const detailB = { ...canonical, id: 'conversation-b', title: 'Conversation B', messages: [{ ...canonical.messages[0], id: 'user-b', body: 'History B' }] }
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/v1/conversations/conversation-a') return new Response(JSON.stringify(turnStatus === 'running' ? runningA : completedA), { status: 200 })
      if (url === '/api/v1/conversations/conversation-b') return new Response(JSON.stringify(detailB), { status: 200 })
      if (url === '/api/v1/turns/turn-a') return new Response(JSON.stringify({ ...runningTurn('turn-a', 'conversation-a'), status: turnStatus, completed_at: turnStatus === 'completed' ? '2026-08-19T00:00:02Z' : null }), { status: 200 })
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)

    render(<Harness conversationId="conversation-a" turnId="turn-a" />)
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    fireEvent.click(screen.getByRole('button', { name: 'Open B' }))
    await screen.findByText('History B')
    turnStatus = 'completed'
    fireEvent.click(screen.getByRole('button', { name: 'Open A' }))

    expect(await screen.findByText('Canonical response')).toBeInTheDocument()
    expect(screen.getByTestId('running-status')).toHaveTextContent('idle')
    expect(screen.getByTestId('active-turn')).toHaveTextContent('none')
    expect(MockEventSource.instances).toHaveLength(1)
  })

  it('cancels only the exact currently viewed Turn when other Conversations are running', async () => {
    const details = new Map([
      ['conversation-a', { ...canonical, id: 'conversation-a', title: 'Conversation A', messages: canonical.messages.slice(0, 1) }],
      ['conversation-b', { ...canonical, id: 'conversation-b', title: 'Conversation B', messages: [{ ...canonical.messages[0], id: 'user-b', body: 'History B' }] }],
    ])
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/v1/conversations/conversation-a') return new Response(JSON.stringify(details.get('conversation-a')), { status: 200 })
      if (url === '/api/v1/conversations/conversation-b') return new Response(JSON.stringify(details.get('conversation-b')), { status: 200 })
      if (url === '/api/v1/turns/turn-a' && !init?.method) return new Response(JSON.stringify(runningTurn('turn-a', 'conversation-a')), { status: 200 })
      if (url === '/api/v1/conversations/conversation-b/turns') return new Response(JSON.stringify({ turn_id: 'turn-b' }), { status: 201 })
      if (url === '/api/v1/turns/turn-a/cancel') return new Response(JSON.stringify({ status: 'cancelled' }), { status: 200 })
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    vi.stubGlobal('crypto', { randomUUID: () => 'local-b' })

    render(<Harness conversationId="conversation-a" turnId="turn-a" />)
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    fireEvent.click(screen.getByRole('button', { name: 'Open B' }))
    await screen.findByText('History B')
    fireEvent.click(screen.getByRole('button', { name: 'Submit B' }))
    await waitFor(() => expect(screen.getByTestId('active-turn')).toHaveTextContent('turn-b'))
    fireEvent.click(screen.getByRole('button', { name: 'Open A' }))
    await waitFor(() => expect(screen.getByTestId('active-turn')).toHaveTextContent('turn-a'))
    fireEvent.click(screen.getByRole('button', { name: 'Stop current' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/turns/turn-a/cancel', expect.objectContaining({ method: 'POST' })))
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/v1/turns/turn-b/cancel')).toBe(false)
  })

  it('does not reuse the previous conversation after New conversation', async () => {
    const conversationA = { ...canonical, id: 'conversation-a', title: 'Conversation A', messages: [{ ...canonical.messages[0], id: 'message-a', body: 'History A' }] }
    const conversationB = { id: 'conversation-b', title: 'Message B', created_at: canonical.created_at, updated_at: canonical.updated_at, archived_at: null }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(conversationA), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(conversationB), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ turn_id: 'turn-b' }), { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)
    vi.stubGlobal('crypto', { randomUUID: () => 'local-b' })

    render(<Harness conversationId="conversation-a" />)
    await screen.findByText('History A')
    fireEvent.click(screen.getByRole('button', { name: 'New' }))
    expect(screen.queryByText('History A')).not.toBeInTheDocument()
    expect(screen.getByTestId('conversation-id')).toHaveTextContent('none')
    fireEvent.click(screen.getByRole('button', { name: 'Submit B' }))

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    expect(screen.getByTestId('conversation-id')).toHaveTextContent('conversation-b')
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/conversations', expect.objectContaining({ method: 'POST', body: JSON.stringify({ title: 'Message B' }) }))
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/v1/conversations/conversation-b/turns', expect.objectContaining({ method: 'POST' }))
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/v1/conversations/conversation-a/turns')).toBe(false)
  })

  it('switches exact canonical histories without merging stale messages', async () => {
    let resolveA!: (response: Response) => void
    const deferredA = new Promise<Response>((resolve) => { resolveA = resolve })
    const conversationB = { ...canonical, id: 'conversation-b', title: 'Conversation B', messages: [{ ...canonical.messages[0], id: 'message-b', body: 'History B' }] }
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => deferredA)
      .mockResolvedValueOnce(new Response(JSON.stringify(conversationB), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)

    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'Open A' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open B' }))
    await screen.findByText('History B')
    resolveA(new Response(JSON.stringify({ ...canonical, id: 'conversation-a', title: 'Conversation A', messages: [{ ...canonical.messages[0], id: 'message-a', body: 'History A' }] }), { status: 200 }))
    await act(async () => { await deferredA })

    expect(screen.queryByText('History A')).not.toBeInTheDocument()
    expect(screen.getByTestId('conversation-id')).toHaveTextContent('conversation-b')
    expect(screen.getByTestId('conversation-title')).toHaveTextContent('Conversation B')
  })

  it('tracks sanitized tool events and clears the trace on Conversation change', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/v1/conversations/conversation-1') return new Response(JSON.stringify(canonical), { status: 200 })
      if (url === '/api/v1/turns/turn-active') return new Response(JSON.stringify(runningTurn('turn-active', 'conversation-1')), { status: 200 })
      if (url === '/api/v1/conversations/conversation-a') return new Response(JSON.stringify({ ...canonical, id: 'conversation-a' }), { status: 200 })
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', MockEventSource)

    render(<Harness conversationId="conversation-1" turnId="turn-active" />)
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    const stream = MockEventSource.instances[0]
    act(() => stream.emit('turn.started', { turn_id: 'turn-active', sequence: 1, type: 'turn.started' }))
    expect(screen.getByTestId('progress-state')).toHaveTextContent('processing')
    act(() => stream.emit('tool.started', { turn_id: 'turn-active', sequence: 2, type: 'tool.started', operation_id: 1, category: 'pdi', capability: 'search_personal_resources', arguments: 'private', result: 'private', resource_refs: ['pdi:resource:private'] }))
    expect(screen.getByTestId('progress-state')).toHaveTextContent('searching')
    act(() => stream.emit('tool.completed', { turn_id: 'turn-active', sequence: 3, type: 'tool.completed', operation_id: 1, category: 'pdi', capability: 'search_personal_resources', duration_ms: 20, result: 'private' }))
    expect(screen.getByTestId('progress-state')).toHaveTextContent('search_complete')
    expect(screen.queryByText(/private/)).not.toBeInTheDocument()
    act(() => stream.emit('tool.started', { turn_id: 'turn-active', sequence: 4, type: 'tool.started', operation_id: 2, category: 'exec', capability: 'run_python' }))
    act(() => stream.emit('tool.completed', { turn_id: 'turn-active', sequence: 5, type: 'tool.completed', operation_id: 2, category: 'exec', capability: 'run_python', duration_ms: 42 }))
    expect(screen.getByText('Run Python:Finished · 42 ms')).toBeInTheDocument()
    expect(screen.getByTestId('progress-state')).toHaveTextContent('reviewing')
    act(() => stream.emit('phase.changed', { turn_id: 'turn-active', sequence: 6, type: 'phase.changed', phase: 'composing' }))
    expect(screen.getByTestId('progress-state')).toHaveTextContent('composing')
    expect(screen.getByTestId('trace-status')).toHaveTextContent('running')

    fireEvent.click(screen.getByRole('button', { name: 'Open A' }))
    await screen.findByText('Canonical response')
    expect(screen.getByTestId('trace-status')).toHaveTextContent('none')
    expect(screen.queryByText(/Run Python/)).not.toBeInTheDocument()
  })
})
