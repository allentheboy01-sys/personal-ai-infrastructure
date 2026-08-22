import * as Dialog from '@radix-ui/react-dialog'
import { Check, Circle, LoaderCircle, Square, X } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import type { ExecutionStep } from '../models/chat'

export type PanelContent = { title: string; eyebrow: string; content: ReactNode }

export function ExecutionPanel({ steps, status = 'running', onStop, stopping = false }: { steps: ExecutionStep[]; status?: 'running' | 'completed' | 'failed' | 'cancelled'; onStop?: () => void; stopping?: boolean }) {
  const summary = status === 'running' ? 'Working across your resources' : status === 'completed' ? 'Work completed' : status === 'cancelled' ? 'Cancelled' : 'Work stopped'
  return <div className="execution-panel"><div className={`execution-summary ${status}`}><span className="live-dot" />{summary}</div><ol>{steps.map((step, index) => <li key={step.id ?? `${step.label}:${index}`} className={step.state}><span className="step-icon">{step.state === 'completed' ? <Check size={14} /> : step.state === 'current' ? <LoaderCircle size={15} /> : <Circle size={13} />}</span><div><strong>{step.label}</strong><p>{step.detail}</p></div></li>)}</ol>{status === 'running' && onStop && <button className="stop-work" onClick={onStop} disabled={stopping}><Square size={12} fill="currentColor" />{stopping ? 'Stopping' : 'Stop'}</button>}</div>
}

function PanelFrame({ panel, onClose, mobile = false }: { panel: PanelContent; onClose: () => void; mobile?: boolean }) {
  return <div className={`work-panel ${mobile ? 'mobile' : ''}`}><header><div><span>{panel.eyebrow}</span><h2>{panel.title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close work panel"><X size={19} /></button></header><div className="work-panel-scroll">{panel.content}</div></div>
}

export function WorkPanel({ panel, onClose }: { panel: PanelContent | null; onClose: () => void }) {
  const reduced = useReducedMotion()
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 820px)').matches)

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(max-width: 820px)')
    const update = () => setMobile(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  return <>
    <div className="desktop-panel-slot"><AnimatePresence>{panel && <motion.div className="desktop-panel-motion" initial={reduced ? false : { opacity: 0, x: 28 }} animate={{ opacity: 1, x: 0 }} exit={reduced ? undefined : { opacity: 0, x: 24 }} transition={{ duration: .22, ease: 'easeOut' }}><PanelFrame panel={panel} onClose={onClose} /></motion.div>}</AnimatePresence></div>
    <Dialog.Root open={Boolean(panel) && mobile} onOpenChange={(open) => { if (!open && mobile) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="mobile-panel-overlay" />
        {panel && mobile && <Dialog.Content className="mobile-panel-content" aria-describedby={undefined}><Dialog.Title className="sr-only">{panel.title}</Dialog.Title><PanelFrame panel={panel} onClose={onClose} mobile /></Dialog.Content>}
      </Dialog.Portal>
    </Dialog.Root>
  </>
}
