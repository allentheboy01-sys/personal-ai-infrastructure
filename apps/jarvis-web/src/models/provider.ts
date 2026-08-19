export type ProviderState = 'not_synced' | 'syncing' | 'processing' | 'ready' | 'attention'

export interface ProviderView {
  providerRef: 'gmail' | 'immich' | 'nextcloud'
  displayName: string
  category: string
  resourceCount: number
  accessMode: 'Read only'
  status: ProviderState
  lastSuccessfulSync: string | null
  description: string
  capabilities: string[]
  stages: Array<{ label: string; state: 'completed' | 'current' | 'pending' | 'attention' }>
}
