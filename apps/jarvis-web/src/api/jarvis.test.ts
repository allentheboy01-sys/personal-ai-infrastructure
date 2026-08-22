import { afterEach, describe, expect, it, vi } from 'vitest'
import { jarvisApi } from './jarvis'

describe('Jarvis API boundary', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses same-origin JSON writes with the CSRF marker', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'conversation-1' }), { status: 201, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await jarvisApi.createConversation('A conversation')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/conversations', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Jarvis-Request': 'web-v1' },
    }))
  })

  it('lists canonical conversations without a frontend-local store', async () => {
    const conversations = [{ id: 'conversation-1', title: 'Canonical title', created_at: '2026-08-22T00:00:00Z', updated_at: '2026-08-22T00:00:00Z', archived_at: null }]
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(conversations), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(jarvisApi.listConversations()).resolves.toEqual(conversations)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/conversations', { cache: 'no-store' })
  })
})
