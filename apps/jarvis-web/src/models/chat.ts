import type { ResourceView } from './resource'

export type AgentPhase = 'thinking' | 'searching' | 'reviewing' | 'computing' | 'composing'

export type AgentProgress = 'processing' | 'searching' | 'search_complete' | 'computing' | 'reviewing' | 'composing'

export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant'
  body: string
  resources?: ResourceView[]
  moreCount?: number
}

export interface ExecutionStep {
  id?: string
  label: string
  detail: string
  state: 'completed' | 'current' | 'pending' | 'failed' | 'cancelled'
}
