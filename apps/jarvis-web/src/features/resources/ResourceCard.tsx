import { File, FileText, Mail, MoreHorizontal } from 'lucide-react'
import type { ResourceView } from '../../models/resource'

function ImageRenderer({ resource }: { resource: ResourceView }) {
  return <div className="resource-visual image-renderer"><img src={resource.presentation.thumbnail} alt="Synthetic misty mountain lake with a wooden rowboat" loading="lazy" /></div>
}

function DocumentRenderer({ resource }: { resource: ResourceView }) {
  return <div className="resource-visual icon-renderer document"><span className="renderer-icon"><FileText size={24} /></span><span>{resource.presentation.label}</span></div>
}

function MessageRenderer() { return <div className="resource-visual icon-renderer message"><span className="renderer-icon"><Mail size={24} /></span><span>Message</span></div> }
function GenericRenderer() { return <div className="resource-visual icon-renderer generic"><span className="renderer-icon"><File size={24} /></span><span>File</span></div> }

export function ResourceCard({ resource, onOpen, compact = false }: { resource: ResourceView; onOpen?: (resource: ResourceView) => void; compact?: boolean }) {
  const renderer = resource.presentation.kind === 'image' ? <ImageRenderer resource={resource} /> : resource.presentation.kind === 'document' ? <DocumentRenderer resource={resource} /> : resource.presentation.kind === 'message' ? <MessageRenderer /> : <GenericRenderer />
  return (
    <article className={`resource-card ${compact ? 'compact' : ''}`}>
      <button className="resource-hitbox" onClick={() => onOpen?.(resource)} aria-label={`View ${resource.title}`}>
        {renderer}
        <div className="resource-copy">
          <div className="resource-meta"><span>{resource.provider}</span><span aria-hidden="true">·</span><time>{resource.timestamp}</time></div>
          <h3>{resource.title}</h3>
          <p>{resource.secondary}</p>
        </div>
        <MoreHorizontal className="resource-more" size={17} aria-hidden="true" />
      </button>
    </article>
  )
}

export function ResourceStrip({ resources, moreCount = 0, onOpen }: { resources: ResourceView[]; moreCount?: number; onOpen?: (resource: ResourceView) => void }) {
  return <div className="resource-strip-wrap"><div className="resource-strip">{resources.map((resource) => <ResourceCard key={resource.resourceRef} resource={resource} onOpen={onOpen} compact />)}{moreCount > 0 && <button className="more-resources" aria-label={`Show ${moreCount} more resources`}><span>View</span>+{moreCount}<span>more</span></button>}</div>{moreCount > 0 && <button className="mobile-resource-more" aria-label={`View all ${resources.length + moreCount} resources`}>View all <span>{resources.length + moreCount}</span></button>}</div>
}

export function ResourceGrid({ resources, onOpen }: { resources: ResourceView[]; onOpen?: (resource: ResourceView) => void }) {
  return <div className="resource-grid">{resources.map((resource) => <ResourceCard key={resource.resourceRef} resource={resource} onOpen={onOpen} />)}</div>
}
