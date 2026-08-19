import { ArrowUpRight, Clock3, Database, LockKeyhole } from 'lucide-react'
import type { ProviderState, ProviderView } from '../../models/provider'

const statusLabel: Record<ProviderState, string> = { not_synced: 'Not synced', syncing: 'Syncing', processing: 'Processing', ready: 'Ready', attention: 'Attention' }

export function ProviderCard({ provider, onOpen, compact = false }: { provider: ProviderView; onOpen?: (provider: ProviderView) => void; compact?: boolean }) {
  return <article className={`provider-card ${compact ? 'compact' : ''}`}><button onClick={() => onOpen?.(provider)} aria-label={`View ${provider.displayName}`}><div className="provider-card-top"><span className={`provider-glyph ${provider.providerRef}`}>{provider.displayName.slice(0, 1)}</span><span className={`status-pill ${provider.status}`}><i />{statusLabel[provider.status]}</span></div><h2>{provider.displayName}</h2><p className="provider-category">{provider.category}</p><div className="provider-stats"><span><Database size={15} />{provider.resourceCount.toLocaleString()} Resources</span><span><LockKeyhole size={15} />{provider.accessMode}</span><span><Clock3 size={15} />{provider.lastSuccessfulSync ?? 'Never synced'}</span></div><ArrowUpRight className="provider-arrow" size={18} /></button></article>
}
