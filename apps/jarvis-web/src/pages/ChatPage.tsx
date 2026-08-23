import { AgentStatus } from '../components/AgentStatus'
import { Composer } from '../components/Composer'
import { Conversation } from '../features/chat/Conversation'
import { useChatAutoFollow } from '../features/chat/useChatAutoFollow'
import { conversation } from '../mocks/chat'
import type { AgentPhase, AgentProgress } from '../models/chat'
import type { ResourceView } from '../models/resource'

interface ChatPageProps {
  working: boolean
  stopping?: boolean
  onResource: (resource: ResourceView) => void
  messages?: typeof conversation
  phase?: AgentPhase
  progress?: AgentProgress | null
  conversationKey?: string | null
  turnStartedAtMs?: number | null
  onSubmit?: (body: string) => void
  onStop?: () => void
}

export function ChatPage({ working, stopping = false, onResource, messages, phase = 'reviewing', progress, conversationKey = null, turnStartedAtMs, onSubmit, onStop }: ChatPageProps) {
  const visibleMessages = messages ?? (working ? conversation.slice(0, 2) : conversation)
  const contentVersion = `${visibleMessages.map((message) => `${message.id}:${message.body.length}:${message.resources?.length ?? 0}`).join('|')}|${working ? progress ?? phase : 'idle'}`
  const { scrollRef, contentRef, newContentPending, onScroll, scrollToLatest } = useChatAutoFollow(contentVersion, conversationKey ?? 'new', working)
  return <main className="chat-page">
    <div className="chat-scroll" ref={scrollRef} onScroll={onScroll}>
      <div className="chat-content" ref={contentRef}>
        <Conversation messages={visibleMessages} onResource={onResource} />
        {working && <div className="conversation-status"><AgentStatus phase={phase} progress={progress ?? undefined} startedAtMs={turnStartedAtMs} /></div>}
      </div>
    </div>
    {newContentPending && <button className="jump-to-latest" type="button" onClick={() => scrollToLatest('smooth')}>Jump to latest</button>}
    <Composer running={working} stopping={stopping} onSubmit={onSubmit} onStop={onStop} />
  </main>
}
