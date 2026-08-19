import { AgentStatus } from '../components/AgentStatus'
import { Composer } from '../components/Composer'
import { Conversation } from '../features/chat/Conversation'
import { conversation } from '../mocks/chat'
import type { AgentPhase } from '../models/chat'
import type { ResourceView } from '../models/resource'

export function ChatPage({ working, onResource, messages, phase = 'reviewing', onSubmit, onStop }: { working: boolean; onResource: (resource: ResourceView) => void; messages?: typeof conversation; phase?: AgentPhase; onSubmit?: (body: string) => void; onStop?: () => void }) {
  const visibleMessages = messages ?? (working ? conversation.slice(0, 2) : conversation)
  return <main className="chat-page"><div className="chat-scroll"><Conversation messages={visibleMessages} onResource={onResource} />{working && <div className="conversation-status"><AgentStatus phase={phase} /></div>}</div><Composer running={working} onSubmit={onSubmit} onStop={onStop} /></main>
}
