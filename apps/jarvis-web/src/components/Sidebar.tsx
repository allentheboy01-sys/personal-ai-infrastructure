import { useEffect, useRef } from 'react'
import { Archive, LoaderCircle, MessageCircle, PanelLeftClose, Plus, Radio } from 'lucide-react'
import type { ApiConversationSummary } from '../api/jarvis'
import { JarvisMark } from './JarvisMark'

export type AppPage = 'chat' | 'resources' | 'providers'

const nav = [
  { id: 'chat' as const, label: 'Chat', icon: MessageCircle },
  { id: 'resources' as const, label: 'Resources', icon: Archive },
  { id: 'providers' as const, label: 'Providers', icon: Radio },
]

const reviewRecent = [
  { id: 'review-interface', title: 'Interface review', label: 'Today' },
  { id: 'review-trip', title: 'Trip references', label: 'Yesterday' },
  { id: 'review-reading', title: 'Reading notes', label: 'Aug 16' },
]

function dateLabel(value: string) {
  const date = new Date(value)
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const difference = Math.round((start - day) / 86_400_000)
  if (difference === 0) return 'Today'
  if (difference === 1) return 'Yesterday'
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date)
}

interface SidebarProps {
  page: AppPage
  onNavigate: (page: AppPage) => void
  onNewConversation: () => void
  conversations?: ApiConversationSummary[]
  activeConversationId?: string | null
  runningConversationIds?: ReadonlySet<string>
  onConversation?: (id: string) => void
  onClose?: () => void
  compact?: boolean
  review?: boolean
}

const noRunningConversations: ReadonlySet<string> = new Set()

export function Sidebar({ page, onNavigate, onNewConversation, conversations = [], activeConversationId, runningConversationIds = noRunningConversations, onConversation, onClose, compact = false, review = false }: SidebarProps) {
  const recent = review ? reviewRecent : conversations.map((conversation) => ({ id: conversation.id, title: conversation.title, label: dateLabel(conversation.updated_at) }))
  const listRef = useRef<HTMLDivElement>(null)
  const selectedRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const list = listRef.current
    const selected = selectedRef.current
    if (!list || !selected) return
    const listBounds = list.getBoundingClientRect()
    const selectedBounds = selected.getBoundingClientRect()
    if (selectedBounds.top < listBounds.top || selectedBounds.bottom > listBounds.bottom) selected.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [activeConversationId, recent.length])

  return (
    <aside className={`sidebar ${compact ? 'compact' : ''}`} aria-label="Jarvis sidebar">
      <div className="brand-row">
        <span className="brand-symbol" aria-hidden="true"><JarvisMark size={19} /></span>
        <span className="brand-name">Jarvis</span>
        {onClose && <button className="icon-button drawer-close" onClick={onClose} aria-label="Close navigation"><PanelLeftClose size={19} /></button>}
      </div>
      <button className="new-chat" onClick={onNewConversation}><Plus size={17} /><span>New conversation</span></button>
      <nav className="nav-list" aria-label="Primary navigation">
        {nav.map(({ id, label, icon: Icon }) => (
          <button key={id} className={page === id ? 'active' : ''} onClick={() => onNavigate(id)} aria-current={page === id ? 'page' : undefined}>
            <Icon size={18} /><span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="recent-section">
        <p>Recent</p>
        <div className="recent-list" ref={listRef} data-testid="conversation-list">
          {recent.map((conversation) => {
            const selected = conversation.id === activeConversationId
            const running = !review && runningConversationIds.has(conversation.id)
            return <button key={conversation.id} ref={selected ? selectedRef : undefined} className={selected ? 'active' : ''} onClick={() => review ? onNavigate('chat') : onConversation?.(conversation.id)} aria-current={selected ? 'page' : undefined}>
              <span className="conversation-activity-slot" aria-hidden="true">{running && <LoaderCircle className="conversation-running" size={13} />}</span>
              <span className="conversation-title">{conversation.title}</span>
              <small>{conversation.label}</small>
              {running && <span className="sr-only">Running</span>}
            </button>
          })}
          {!review && recent.length === 0 && <span className="recent-empty">No conversations yet</span>}
        </div>
      </div>
      <div className="sidebar-footer"><span className="avatar">HF</span><div><strong>Personal Jarvis</strong><small>Private workspace</small></div></div>
    </aside>
  )
}
