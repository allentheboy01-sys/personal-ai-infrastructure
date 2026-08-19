import { useState } from 'react'
import { AgentStatus } from '../components/AgentStatus'
import { Composer } from '../components/Composer'
import { Conversation } from '../features/chat/Conversation'
import { conversation } from '../mocks/chat'
import type { AgentPhase } from '../models/chat'
import type { ResourceView } from '../models/resource'

export function ChatPage({ working, onResource }: { working: boolean; onResource: (resource: ResourceView) => void }) {
  const [phase] = useState<AgentPhase>('reviewing')
  return <main className="chat-page"><div className="chat-scroll"><Conversation messages={working ? conversation.slice(0, 2) : conversation} onResource={onResource} />{working && <div className="conversation-status"><AgentStatus phase={phase} /></div>}</div><Composer running={working} /></main>
}
