import type { ConversationMessage, ExecutionStep } from '../models/chat'
import { resources } from './resources'

export const conversation: ConversationMessage[] = [
  { id: 'm1', role: 'user', body: 'Find the notes and messages related to the recent interface review.' },
  {
    id: 'm2', role: 'assistant',
    body: 'I found a small set of related resources across your documents, messages, and photos. The research notes and design review message look most relevant.',
    resources: resources.slice(0, 3), moreCount: 2,
  },
  { id: 'm3', role: 'user', body: 'Give me the concise version and keep the source material nearby.' },
  {
    id: 'm4', role: 'assistant',
    body: 'The review converged on three ideas: keep the primary surface conversational, reveal execution only when it helps, and treat every resource consistently regardless of where it came from.',
    resources: [resources[1], resources[2]],
  },
]

export const executionSteps: ExecutionStep[] = [
  { label: 'Understand the request', detail: 'Identify the topic and likely resource types.', state: 'completed' },
  { label: 'Search your resources', detail: 'Look across connected read-only sources.', state: 'completed' },
  { label: 'Review likely matches', detail: 'Compare titles, dates, and available context.', state: 'current' },
  { label: 'Compose a grounded answer', detail: 'Summarize with the relevant resources nearby.', state: 'pending' },
]
