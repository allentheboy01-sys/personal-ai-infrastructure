import { ProviderCard } from '../features/providers/ProviderCard'
import { providers } from '../mocks/providers'
import type { ProviderView } from '../models/provider'

export function ProvidersPage({ onProvider }: { onProvider: (provider: ProviderView) => void }) {
  const primary = providers.slice(0, 3)
  return <main className="collection-page providers-page"><div className="collection-heading"><div><span>Read-only connections</span><h2>Providers</h2><p>Connected sources Jarvis can work with.</p></div></div><div className="provider-grid">{primary.map((provider) => <ProviderCard key={provider.providerRef} provider={provider} onOpen={onProvider} />)}</div></main>
}
