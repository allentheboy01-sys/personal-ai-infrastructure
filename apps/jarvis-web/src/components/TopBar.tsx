import { Menu, PanelRight } from 'lucide-react'
import { JarvisMark } from './JarvisMark'

export function TopBar({ title, eyebrow, onMenu, onPanel, panelAvailable = false }: { title: string; eyebrow?: string; onMenu: () => void; onPanel?: () => void; panelAvailable?: boolean }) {
  return (
    <header className="topbar">
      <button className="icon-button mobile-menu" onClick={onMenu} aria-label="Open navigation"><Menu size={20} /></button>
      <div className="topbar-title">
        {eyebrow && <span>{eyebrow}</span>}
        <h1>{title}</h1>
      </div>
      <div className="topbar-mark" aria-hidden="true"><JarvisMark size={17} /></div>
      {panelAvailable && <button className="icon-button topbar-panel" onClick={onPanel} aria-label="Open work panel"><PanelRight size={19} /></button>}
    </header>
  )
}
