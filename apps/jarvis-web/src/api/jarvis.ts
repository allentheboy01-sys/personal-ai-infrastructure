export interface ApiMessage {
  id: string
  role: 'user' | 'assistant'
  body: string
  created_at: string
  resource_refs: Array<{ resource_ref: string; ordinal: number }>
  resources: ApiResourceSummary[]
}

export interface ApiResourceSummary {
  resource_ref: `pdi:resource:${string}`
  resource_type: 'file' | 'message'
  title: string
  secondary_text: string | null
  timestamp: string | null
  presentation_kind: 'image' | 'document' | 'message' | 'generic'
  presentation_label: string
  providers: string[]
  capabilities: { detail: boolean; preview: boolean; open: boolean }
}

export interface ApiResourceDetail { summary: ApiResourceSummary; facts: Array<[string, string]>; mime_type: string | null; size_bytes: number | null; notice: string | null }
export interface ApiProviderSummary { provider_ref: 'gmail' | 'immich' | 'nextcloud'; provider_type: string; display_name: string; category: string; configured: boolean; access_mode: 'read_only' | 'read_write' | 'unknown'; resource_count: number; operational_state: 'not_synced' | 'syncing' | 'processing' | 'ready' | 'attention'; last_success_at: string | null }
export interface ApiProviderDetail { summary: ApiProviderSummary; description: string; capabilities: string[]; stages: Array<[string, 'completed' | 'current' | 'pending' | 'attention']> }

export interface ApiConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface ApiConversation extends ApiConversationSummary {
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
  listConversations: () => json<ApiConversationSummary[]>(fetch('/api/v1/conversations', { cache: 'no-store' })),
  createConversation: (title: string) => json<ApiConversationSummary>(fetch('/api/v1/conversations', { method: 'POST', headers: writeHeaders, body: JSON.stringify({ title }) })),
  getConversation: (id: string) => json<ApiConversation>(fetch(`/api/v1/conversations/${encodeURIComponent(id)}`, { cache: 'no-store' })),
  createTurn: (conversationId: string, body: string) => json<{ turn_id: string }>(fetch(`/api/v1/conversations/${encodeURIComponent(conversationId)}/turns`, { method: 'POST', headers: writeHeaders, body: JSON.stringify({ body }) })),
  cancelTurn: (turnId: string) => json<{ status: string }>(fetch(`/api/v1/turns/${encodeURIComponent(turnId)}/cancel`, { method: 'POST', headers: writeHeaders, body: '{}' })),
  eventsUrl: (turnId: string) => `/api/v1/turns/${encodeURIComponent(turnId)}/events`,
  listResources: (query?: string) => json<{ resources: ApiResourceSummary[]; next_cursor: string | null }>(fetch(`/api/v1/resources${query ? `?query=${encodeURIComponent(query)}` : ''}`, { cache: 'no-store' })),
  getResource: (resourceRef: string) => json<ApiResourceDetail>(fetch(`/api/v1/resources/${encodeURIComponent(resourceRef)}`, { cache: 'no-store' })),
  listProviders: () => json<ApiProviderSummary[]>(fetch('/api/v1/providers', { cache: 'no-store' })),
  getProvider: (providerRef: string) => json<ApiProviderDetail>(fetch(`/api/v1/providers/${encodeURIComponent(providerRef)}`, { cache: 'no-store' })),
}
