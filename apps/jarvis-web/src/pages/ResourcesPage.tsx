import { ChevronDown, Search, SlidersHorizontal } from 'lucide-react'
import { ResourceGrid } from '../features/resources/ResourceCard'
import { useEffect, useState } from 'react'
import { resources as reviewResources } from '../mocks/resources'
import type { ResourceView } from '../models/resource'
import { jarvisApi } from '../api/jarvis'
import { resourceSummary } from '../api/productViews'
import { EmptyState, ErrorState, LoadingState } from '../components/States'

export function ResourcesPage({ onResource, review = false }: { onResource: (resource: ResourceView) => void; review?: boolean }) {
  const [resources, setResources] = useState<ResourceView[]>(review ? reviewResources : [])
  const [state, setState] = useState<'loading' | 'ready' | 'error'>(review ? 'ready' : 'loading')
  const [query, setQuery] = useState('')
  const load = (search?: string) => { if (review) return; setState('loading'); void jarvisApi.listResources(search).then((page) => { setResources(page.resources.map(resourceSummary)); setState('ready') }).catch(() => setState('error')) }
  useEffect(() => { load() /* live composition only */ }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return <main className="collection-page"><div className="collection-heading"><div><span>Your digital world</span><h2>Resources</h2><p>Files and messages, presented consistently wherever they came from.</p></div><div className="resource-count">{resources.length}<span>shown</span></div></div><form className="filter-bar" onSubmit={(event) => { event.preventDefault(); load(query.trim() || undefined) }}><label><Search size={17} /><span className="sr-only">Search resources</span><input placeholder="Search resources" value={query} onChange={(event) => setQuery(event.target.value)} /></label><button type="button"><SlidersHorizontal size={16} />Type<ChevronDown size={14} /></button><button type="button">Any time<ChevronDown size={14} /></button></form>{state === 'loading' ? <LoadingState label="Loading resources" /> : state === 'error' ? <ErrorState title="Resources are unavailable" body="Jarvis could not reach your digital world. Try again shortly." /> : resources.length ? <ResourceGrid resources={resources} onOpen={onResource} /> : <EmptyState title="No resources found" body="Try a different search." />}</main>
}
