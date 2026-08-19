export interface ApiMessage {
  id: string
  role: 'user' | 'assistant'
  body: string
  created_at: string
  resource_refs: Array<{ resource_ref: string; ordinal: number }>
}

export interface ApiConversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  archived_at: string | null
  messages: ApiMessage[]
}

export interface RuntimeEvent {
  turn_id: string
  sequence: number
  type: 'turn.started' | 'phase.changed' | 'message.delta' | 'turn.completed' | 'turn.failed' | 'turn.cancelled'
  phase?: 'thinking' | 'searching' | 'reviewing' | 'computing' | 'composing'
  delta?: string
  error_code?: string
}

const writeHeaders = { 'Content-Type': 'application/json', 'X-Jarvis-Request': 'web-v1' }

async function json<T>(request: Promise<Response>): Promise<T> {
  const response = await request
  if (!response.ok) throw new Error(`jarvis_api_${response.status}`)
  return response.json() as Promise<T>
}

export const jarvisApi = {
  createConversation: (title: string) => json<{ id: string }>(fetch('/api/v1/conversations', { method: 'POST', headers: writeHeaders, body: JSON.stringify({ title }) })),
  getConversation: (id: string) => json<ApiConversation>(fetch(`/api/v1/conversations/${encodeURIComponent(id)}`, { cache: 'no-store' })),
  createTurn: (conversationId: string, body: string) => json<{ turn_id: string }>(fetch(`/api/v1/conversations/${encodeURIComponent(conversationId)}/turns`, { method: 'POST', headers: writeHeaders, body: JSON.stringify({ body }) })),
  cancelTurn: (turnId: string) => json<{ status: string }>(fetch(`/api/v1/turns/${encodeURIComponent(turnId)}/cancel`, { method: 'POST', headers: writeHeaders, body: '{}' })),
  eventsUrl: (turnId: string) => `/api/v1/turns/${encodeURIComponent(turnId)}/events`,
}
