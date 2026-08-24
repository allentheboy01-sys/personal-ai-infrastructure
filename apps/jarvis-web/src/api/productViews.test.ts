import { resourceSummary } from './productViews'
import type { ApiResourceSummary } from './jarvis'

const video: ApiResourceSummary = {
  resource_ref: 'pdi:resource:66666666-6666-4666-8666-666666666666',
  resource_type: 'file',
  title: 'Synthetic clip',
  secondary_text: 'video/quicktime',
  timestamp: null,
  presentation_kind: 'video',
  presentation_label: 'Video',
  providers: ['Immich'],
  capabilities: { detail: true, preview: true, open: false, playback: true },
}

it('builds only Jarvis-owned video presentation URLs', () => {
  const view = resourceSummary(video)
  expect(view.presentation.thumbnail).toMatch(/^\/api\/v1\/resources\/.+\/representation\?kind=thumbnail$/)
  expect(view.presentation.preview).toMatch(/^\/api\/v1\/resources\/.+\/representation\?kind=preview$/)
  expect(view.presentation.playback).toMatch(/^\/api\/v1\/resources\/.+\/video$/)
  expect(JSON.stringify(view)).not.toContain('immich.example')
})

it('does not make a non-Immich video previewable or playable', () => {
  const view = resourceSummary({
    ...video,
    providers: ['Nextcloud'],
    capabilities: { detail: true, preview: false, open: false, playback: false },
  })
  expect(view.presentation.kind).toBe('video')
  expect(view.presentation.thumbnail).toBeUndefined()
  expect(view.presentation.playback).toBeUndefined()
})
