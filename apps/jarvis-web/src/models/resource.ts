export type ResourceType = 'file' | 'message'
export type PresentationKind = 'image' | 'video' | 'document' | 'message' | 'generic'

export interface ResourceCapabilities {
  detail: boolean
  preview: boolean
  open: boolean
  playback: boolean
}

export interface ResourceView {
  resourceRef: `pdi:resource:${string}`
  resourceType: ResourceType
  title: string
  secondary: string
  timestamp: string
  provider: 'Immich' | 'Nextcloud' | 'Gmail'
  presentation: {
    kind: PresentationKind
    label: string
    thumbnail?: string
    preview?: string
    playback?: string
  }
  capabilities: ResourceCapabilities
  facts: Array<{ label: string; value: string }>
  provenance: string
  notice?: string
}
