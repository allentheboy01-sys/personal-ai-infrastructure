import type { ResourceView } from './resource'

export type AgentPhase = 'thinking' | 'searching' | 'reviewing' | 'computing' | 'composing'

export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant'
  body: string
  resources?: ResourceView[]
  moreCount?: number
}

export interface ExecutionStep {
  label: string
  detail: string
  state: 'completed' | 'current' | 'pending'
}
