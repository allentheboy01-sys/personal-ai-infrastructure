import { useCallback, useEffect, useRef, useState } from 'react'
import { jarvisApi, type ApiConversation, type RuntimeEvent } from '../../api/jarvis'
import type { AgentPhase, AgentProgress, ConversationMessage } from '../../models/chat'
import { resourceSummary } from '../../api/productViews'
import { createExecutionTrace, reduceExecutionTrace, type ExecutionTrace } from './executionTrace'
import { useProgressPresentation } from './useProgressPresentation'

const eventTypes: RuntimeEvent['type'][] = ['turn.started', 'phase.changed', 'tool.started', 'tool.completed', 'message.delta', 'turn.completed', 'turn.failed', 'turn.cancelled']

interface ChatOptions {
  onConversationChanged?: () => void
}

interface ActiveTurnObservation {
  turnId: string
  startedAtMs: number
}

const progressFromPhase: Record<AgentPhase, AgentProgress> = { thinking: 'processing', searching: 'searching', reviewing: 'reviewing', computing: 'computing', composing: 'composing' }

const messagesFrom = (conversation: ApiConversation): ConversationMessage[] => conversation.messages.map(({ id, role, body, resources }) => ({ id, role, body, resources: resources.map(resourceSummary) }))

export function useJarvisChat(initialConversationId: string | null, initialTurnId: string | null = null, options: ChatOptions = {}) {
  const [conversationId, setConversationId] = useState(initialConversationId)
  const [conversationTitle, setConversationTitle] = useState<string | null>(null)
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [phase, setPhase] = useState<AgentPhase>('thinking')
  const { progress, presentProgress, resetProgress, clearProgress } = useProgressPresentation(initialTurnId ? 'processing' : null)
  const [running, setRunning] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [activeTurnId, setActiveTurnId] = useState<string | null>(initialTurnId)
  const [activeConversationIds, setActiveConversationIds] = useState<ReadonlySet<string>>(() => new Set(initialConversationId && initialTurnId ? [initialConversationId] : []))
  const [turnStartedAtMs, setTurnStartedAtMs] = useState<number | null>(initialTurnId ? Date.now() : null)
  const [executionTrace, setExecutionTrace] = useState<ExecutionTrace | null>(initialTurnId ? createExecutionTrace(initialTurnId) : null)
  const [error, setError] = useState<string | null>(null)
  const conversationRef = useRef(initialConversationId)
  const turnRef = useRef<string | null>(null)
  const streamRef = useRef<EventSource | null>(null)
  const generationRef = useRef(0)
  const activeTurnsRef = useRef(new Map<string, ActiveTurnObservation>(initialConversationId && initialTurnId ? [[initialConversationId, { turnId: initialTurnId, startedAtMs: Date.now() }]] : []))
  const changedRef = useRef(options.onConversationChanged)
  changedRef.current = options.onConversationChanged

  const closeStream = useCallback(() => {
    streamRef.current?.close()
    streamRef.current = null
  }, [])

  const load = useCallback(async (id: string, generation = generationRef.current) => {
    const conversation = await jarvisApi.getConversation(id)
    if (generation !== generationRef.current || conversationRef.current !== id) return
    setConversationTitle(conversation.title)
    setMessages(messagesFrom(conversation))
  }, [])

  const rememberActiveTurn = useCallback((id: string, observation: ActiveTurnObservation) => {
    activeTurnsRef.current.set(id, observation)
    setActiveConversationIds(new Set(activeTurnsRef.current.keys()))
  }, [])

  const forgetActiveTurn = useCallback((id: string, turnId: string) => {
    if (activeTurnsRef.current.get(id)?.turnId !== turnId) return
    activeTurnsRef.current.delete(id)
    setActiveConversationIds(new Set(activeTurnsRef.current.keys()))
  }, [])

  const watch = useCallback((turnId: string, id: string) => {
    closeStream()
    const stream = new EventSource(jarvisApi.eventsUrl(turnId))
    streamRef.current = stream
    const receive = (raw: MessageEvent<string>) => {
      if (streamRef.current !== stream || conversationRef.current !== id || turnRef.current !== turnId) return
      const event = JSON.parse(raw.data) as RuntimeEvent
      setExecutionTrace((current) => reduceExecutionTrace(current, event))
      if (event.type === 'turn.started') presentProgress('processing')
      if (event.type === 'phase.changed' && event.phase) {
        setPhase(event.phase)
        presentProgress(progressFromPhase[event.phase])
      }
      if (event.type === 'tool.started' && event.category === 'pdi') presentProgress('searching')
      if (event.type === 'tool.started' && event.category === 'exec') presentProgress('computing')
      if (event.type === 'tool.completed' && event.category === 'pdi') presentProgress('search_complete')
      if (event.type === 'tool.completed' && event.category === 'exec') presentProgress('reviewing')
      if (event.type === 'message.delta' && event.delta) {
        setMessages((current) => {
          const withoutDraft = current.filter((message) => message.id !== `draft:${turnId}`)
          const previous = current.find((message) => message.id === `draft:${turnId}`)?.body ?? ''
          return [...withoutDraft, { id: `draft:${turnId}`, role: 'assistant', body: previous + event.delta! }]
        })
      }
      if (event.type === 'turn.completed') {
        closeStream(); forgetActiveTurn(id, turnId); setRunning(false); setCancelling(false); clearProgress(); setActiveTurnId(null); setTurnStartedAtMs(null); turnRef.current = null
        window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}`)
        void load(id).catch(() => setError('conversation_refresh_failed'))
        changedRef.current?.()
      }
      if (event.type === 'turn.failed' || event.type === 'turn.cancelled') {
        closeStream(); forgetActiveTurn(id, turnId); setRunning(false); setCancelling(false); clearProgress(); setActiveTurnId(null); setTurnStartedAtMs(null); turnRef.current = null
        window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}`)
        setMessages((current) => current.filter((message) => message.id !== `draft:${turnId}`))
        if (event.type === 'turn.failed') setError(event.error_code ?? 'turn_failed')
        changedRef.current?.()
      }
    }
    eventTypes.forEach((type) => stream.addEventListener(type, receive as EventListener))
    stream.onerror = () => {
      if (streamRef.current !== stream || stream.readyState !== EventSource.CLOSED) return
      void jarvisApi.getTurn(turnId).then((turn) => {
        if (streamRef.current !== stream || conversationRef.current !== id || turnRef.current !== turnId) return
        if (turn.status === 'running') { setError('stream_unavailable'); return }
        closeStream(); forgetActiveTurn(id, turnId); setRunning(false); setCancelling(false); clearProgress(); setActiveTurnId(null); setTurnStartedAtMs(null); turnRef.current = null
        window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}`)
        void load(id).catch(() => setError('conversation_refresh_failed'))
        changedRef.current?.()
      }).catch(() => setError('stream_unavailable'))
    }
  }, [clearProgress, closeStream, forgetActiveTurn, load, presentProgress])

  const selectConversation = useCallback(async (id: string, turnId: string | null = null) => {
    const generation = ++generationRef.current
    const known = turnId ? { turnId, startedAtMs: Date.now() } : activeTurnsRef.current.get(id) ?? null
    if (turnId) rememberActiveTurn(id, known!)
    closeStream()
    conversationRef.current = id
    turnRef.current = known?.turnId ?? null
    setConversationId(id)
    setConversationTitle(null)
    setMessages([])
    setPhase('thinking')
    resetProgress(known ? 'processing' : null)
    setRunning(Boolean(known))
    setCancelling(false)
    setActiveTurnId(known?.turnId ?? null)
    setTurnStartedAtMs(known?.startedAtMs ?? null)
    setExecutionTrace(known ? createExecutionTrace(known.turnId) : null)
    setError(null)
    try {
      await load(id, generation)
    } catch {
      if (generation === generationRef.current) {
        setRunning(false)
        clearProgress()
        setActiveTurnId(null)
        setTurnStartedAtMs(null)
        setExecutionTrace(null)
        turnRef.current = null
        setError('conversation_unavailable')
      }
      return
    }
    if (generation !== generationRef.current || conversationRef.current !== id || !known) return
    try {
      const turn = await jarvisApi.getTurn(known.turnId)
      if (generation !== generationRef.current || conversationRef.current !== id || turnRef.current !== known.turnId) return
      if (turn.conversation_id !== id) {
        forgetActiveTurn(id, known.turnId); turnRef.current = null; setRunning(false); clearProgress(); setActiveTurnId(null); setTurnStartedAtMs(null); setExecutionTrace(null); setError('turn_conversation_mismatch')
        return
      }
      if (turn.status !== 'running') {
        forgetActiveTurn(id, known.turnId); turnRef.current = null; setRunning(false); clearProgress(); setActiveTurnId(null); setTurnStartedAtMs(null); setExecutionTrace(null)
        await load(id, generation)
        changedRef.current?.()
        return
      }
      const startedAtMs = Date.parse(turn.started_at)
      const authoritativeStart = Number.isFinite(startedAtMs) ? startedAtMs : known.startedAtMs
      rememberActiveTurn(id, { turnId: known.turnId, startedAtMs: authoritativeStart })
      setRunning(true)
      setPhase(turn.phase ?? 'thinking')
      resetProgress(progressFromPhase[turn.phase ?? 'thinking'])
      setActiveTurnId(known.turnId)
      setTurnStartedAtMs(authoritativeStart)
      window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}&turn=${encodeURIComponent(known.turnId)}`)
      watch(known.turnId, id)
    } catch {
      if (generation === generationRef.current && conversationRef.current === id) {
        setRunning(true)
        setError('turn_status_unavailable')
      }
    }
  }, [clearProgress, closeStream, forgetActiveTurn, load, rememberActiveTurn, resetProgress, watch])

  const resetConversation = useCallback(() => {
    generationRef.current += 1
    closeStream()
    conversationRef.current = null
    turnRef.current = null
    setConversationId(null)
    setConversationTitle(null)
    setMessages([])
    setPhase('thinking')
    clearProgress()
    setRunning(false)
    setCancelling(false)
    setActiveTurnId(null)
    setTurnStartedAtMs(null)
    setExecutionTrace(null)
    setError(null)
  }, [clearProgress, closeStream])

  useEffect(() => {
    if (initialConversationId) void selectConversation(initialConversationId, initialTurnId)
    return () => {
      generationRef.current += 1
      closeStream()
    }
    // Initial URL state is consumed once; later navigation uses selectConversation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submit = useCallback(async (body: string) => {
    setError(null)
    setCancelling(false)
    setExecutionTrace(null)
    resetProgress('processing')
    setTurnStartedAtMs(Date.now())
    const generation = generationRef.current
    let id = conversationRef.current
    if (!id) {
      const created = await jarvisApi.createConversation(body.slice(0, 80))
      if (generation !== generationRef.current) return
      id = created.id
      conversationRef.current = id
      setConversationId(id)
      setConversationTitle(created.title)
      window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}`)
      changedRef.current?.()
    }
    setMessages((current) => [...current, { id: `local:${crypto.randomUUID()}`, role: 'user', body }])
    setRunning(true)
    setPhase('thinking')
    try {
      const { turn_id: turnId } = await jarvisApi.createTurn(id, body)
      const startedAtMs = Date.now()
      rememberActiveTurn(id, { turnId, startedAtMs })
      if (generation !== generationRef.current || conversationRef.current !== id) return
      turnRef.current = turnId
      setActiveTurnId(turnId)
      setTurnStartedAtMs(startedAtMs)
      setExecutionTrace(createExecutionTrace(turnId))
      window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}&turn=${encodeURIComponent(turnId)}`)
      changedRef.current?.()
      watch(turnId, id)
    } catch {
      if (generation !== generationRef.current || conversationRef.current !== id) return
      setRunning(false)
      clearProgress()
      setTurnStartedAtMs(null)
      setError('turn_start_failed')
      await load(id).catch(() => undefined)
    }
  }, [clearProgress, load, rememberActiveTurn, resetProgress, watch])

  const cancel = useCallback(async () => {
    if (!turnRef.current || cancelling) return
    setCancelling(true)
    try {
      await jarvisApi.cancelTurn(turnRef.current)
    } catch {
      setCancelling(false)
      setError('turn_cancel_failed')
    }
  }, [cancelling])

  const clearExecutionTrace = useCallback(() => setExecutionTrace(null), [])

  return { conversationId, conversationTitle, messages, phase, progress, running, cancelling, activeTurnId, activeConversationIds, turnStartedAtMs, executionTrace, error, submit, cancel, selectConversation, resetConversation, clearExecutionTrace }
}
