import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

const NEAR_BOTTOM_PX = 96
const PROGRAMMATIC_SCROLL_FALLBACK_MS = 800

function isNearBottom(element: HTMLElement) {
  return element.scrollHeight - element.scrollTop - element.clientHeight <= NEAR_BOTTOM_PX
}

export function useChatAutoFollow(contentVersion: string, resetKey: string, working: boolean) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const pinnedRef = useRef(true)
  const programmaticScrollRef = useRef(false)
  const programmaticFallbackRef = useRef<number | null>(null)
  const previousWorkingRef = useRef(working)
  const previousHeightRef = useRef<number | null>(null)
  const [newContentPending, setNewContentPending] = useState(false)

  const clearProgrammaticFallback = useCallback(() => {
    if (programmaticFallbackRef.current !== null) window.clearTimeout(programmaticFallbackRef.current)
    programmaticFallbackRef.current = null
  }, [])

  const finishProgrammaticScroll = useCallback(() => {
    if (!programmaticScrollRef.current) return
    clearProgrammaticFallback()
    const element = scrollRef.current
    if (element && !isNearBottom(element)) element.scrollTo({ top: element.scrollHeight, behavior: 'auto' })
    programmaticScrollRef.current = false
    const pinned = Boolean(element && isNearBottom(element))
    pinnedRef.current = pinned
    setNewContentPending(!pinned)
  }, [clearProgrammaticFallback])

  const releaseToUser = useCallback(() => {
    if (!programmaticScrollRef.current) return
    clearProgrammaticFallback()
    programmaticScrollRef.current = false
    const element = scrollRef.current
    pinnedRef.current = Boolean(element && isNearBottom(element))
  }, [clearProgrammaticFallback])

  const scrollToLatest = useCallback((behavior: ScrollBehavior = 'auto') => {
    const element = scrollRef.current
    if (!element) return
    clearProgrammaticFallback()
    programmaticScrollRef.current = behavior === 'smooth'
    if (typeof element.scrollTo === 'function') element.scrollTo({ top: element.scrollHeight, behavior })
    else element.scrollTop = element.scrollHeight
    if (behavior === 'smooth') programmaticFallbackRef.current = window.setTimeout(finishProgrammaticScroll, PROGRAMMATIC_SCROLL_FALLBACK_MS)
    pinnedRef.current = true
    setNewContentPending(false)
  }, [clearProgrammaticFallback, finishProgrammaticScroll])

  const onScroll = useCallback(() => {
    if (programmaticScrollRef.current) return
    const element = scrollRef.current
    if (!element) return
    const pinned = isNearBottom(element)
    pinnedRef.current = pinned
    if (pinned) setNewContentPending(false)
  }, [])

  useLayoutEffect(() => {
    clearProgrammaticFallback()
    programmaticScrollRef.current = false
    pinnedRef.current = true
    previousHeightRef.current = null
    setNewContentPending(false)
    scrollToLatest()
  }, [clearProgrammaticFallback, resetKey, scrollToLatest])

  useEffect(() => {
    const scroll = scrollRef.current
    if (!scroll) return
    scroll.addEventListener('scrollend', finishProgrammaticScroll)
    scroll.addEventListener('wheel', releaseToUser, { passive: true })
    scroll.addEventListener('touchstart', releaseToUser, { passive: true })
    scroll.addEventListener('pointerdown', releaseToUser, { passive: true })
    return () => {
      scroll.removeEventListener('scrollend', finishProgrammaticScroll)
      scroll.removeEventListener('wheel', releaseToUser)
      scroll.removeEventListener('touchstart', releaseToUser)
      scroll.removeEventListener('pointerdown', releaseToUser)
      clearProgrammaticFallback()
    }
  }, [clearProgrammaticFallback, finishProgrammaticScroll, releaseToUser, resetKey])

  useLayoutEffect(() => {
    const started = working && !previousWorkingRef.current
    previousWorkingRef.current = working
    if (started) {
      scrollToLatest()
      return
    }
    if (pinnedRef.current) scrollToLatest()
    else setNewContentPending(true)
  }, [contentVersion, scrollToLatest, working])

  useEffect(() => {
    const content = contentRef.current
    const scroll = scrollRef.current
    if (!content || !scroll || typeof ResizeObserver === 'undefined') return
    previousHeightRef.current = content.getBoundingClientRect().height
    const observer = new ResizeObserver((entries) => {
      const height = entries[0]?.contentRect.height ?? content.getBoundingClientRect().height
      const previous = previousHeightRef.current
      previousHeightRef.current = height
      if (previous !== null && height <= previous) return
      if (pinnedRef.current) scrollToLatest()
      else setNewContentPending(true)
    })
    observer.observe(content)
    return () => observer.disconnect()
  }, [resetKey, scrollToLatest])

  return { scrollRef, contentRef, newContentPending, onScroll, scrollToLatest }
}
