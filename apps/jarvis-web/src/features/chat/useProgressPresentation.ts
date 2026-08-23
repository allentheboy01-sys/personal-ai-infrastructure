import { useCallback, useEffect, useRef, useState } from 'react'
import type { AgentProgress } from '../../models/chat'

export const PROGRESS_MIN_VISIBLE_MS = 320

const transientProgress = new Set<AgentProgress>(['searching', 'computing', 'reviewing'])

export function useProgressPresentation(initialProgress: AgentProgress | null) {
  const [progress, setProgress] = useState<AgentProgress | null>(initialProgress)
  const currentRef = useRef<AgentProgress | null>(initialProgress)
  const shownAtRef = useRef(initialProgress ? Date.now() : 0)
  const queuedRef = useRef<AgentProgress | null>(null)
  const timerRef = useRef<number | null>(null)

  const cancelTimer = useCallback(() => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    timerRef.current = null
  }, [])

  const commit = useCallback((next: AgentProgress | null) => {
    currentRef.current = next
    shownAtRef.current = next ? Date.now() : 0
    setProgress(next)
  }, [])

  const resetProgress = useCallback((next: AgentProgress | null) => {
    cancelTimer()
    queuedRef.current = null
    commit(next)
  }, [cancelTimer, commit])

  const clearProgress = useCallback(() => resetProgress(null), [resetProgress])

  const presentProgress = useCallback((next: AgentProgress) => {
    const current = currentRef.current
    if (current === next) return

    if (current && transientProgress.has(current)) {
      const remaining = PROGRESS_MIN_VISIBLE_MS - (Date.now() - shownAtRef.current)
      if (remaining > 0) {
        queuedRef.current = next
        if (timerRef.current === null) {
          timerRef.current = window.setTimeout(() => {
            timerRef.current = null
            const queued = queuedRef.current
            queuedRef.current = null
            if (queued) commit(queued)
          }, remaining)
        }
        return
      }
    }

    cancelTimer()
    queuedRef.current = null
    commit(next)
  }, [cancelTimer, commit])

  useEffect(() => () => cancelTimer(), [cancelTimer])

  return { progress, presentProgress, resetProgress, clearProgress }
}
