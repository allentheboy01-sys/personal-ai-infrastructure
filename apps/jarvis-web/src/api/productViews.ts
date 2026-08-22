import type { ApiProviderDetail, ApiProviderSummary, ApiResourceDetail, ApiResourceSummary } from './jarvis'
import type { ProviderView } from '../models/provider'
import type { ResourceView } from '../models/resource'

const relative = (value: string | null) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value)) : 'Unknown'

export function resourceSummary(value: ApiResourceSummary): ResourceView {
  const provider = (value.providers[0] ?? 'Nextcloud') as ResourceView['provider']
  const representation = `/api/v1/resources/${encodeURIComponent(value.resource_ref)}/representation`
  return { resourceRef: value.resource_ref, resourceType: value.resource_type, title: value.title, secondary: value.secondary_text ?? 'Resource metadata', timestamp: relative(value.timestamp), provider, presentation: { kind: value.presentation_kind, label: value.presentation_label, thumbnail: value.capabilities.preview ? `${representation}?kind=thumbnail` : undefined, preview: value.capabilities.preview ? `${representation}?kind=preview` : undefined }, capabilities: value.capabilities, facts: [], provenance: value.providers.length ? `Observed through ${value.providers.join(', ')}.` : 'Provider provenance unavailable.' }
}

export function resourceDetail(value: ApiResourceDetail): ResourceView {
  return { ...resourceSummary(value.summary), facts: value.facts.map(([label, fact]) => ({ label, value: fact })), notice: value.notice ?? undefined }
}

export function providerSummary(value: ApiProviderSummary): ProviderView {
  return { providerRef: value.provider_ref, displayName: value.display_name, category: value.category, resourceCount: value.resource_count, accessMode: 'Read only', status: value.operational_state, lastSuccessfulSync: value.last_success_at ? relative(value.last_success_at) : null, description: '', capabilities: [], stages: [] }
}

export function providerDetail(value: ApiProviderDetail): ProviderView {
  return { ...providerSummary(value.summary), description: value.description, capabilities: value.capabilities, stages: value.stages.map(([label, state]) => ({ label, state })) }
}
