import { CircleCheck, LoaderCircle } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import type { AgentPhase, AgentProgress } from '../models/chat'
import { progressWording } from '../features/chat/progressWording'

const progressFromPhase: Record<AgentPhase, AgentProgress> = { thinking: 'processing', searching: 'searching', reviewing: 'reviewing', computing: 'computing', composing: 'composing' }
export function AgentStatus({ phase, progress, startedAtMs }: { phase: AgentPhase; progress?: AgentProgress; startedAtMs?: number | null }) {
  const reduced = useReducedMotion()
  const [elapsed, setElapsed] = useState(0)
  const state = progress ?? progressFromPhase[phase]
  const wordingSeed = useRef(String(startedAtMs ?? 'jarvis'))
  const label = progressWording(state, wordingSeed.current)

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
        <motion.span key={state} initial={reduced ? false : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={reduced ? undefined : { opacity: 0, y: -4 }} transition={{ duration: .18 }}>{label}{elapsed > 0 && <span className="agent-elapsed"> · {elapsed}s</span>}</motion.span>
      </AnimatePresence>
      <CircleCheck size={15} className="status-check" />
    </div>
  )
}
