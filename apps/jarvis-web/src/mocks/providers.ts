import type { ProviderView } from '../models/provider'

export const providers: ProviderView[] = [
  {
    providerRef: 'gmail', displayName: 'Gmail', category: 'Messages', resourceCount: 1248,
    accessMode: 'Read only', status: 'attention', lastSuccessfulSync: 'Aug 17, 22:10',
    description: 'Message metadata from a connected mailbox.',
    capabilities: ['Message metadata', 'Subject and sender', 'Received time'],
    stages: [
      { label: 'Connected', state: 'completed' },
      { label: 'Messages observed', state: 'completed' },
      { label: 'Metadata needs attention', state: 'attention' },
    ],
  },
  {
    providerRef: 'immich', displayName: 'Immich', category: 'Photos & media', resourceCount: 10382,
    accessMode: 'Read only', status: 'ready', lastSuccessfulSync: 'Today, 07:42',
    description: 'Photos and media represented as unified Resources.',
    capabilities: ['Image metadata', 'Bounded previews', 'Visual retrieval'],
    stages: [
      { label: 'Connected', state: 'completed' },
      { label: 'Resources observed', state: 'completed' },
      { label: 'Ready to use', state: 'completed' },
    ],
  },
  {
    providerRef: 'nextcloud', displayName: 'Nextcloud', category: 'Files & documents', resourceCount: 3687,
    accessMode: 'Read only', status: 'processing', lastSuccessfulSync: 'Today, 07:36',
    description: 'Files and documents represented without exposing storage details.',
    capabilities: ['File metadata', 'Document discovery', 'Text retrieval'],
    stages: [
      { label: 'Connected', state: 'completed' },
      { label: 'Resources observed', state: 'completed' },
      { label: 'Preparing document context', state: 'current' },
    ],
  },
  {
    providerRef: 'gmail', displayName: 'Gmail', category: 'Messages', resourceCount: 0,
    accessMode: 'Read only', status: 'not_synced', lastSuccessfulSync: null,
    description: 'A synthetic alternate state used for component review.', capabilities: ['Message metadata'],
    stages: [{ label: 'Waiting for first sync', state: 'pending' }],
  },
  {
    providerRef: 'immich', displayName: 'Immich', category: 'Photos & media', resourceCount: 10291,
    accessMode: 'Read only', status: 'syncing', lastSuccessfulSync: 'Yesterday, 22:04',
    description: 'A synthetic alternate state used for component review.', capabilities: ['Image metadata'],
    stages: [{ label: 'Reading recent changes', state: 'current' }],
  },
]
