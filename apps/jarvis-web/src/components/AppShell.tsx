import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useMemo, useState } from 'react'
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
import { jarvisApi } from '../api/jarvis'
import { providerDetail, resourceDetail } from '../api/productViews'
import { ErrorState } from './States'
import { reviewModeEnabled } from './reviewMode'

type Scene = 'home' | 'conversation' | 'working'

function readInitial() {
  const params = new URLSearchParams(window.location.search)
  const page = (params.get('page') as AppPage | null) ?? 'chat'
  const conversation = params.get('conversation')
  const review = reviewModeEnabled(import.meta.env.VITE_JARVIS_REVIEW === 'true', params.has('scene'))
  const requestedScene = review ? (params.get('scene') as Scene | null) : null
  const scene = requestedScene ?? (conversation ? 'conversation' : 'home')
  return { page: ['chat', 'resources', 'providers'].includes(page) ? page : 'chat', scene: ['home', 'conversation', 'working'].includes(scene) ? scene : 'home', detail: review ? params.get('detail') : null, conversation, turn: params.get('turn'), review }
}

export function AppShell() {
  const initial = useMemo(readInitial, [])
  const [page, setPage] = useState<AppPage>(initial.page)
  const [scene, setScene] = useState<Scene>(initial.scene)
  const [drawer, setDrawer] = useState(false)
  const [panel, setPanel] = useState<PanelContent | null>(null)
  const liveChat = useJarvisChat(initial.review ? null : initial.conversation, initial.review ? null : initial.turn)

  const showResource = (resource: ResourceView) => { if (initial.review) setPanel({ eyebrow: resource.provider, title: 'Resource detail', content: <ResourceDetail resource={resource} /> }); else void jarvisApi.getResource(resource.resourceRef).then((detail) => { const view = resourceDetail(detail); setPanel({ eyebrow: view.provider, title: 'Resource detail', content: <ResourceDetail resource={view} /> }) }).catch(() => setPanel({ eyebrow: 'Resource', title: 'Resource detail', content: <ErrorState title="Resource unavailable" body="Jarvis could not prepare this resource." /> })) }
  const showProvider = (provider: ProviderView) => { if (initial.review) setPanel({ eyebrow: provider.category, title: 'Provider detail', content: <ProviderDetail provider={provider} /> }); else void jarvisApi.getProvider(provider.providerRef).then((detail) => { const view = providerDetail(detail); setPanel({ eyebrow: view.category, title: 'Provider detail', content: <ProviderDetail provider={view} /> }) }).catch(() => setPanel({ eyebrow: 'Provider', title: 'Provider detail', content: <ErrorState title="Provider unavailable" body="Jarvis could not prepare this provider." /> })) }
  const showExecution = () => setPanel({ eyebrow: 'Live execution', title: 'Working', content: <ExecutionPanel steps={executionSteps} /> })

  useEffect(() => {
    if (initial.detail === 'image') showResource(resources[0])
    if (initial.detail === 'document') showResource(resources[1])
    if (initial.detail === 'message') showResource(resources[2])
    if (initial.detail === 'provider') showProvider(providers[1])
    if (initial.scene === 'working') showExecution()
    // deterministic review-state initialization only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const navigate = (next: AppPage) => { setPage(next); setPanel(null); setDrawer(false); if (next === 'chat') setScene('home') }
  const title = page === 'chat' ? (scene === 'home' ? 'New conversation' : 'Interface review') : page === 'resources' ? 'Resources' : 'Providers'
  const eyebrow = page === 'chat' && scene !== 'home' ? 'Today' : undefined

  return <div className={`app-shell ${panel ? 'panel-open' : ''}`}>
    <div className="desktop-sidebar"><Sidebar page={page} onNavigate={navigate} /></div>
    <Dialog.Root open={drawer} onOpenChange={setDrawer}><Dialog.Portal><Dialog.Overlay className="drawer-overlay" /><Dialog.Content className="drawer-content" aria-describedby={undefined}><Dialog.Title className="sr-only">Navigation</Dialog.Title><Sidebar page={page} onNavigate={navigate} onClose={() => setDrawer(false)} /></Dialog.Content></Dialog.Portal></Dialog.Root>
    <section className="main-column">
      <TopBar title={title} eyebrow={eyebrow} onMenu={() => setDrawer(true)} panelAvailable={scene === 'working'} onPanel={showExecution} />
      {page === 'chat' && scene === 'home' && <HomePage onStart={(prompt) => { setScene('conversation'); if (!initial.review) void liveChat.submit(prompt) }} />}
      {page === 'chat' && scene !== 'home' && <ChatPage working={initial.review ? scene === 'working' : liveChat.running} onResource={showResource} messages={initial.review ? undefined : liveChat.messages} phase={initial.review ? 'reviewing' : liveChat.phase} onSubmit={initial.review ? undefined : liveChat.submit} onStop={initial.review ? undefined : liveChat.cancel} />}
      {page === 'resources' && <ResourcesPage onResource={showResource} review={initial.review} />}
      {page === 'providers' && <ProvidersPage onProvider={showProvider} review={initial.review} />}
    </section>
    <WorkPanel panel={panel} onClose={() => setPanel(null)} />
  </div>
}
