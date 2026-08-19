import * as Dialog from '@radix-ui/react-dialog'
import { Check, Circle, LoaderCircle, Square, X } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import type { ExecutionStep } from '../models/chat'

export type PanelContent = { title: string; eyebrow: string; content: ReactNode }

export function ExecutionPanel({ steps }: { steps: ExecutionStep[] }) {
  return <div className="execution-panel"><div className="execution-summary"><span className="live-dot" />Working across your resources</div><ol>{steps.map((step) => <li key={step.label} className={step.state}><span className="step-icon">{step.state === 'completed' ? <Check size={14} /> : step.state === 'current' ? <LoaderCircle size={15} /> : <Circle size={13} />}</span><div><strong>{step.label}</strong><p>{step.detail}</p></div></li>)}</ol><button className="stop-work"><Square size={12} fill="currentColor" />Stop</button></div>
}

function PanelFrame({ panel, onClose, mobile = false }: { panel: PanelContent; onClose: () => void; mobile?: boolean }) {
  return <div className={`work-panel ${mobile ? 'mobile' : ''}`}><header><div><span>{panel.eyebrow}</span><h2>{panel.title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close work panel"><X size={19} /></button></header><div className="work-panel-scroll">{panel.content}</div></div>
}

export function WorkPanel({ panel, onClose }: { panel: PanelContent | null; onClose: () => void }) {
  const reduced = useReducedMotion()
  return <>
    <div className="desktop-panel-slot"><AnimatePresence>{panel && <motion.div className="desktop-panel-motion" initial={reduced ? false : { opacity: 0, x: 28 }} animate={{ opacity: 1, x: 0 }} exit={reduced ? undefined : { opacity: 0, x: 24 }} transition={{ duration: .22, ease: 'easeOut' }}><PanelFrame panel={panel} onClose={onClose} /></motion.div>}</AnimatePresence></div>
    <Dialog.Root open={Boolean(panel)} onOpenChange={(open) => { if (!open) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="mobile-panel-overlay" />
        {panel && <Dialog.Content className="mobile-panel-content" aria-describedby={undefined}><Dialog.Title className="sr-only">{panel.title}</Dialog.Title><PanelFrame panel={panel} onClose={onClose} mobile /></Dialog.Content>}
      </Dialog.Portal>
    </Dialog.Root>
  </>
}
