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
})
