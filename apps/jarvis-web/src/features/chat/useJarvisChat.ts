import { useCallback, useEffect, useRef, useState } from 'react'
import { jarvisApi, type RuntimeEvent } from '../../api/jarvis'
import type { AgentPhase, ConversationMessage } from '../../models/chat'

const eventTypes: RuntimeEvent['type'][] = ['turn.started', 'phase.changed', 'message.delta', 'turn.completed', 'turn.failed', 'turn.cancelled']

export function useJarvisChat(initialConversationId: string | null, initialTurnId: string | null = null) {
  const [conversationId, setConversationId] = useState(initialConversationId)
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [phase, setPhase] = useState<AgentPhase>('thinking')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const turnRef = useRef<string | null>(null)
  const streamRef = useRef<EventSource | null>(null)

  const load = useCallback(async (id: string) => {
    const conversation = await jarvisApi.getConversation(id)
    setMessages(conversation.messages.map(({ id: messageId, role, body }) => ({ id: messageId, role, body })))
  }, [])

  useEffect(() => {
    if (!initialConversationId) return
    void load(initialConversationId).catch(() => setError('conversation_unavailable'))
  }, [initialConversationId, load])

  useEffect(() => () => streamRef.current?.close(), [])

  const watch = useCallback((turnId: string, id: string) => {
    streamRef.current?.close()
    const stream = new EventSource(jarvisApi.eventsUrl(turnId))
    streamRef.current = stream
    const receive = (raw: MessageEvent<string>) => {
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
        stream.close(); setRunning(false); turnRef.current = null
        window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}`)
        void load(id).catch(() => setError('conversation_refresh_failed'))
      }
      if (event.type === 'turn.failed' || event.type === 'turn.cancelled') {
        stream.close(); setRunning(false); turnRef.current = null
        window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}`)
        setMessages((current) => current.filter((message) => message.id !== `draft:${turnId}`))
        if (event.type === 'turn.failed') setError(event.error_code ?? 'turn_failed')
      }
    }
    eventTypes.forEach((type) => stream.addEventListener(type, receive as EventListener))
    stream.onerror = () => { if (stream.readyState === EventSource.CLOSED) setError('stream_unavailable') }
  }, [load])

  useEffect(() => {
    if (!initialConversationId || !initialTurnId) return
    turnRef.current = initialTurnId
    setRunning(true)
    watch(initialTurnId, initialConversationId)
  }, [initialConversationId, initialTurnId, watch])

  const submit = useCallback(async (body: string) => {
    setError(null)
    const id = conversationId ?? (await jarvisApi.createConversation(body.slice(0, 80))).id
    if (!conversationId) {
      setConversationId(id)
      window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}`)
    }
    setMessages((current) => [...current, { id: `local:${crypto.randomUUID()}`, role: 'user', body }])
    setRunning(true); setPhase('thinking')
    try {
      const { turn_id: turnId } = await jarvisApi.createTurn(id, body)
      turnRef.current = turnId
      window.history.replaceState(null, '', `?page=chat&conversation=${encodeURIComponent(id)}&turn=${encodeURIComponent(turnId)}`)
      watch(turnId, id)
    } catch {
      setRunning(false); setError('turn_start_failed')
      await load(id).catch(() => undefined)
    }
  }, [conversationId, load, watch])

  const cancel = useCallback(async () => {
    if (turnRef.current) await jarvisApi.cancelTurn(turnRef.current)
  }, [])

  return { conversationId, messages, phase, running, error, submit, cancel }
}
