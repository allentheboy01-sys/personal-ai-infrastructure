import { ProviderCard } from '../features/providers/ProviderCard'
import { useEffect, useState } from 'react'
import { providers as reviewProviders } from '../mocks/providers'
import type { ProviderView } from '../models/provider'
import { jarvisApi } from '../api/jarvis'
import { providerSummary } from '../api/productViews'
import { ErrorState, LoadingState } from '../components/States'

export function ProvidersPage({ onProvider, review = false }: { onProvider: (provider: ProviderView) => void; review?: boolean }) {
  const [providers, setProviders] = useState<ProviderView[]>(review ? reviewProviders.slice(0, 3) : [])
  const [state, setState] = useState<'loading' | 'ready' | 'error'>(review ? 'ready' : 'loading')
  useEffect(() => { if (!review) void jarvisApi.listProviders().then((items) => { setProviders(items.map(providerSummary)); setState('ready') }).catch(() => setState('error')) }, [review])
  return <main className="collection-page providers-page"><div className="collection-heading"><div><span>Read-only connections</span><h2>Providers</h2><p>Connected sources Jarvis can work with.</p></div></div>{state === 'loading' ? <LoadingState label="Loading providers" /> : state === 'error' ? <ErrorState title="Providers are unavailable" body="Jarvis could not read provider status. Try again shortly." /> : <div className="provider-grid">{providers.map((provider) => <ProviderCard key={provider.providerRef} provider={provider} onOpen={onProvider} />)}</div>}</main>
}
