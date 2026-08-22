import { useCallback, useEffect, useRef, useState } from 'react'
import { jarvisApi, type ApiConversation, type RuntimeEvent } from '../../api/jarvis'
import type { AgentPhase, ConversationMessage } from '../../models/chat'
import { resourceSummary } from '../../api/productViews'

const eventTypes: RuntimeEvent['type'][] = ['turn.started', 'phase.changed', 'message.delta', 'turn.completed', 'turn.failed', 'turn.cancelled']

interface ChatOptions {
  onConversationChanged?: () => void
}

const messagesFrom = (conversation: ApiConversation): ConversationMessage[] => conversation.messages.map(({ id, role, body, resources }) => ({ id, role, body, resources: resources.map(resourceSummary) }))

export function useJarvisChat(initialConversationId: string | null, initialTurnId: string | null = null, options: ChatOptions = {}) {
  const [conversationId, setConversationId] = useState(initialConversationId)
  const [conversationTitle, setConversationTitle] = useState<string | null>(null)
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [phase, setPhase] = useState<AgentPhase>('thinking')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const conversationRef = useRef(initialConversationId)
  const turnRef = useRef<string | null>(null)
  const streamRef = useRef<EventSource | null>(null)
  const generationRef = useRef(0)
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

  const watch = useCallback((turnId: string, id: string) => {
    closeStream()
    const stream = new EventSource(jarvisApi.eventsUrl(turnId))
    streamRef.current = stream
    const receive = (raw: MessageEvent<string>) => {
      if (streamRef.current !== stream || conversationRef.current !== id || turnRef.current !== turnId) return
      const event = JSON.parse(raw.data) as RuntimeEvent
      if (event.type === 'phase.changed' && event.phase) setPhase(event.phase)
      if (event.type === 'message.delta' && event.delta) {
        setMessages((current) => {
          const withoutDraft = current.filter((message) => message.id !== `draft:${turnId}`)
          const previous = current.find((message) => message.id === `draft:${turnId}`)?.body ?? ''
          return [...withoutDraft, { id: `draft:${turnId}`, role: 'assistant', body: previous + event.delta! }]
        })
      }
      if (event.type === 'turn.completed') {
        closeStream(); setRunning(false); turnRef.current = null
        window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}`)
        void load(id).catch(() => setError('conversation_refresh_failed'))
        changedRef.current?.()
      }
      if (event.type === 'turn.failed' || event.type === 'turn.cancelled') {
        closeStream(); setRunning(false); turnRef.current = null
        window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}`)
        setMessages((current) => current.filter((message) => message.id !== `draft:${turnId}`))
        if (event.type === 'turn.failed') setError(event.error_code ?? 'turn_failed')
        changedRef.current?.()
      }
    }
    eventTypes.forEach((type) => stream.addEventListener(type, receive as EventListener))
    stream.onerror = () => {
      if (streamRef.current === stream && stream.readyState === EventSource.CLOSED) setError('stream_unavailable')
    }
  }, [closeStream, load])

  const selectConversation = useCallback(async (id: string, turnId: string | null = null) => {
    const generation = ++generationRef.current
    closeStream()
    conversationRef.current = id
    turnRef.current = turnId
    setConversationId(id)
    setConversationTitle(null)
    setMessages([])
    setPhase('thinking')
    setRunning(Boolean(turnId))
    setError(null)
    try {
      await load(id, generation)
      if (generation === generationRef.current && conversationRef.current === id && turnId) watch(turnId, id)
    } catch {
      if (generation === generationRef.current) {
        setRunning(false)
        setError('conversation_unavailable')
      }
    }
  }, [closeStream, load, watch])

  const resetConversation = useCallback(() => {
    generationRef.current += 1
    closeStream()
    conversationRef.current = null
    turnRef.current = null
    setConversationId(null)
    setConversationTitle(null)
    setMessages([])
    setPhase('thinking')
    setRunning(false)
    setError(null)
  }, [closeStream])

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
      if (generation !== generationRef.current || conversationRef.current !== id) return
      turnRef.current = turnId
      window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}&turn=${encodeURIComponent(turnId)}`)
      changedRef.current?.()
      watch(turnId, id)
    } catch {
      if (generation !== generationRef.current || conversationRef.current !== id) return
      setRunning(false)
      setError('turn_start_failed')
      await load(id).catch(() => undefined)
    }
  }, [load, watch])

  const cancel = useCallback(async () => {
    if (turnRef.current) await jarvisApi.cancelTurn(turnRef.current)
  }, [])

  return { conversationId, conversationTitle, messages, phase, running, error, submit, cancel, selectConversation, resetConversation }
}
