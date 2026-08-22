import { Archive, MessageCircle, PanelLeftClose, Plus, Radio } from 'lucide-react'
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
  onConversation?: (id: string) => void
  onClose?: () => void
  compact?: boolean
  review?: boolean
}

export function Sidebar({ page, onNavigate, onNewConversation, conversations = [], activeConversationId, onConversation, onClose, compact = false, review = false }: SidebarProps) {
  const recent = review ? reviewRecent : conversations.map((conversation) => ({ id: conversation.id, title: conversation.title, label: dateLabel(conversation.updated_at) }))
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
        {recent.map((conversation) => <button key={conversation.id} className={conversation.id === activeConversationId ? 'active' : ''} onClick={() => review ? onNavigate('chat') : onConversation?.(conversation.id)} aria-current={conversation.id === activeConversationId ? 'page' : undefined}><span>{conversation.title}</span><small>{conversation.label}</small></button>)}
        {!review && recent.length === 0 && <span className="recent-empty">No conversations yet</span>}
      </div>
      <div className="sidebar-footer"><span className="avatar">HF</span><div><strong>Personal Jarvis</strong><small>Private workspace</small></div></div>
    </aside>
  )
}
