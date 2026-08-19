import { Archive, MessageCircle, PanelLeftClose, Plus, Radio } from 'lucide-react'
import { JarvisMark } from './JarvisMark'

export type AppPage = 'chat' | 'resources' | 'providers'

const nav = [
  { id: 'chat' as const, label: 'Chat', icon: MessageCircle },
  { id: 'resources' as const, label: 'Resources', icon: Archive },
  { id: 'providers' as const, label: 'Providers', icon: Radio },
]

export function Sidebar({ page, onNavigate, onClose, compact = false }: { page: AppPage; onNavigate: (page: AppPage) => void; onClose?: () => void; compact?: boolean }) {
  return (
    <aside className={`sidebar ${compact ? 'compact' : ''}`} aria-label="Jarvis sidebar">
      <div className="brand-row">
        <span className="brand-symbol" aria-hidden="true"><JarvisMark size={19} /></span>
        <span className="brand-name">Jarvis</span>
        {onClose && <button className="icon-button drawer-close" onClick={onClose} aria-label="Close navigation"><PanelLeftClose size={19} /></button>}
      </div>
      <button className="new-chat" onClick={() => onNavigate('chat')}><Plus size={17} /><span>New conversation</span></button>
      <nav className="nav-list" aria-label="Primary navigation">
        {nav.map(({ id, label, icon: Icon }) => (
          <button key={id} className={page === id ? 'active' : ''} onClick={() => onNavigate(id)} aria-current={page === id ? 'page' : undefined}>
            <Icon size={18} /><span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="recent-section">
        <p>Recent</p>
        <button onClick={() => onNavigate('chat')}><span>Interface review</span><small>Today</small></button>
        <button onClick={() => onNavigate('chat')}><span>Trip references</span><small>Yesterday</small></button>
        <button onClick={() => onNavigate('chat')}><span>Reading notes</span><small>Aug 16</small></button>
      </div>
      <div className="sidebar-footer"><span className="avatar">HF</span><div><strong>Personal Jarvis</strong><small>Private workspace</small></div></div>
    </aside>
  )
}
