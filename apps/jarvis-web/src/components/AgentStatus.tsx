import { CircleCheck, LoaderCircle } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import type { AgentPhase, AgentProgress } from '../models/chat'

const progressFromPhase: Record<AgentPhase, AgentProgress> = { thinking: 'processing', searching: 'searching', reviewing: 'reviewing', computing: 'computing', composing: 'composing' }
const labels: Record<AgentProgress, string> = {
  processing: 'Working on your request',
  searching: 'Searching your resources',
  search_complete: 'Finished searching, organizing',
  computing: 'Working through the calculation',
  reviewing: 'Reviewing the result',
  composing: 'Composing an answer',
}

export function AgentStatus({ phase, progress, startedAtMs }: { phase: AgentPhase; progress?: AgentProgress; startedAtMs?: number | null }) {
  const reduced = useReducedMotion()
  const [elapsed, setElapsed] = useState(0)
  const state = progress ?? progressFromPhase[phase]

  useEffect(() => {
    if (!startedAtMs) { setElapsed(0); return }
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - startedAtMs) / 1000)))
    update()
    const timer = window.setInterval(update, 1000)
    return () => window.clearInterval(timer)
  }, [startedAtMs])

  return (
    <div className="agent-status" role="status" aria-live="polite">
      <span className="agent-orbit"><LoaderCircle size={17} /></span>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span key={state} initial={reduced ? false : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={reduced ? undefined : { opacity: 0, y: -4 }} transition={{ duration: .18 }}>{labels[state]}{elapsed > 0 && <span className="agent-elapsed"> · {elapsed}s</span>}</motion.span>
      </AnimatePresence>
      <CircleCheck size={15} className="status-check" />
    </div>
  )
}
