import * as Dialog from '@radix-ui/react-dialog'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ExecutionPanel, WorkPanel, type PanelContent } from './WorkPanel'
import { Sidebar, type AppPage } from './Sidebar'
import { TopBar } from './TopBar'
import { ResourceDetail } from '../features/resources/ResourceDetail'
import { ProviderDetail } from '../features/providers/ProviderDetail'
import { executionSteps } from '../mocks/chat'
import { providers } from '../mocks/providers'
import { resources } from '../mocks/resources'
import type { ProviderView } from '../models/provider'
import type { ResourceView } from '../models/resource'
import { ChatPage } from '../pages/ChatPage'
import { useJarvisChat } from '../features/chat/useJarvisChat'
import { HomePage } from '../pages/HomePage'
import { ProvidersPage } from '../pages/ProvidersPage'
import { ResourcesPage } from '../pages/ResourcesPage'
import { jarvisApi, type ApiConversationSummary } from '../api/jarvis'
import { providerDetail, resourceDetail } from '../api/productViews'
import { ErrorState } from './States'
import { reviewModeEnabled } from './reviewMode'

type Scene = 'home' | 'conversation' | 'working'

function readLocation() {
  const params = new URLSearchParams(window.location.search)
  const page = (params.get('page') as AppPage | null) ?? 'chat'
  const conversation = params.get('conversation')
  const review = reviewModeEnabled(import.meta.env.VITE_JARVIS_REVIEW === 'true', params.has('scene'))
  const requestedScene = review ? (params.get('scene') as Scene | null) : null
  const scene = requestedScene ?? (conversation ? 'conversation' : 'home')
  return { page: ['chat', 'resources', 'providers'].includes(page) ? page : 'chat', scene: ['home', 'conversation', 'working'].includes(scene) ? scene : 'home', detail: review ? params.get('detail') : null, conversation, turn: params.get('turn'), review }
}

const chatUrl = (conversationId?: string | null) => conversationId ? `?page=chat&conversation=${encodeURIComponent(conversationId)}` : '?page=chat'

export function AppShell() {
  const initial = useMemo(readLocation, [])
  const [page, setPage] = useState<AppPage>(initial.page)
  const [scene, setScene] = useState<Scene>(initial.scene)
  const [drawer, setDrawer] = useState(false)
  const [panel, setPanel] = useState<PanelContent | null>(null)
  const [conversations, setConversations] = useState<ApiConversationSummary[]>([])

  const refreshConversations = useCallback(() => {
    if (initial.review) return
    void jarvisApi.listConversations().then((items) => setConversations(items.slice(0, 10))).catch(() => undefined)
  }, [initial.review])

  const liveChat = useJarvisChat(initial.review ? null : initial.conversation, initial.review ? null : initial.turn, { onConversationChanged: refreshConversations })

  const showResource = (resource: ResourceView) => {
    if (initial.review) setPanel({ eyebrow: resource.provider, title: 'Resource detail', content: <ResourceDetail resource={resource} /> })
    else void jarvisApi.getResource(resource.resourceRef).then((detail) => {
      const view = resourceDetail(detail)
      setPanel({ eyebrow: view.provider, title: 'Resource detail', content: <ResourceDetail resource={view} /> })
    }).catch(() => setPanel({ eyebrow: 'Resource', title: 'Resource detail', content: <ErrorState title="Resource unavailable" body="Jarvis could not prepare this resource." /> }))
  }
  const showProvider = (provider: ProviderView) => {
    if (initial.review) setPanel({ eyebrow: provider.category, title: 'Provider detail', content: <ProviderDetail provider={provider} /> })
    else void jarvisApi.getProvider(provider.providerRef).then((detail) => {
      const view = providerDetail(detail)
      setPanel({ eyebrow: view.category, title: 'Provider detail', content: <ProviderDetail provider={view} /> })
    }).catch(() => setPanel({ eyebrow: 'Provider', title: 'Provider detail', content: <ErrorState title="Provider unavailable" body="Jarvis could not prepare this provider." /> }))
  }
  const showExecution = () => {
    if (initial.review) setPanel({ eyebrow: 'Review execution', title: 'Working', content: <ExecutionPanel steps={executionSteps} /> })
  }

  useEffect(() => {
    refreshConversations()
  }, [refreshConversations])

  useEffect(() => {
    if (initial.detail === 'image') showResource(resources[0])
    if (initial.detail === 'document') showResource(resources[1])
    if (initial.detail === 'message') showResource(resources[2])
    if (initial.detail === 'provider') showProvider(providers[1])
    if (initial.scene === 'working') showExecution()
    // deterministic review-state initialization only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const newConversation = useCallback(() => {
    liveChat.resetConversation()
    setPage('chat')
    setScene('home')
    setPanel(null)
    setDrawer(false)
    window.history.pushState(null, '', chatUrl())
  }, [liveChat])

  const openConversation = useCallback((id: string) => {
    setPage('chat')
    setScene('conversation')
    setPanel(null)
    setDrawer(false)
    window.history.pushState(null, '', chatUrl(id))
    void liveChat.selectConversation(id)
  }, [liveChat])

  const navigate = useCallback((next: AppPage) => {
    setPage(next)
    setPanel(null)
    setDrawer(false)
    if (next === 'chat') {
      setScene(liveChat.conversationId ? 'conversation' : 'home')
      window.history.pushState(null, '', chatUrl(liveChat.conversationId))
    } else {
      window.history.pushState(null, '', `?page=${next}`)
    }
  }, [liveChat.conversationId])

  useEffect(() => {
    if (initial.review) return
    const restore = () => {
      const location = readLocation()
      setPage(location.page)
      setPanel(null)
      setDrawer(false)
      if (location.page !== 'chat') return
      if (location.conversation) {
        setScene('conversation')
        void liveChat.selectConversation(location.conversation, location.turn)
      } else {
        setScene('home')
        liveChat.resetConversation()
      }
    }
    window.addEventListener('popstate', restore)
    return () => window.removeEventListener('popstate', restore)
  }, [initial.review, liveChat])

  const title = page === 'chat'
    ? initial.review && scene !== 'home' ? 'Interface review' : liveChat.conversationTitle ?? 'New conversation'
    : page === 'resources' ? 'Resources' : 'Providers'
  const eyebrow = page === 'chat' && scene !== 'home' ? 'Today' : undefined
  const sidebar = <Sidebar page={page} onNavigate={navigate} onNewConversation={newConversation} conversations={conversations} activeConversationId={liveChat.conversationId} onConversation={openConversation} review={initial.review} />

  return <div className={`app-shell ${panel ? 'panel-open' : ''}`}>
    <div className="desktop-sidebar">{sidebar}</div>
    <Dialog.Root open={drawer} onOpenChange={setDrawer}><Dialog.Portal><Dialog.Overlay className="drawer-overlay" /><Dialog.Content className="drawer-content" aria-describedby={undefined}><Dialog.Title className="sr-only">Navigation</Dialog.Title><Sidebar page={page} onNavigate={navigate} onNewConversation={newConversation} conversations={conversations} activeConversationId={liveChat.conversationId} onConversation={openConversation} onClose={() => setDrawer(false)} review={initial.review} /></Dialog.Content></Dialog.Portal></Dialog.Root>
    <section className="main-column">
      <TopBar title={title} eyebrow={eyebrow} onMenu={() => setDrawer(true)} panelAvailable={initial.review && scene === 'working'} onPanel={showExecution} />
      {page === 'chat' && scene === 'home' && <HomePage onStart={(prompt) => { setScene('conversation'); if (!initial.review) void liveChat.submit(prompt) }} />}
      {page === 'chat' && scene !== 'home' && <ChatPage working={initial.review ? scene === 'working' : liveChat.running} onResource={showResource} messages={initial.review ? undefined : liveChat.messages} phase={initial.review ? 'reviewing' : liveChat.phase} onSubmit={initial.review ? undefined : liveChat.submit} onStop={initial.review ? undefined : liveChat.cancel} />}
      {page === 'resources' && <ResourcesPage onResource={showResource} review={initial.review} />}
      {page === 'providers' && <ProvidersPage onProvider={showProvider} review={initial.review} />}
    </section>
    <WorkPanel panel={panel} onClose={() => setPanel(null)} />
  </div>
}
