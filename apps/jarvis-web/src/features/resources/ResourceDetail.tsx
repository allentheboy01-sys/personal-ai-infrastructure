import { Eye, FileText, Image, Info, Mail, ShieldCheck } from 'lucide-react'
import type { ResourceView } from '../../models/resource'

export function ResourceDetail({ resource }: { resource: ResourceView }) {
  const Icon = resource.presentation.kind === 'image' ? Image : resource.presentation.kind === 'message' ? Mail : FileText
  return (
    <div className="detail-content resource-detail">
      {resource.presentation.kind === 'image' && resource.presentation.thumbnail ? <div className="detail-image"><img src={resource.presentation.thumbnail} alt="Synthetic misty mountain lake with a wooden rowboat" loading="lazy" /></div> : <div className={`detail-hero ${resource.presentation.kind}`}><Icon size={28} /><span>{resource.presentation.label}</span></div>}
      <div className="detail-heading"><span className="detail-kicker">{resource.presentation.label}</span><h2>{resource.title}</h2><p>{resource.secondary}</p></div>
      <div className="capability-row">
        <span className={resource.capabilities.preview ? 'available' : ''}><Eye size={15} />{resource.capabilities.preview ? 'Preview available' : 'No preview'}</span>
        <span><ShieldCheck size={15} />Read only</span>
      </div>
      {resource.notice && <div className="detail-notice"><Info size={17} /><p>{resource.notice}</p></div>}
      <section className="detail-section"><h3>Details</h3><dl>{resource.facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl></section>
      <section className="detail-section provenance"><h3>Provenance</h3><p>{resource.provenance}</p><small>Provider indicates where this resource was observed. It does not change how Jarvis presents it.</small></section>
    </div>
  )
}
