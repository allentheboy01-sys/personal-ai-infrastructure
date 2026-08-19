import { ChevronDown, Search, SlidersHorizontal } from 'lucide-react'
import { ResourceGrid } from '../features/resources/ResourceCard'
import { resources } from '../mocks/resources'
import type { ResourceView } from '../models/resource'

export function ResourcesPage({ onResource }: { onResource: (resource: ResourceView) => void }) {
  return <main className="collection-page"><div className="collection-heading"><div><span>Your digital world</span><h2>Resources</h2><p>Files and messages, presented consistently wherever they came from.</p></div><div className="resource-count">{resources.length}<span>shown</span></div></div><div className="filter-bar"><label><Search size={17} /><span className="sr-only">Search resources</span><input placeholder="Search resources" /></label><button><SlidersHorizontal size={16} />Type<ChevronDown size={14} /></button><button>Any time<ChevronDown size={14} /></button></div><ResourceGrid resources={resources} onOpen={onResource} /></main>
}
