import { CircleCheck, LoaderCircle } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import type { AgentPhase } from '../models/chat'

const labels: Record<AgentPhase, string> = { searching: 'Searching your resources', reviewing: 'Reviewing likely matches', composing: 'Composing an answer' }

export function AgentStatus({ phase }: { phase: AgentPhase }) {
  const reduced = useReducedMotion()
  return (
    <div className="agent-status" role="status" aria-live="polite">
      <span className="agent-orbit"><LoaderCircle size={17} /></span>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span key={phase} initial={reduced ? false : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={reduced ? undefined : { opacity: 0, y: -4 }} transition={{ duration: .18 }}>{labels[phase]}</motion.span>
      </AnimatePresence>
      <CircleCheck size={15} className="status-check" />
    </div>
  )
}
