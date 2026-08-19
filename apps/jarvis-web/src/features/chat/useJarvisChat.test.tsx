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

function Harness({ conversationId = null, turnId = null }: { conversationId?: string | null; turnId?: string | null }) {
  const chat = useJarvisChat(conversationId, turnId)
  return <div><button onClick={() => void chat.submit('Hello')}>Submit</button><span>{chat.running ? 'running' : 'idle'}</span>{chat.messages.map((message) => <p key={message.id}>{message.body}</p>)}</div>
}

describe('persistent Chat boundary', () => {
  afterEach(() => { vi.unstubAllGlobals(); MockEventSource.instances = [] })

  it('streams through the mock runtime boundary and reloads canonical messages', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'conversation-1' }), { status: 201 }))
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
    first.unmount()

    render(<Harness conversationId="conversation-1" />)
    await screen.findByText('Canonical response')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/conversations/conversation-1', { cache: 'no-store' })
  })

  it('reconnects an active turn after refresh without cancelling it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...canonical, messages: canonical.messages.slice(0, 1) }), { status: 200 })))
    vi.stubGlobal('EventSource', MockEventSource)
    render(<Harness conversationId="conversation-1" turnId="turn-active" />)
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    expect(MockEventSource.instances[0].url).toBe('/api/v1/turns/turn-active/events')
    expect(screen.getByText('running')).toBeInTheDocument()
  })
})
