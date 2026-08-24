import * as Dialog from '@radix-ui/react-dialog'
import { CirclePlay, Eye, FileText, Image, ImageOff, Info, Mail, Maximize2, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'
import type { ResourceView } from '../../models/resource'

export function ResourceDetail({ resource }: { resource: ResourceView }) {
  const [previewFailed, setPreviewFailed] = useState(false)
  const [playbackFailed, setPlaybackFailed] = useState(false)
  const Icon = resource.presentation.kind === 'image' ? Image : resource.presentation.kind === 'video' ? CirclePlay : resource.presentation.kind === 'message' ? Mail : FileText
  const preview = resource.presentation.kind === 'image' && resource.capabilities.preview ? resource.presentation.preview : undefined
  const video = resource.presentation.kind === 'video' && resource.capabilities.playback ? resource.presentation.playback : undefined
  return (
    <div className="detail-content resource-detail">
      {preview && !previewFailed ? <Dialog.Root>
        <Dialog.Trigger asChild><button className="detail-image" aria-label={`Enlarge ${resource.title}`}><img src={preview} alt={resource.title} loading="lazy" onError={() => setPreviewFailed(true)} /><span className="image-enlarge" aria-hidden="true"><Maximize2 size={16} /></span></button></Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="lightbox-overlay" />
          <Dialog.Content className="lightbox-content" aria-describedby={undefined}>
            <Dialog.Title className="sr-only">{resource.title}</Dialog.Title>
            <img src={preview} alt={resource.title} />
            <Dialog.Close className="lightbox-close" aria-label="Close image viewer"><X size={21} /></Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root> : resource.presentation.kind === 'image' && previewFailed ? <div className="detail-hero image"><ImageOff size={28} /><span>Preview unavailable</span></div> : video ? <div className="detail-video"><video controls preload="metadata" poster={resource.presentation.preview ?? resource.presentation.thumbnail} aria-label={`Play ${resource.title}`} onError={() => setPlaybackFailed(true)}><source src={video} /></video>{playbackFailed && <div className="video-unavailable" role="status"><CirclePlay size={24} /><span>Video playback unavailable</span></div>}</div> : resource.presentation.kind === 'video' ? <div className="detail-hero video"><CirclePlay size={28} /><span>Video playback unavailable</span></div> : <div className={`detail-hero ${resource.presentation.kind}`}><Icon size={28} /><span>{resource.presentation.label}</span></div>}
      <div className="detail-heading"><span className="detail-kicker">{resource.presentation.label}</span><h2>{resource.title}</h2><p>{resource.secondary}</p></div>
      <div className="capability-row">
        <span className={resource.capabilities.preview || resource.capabilities.playback ? 'available' : ''}><Eye size={15} />{resource.capabilities.playback ? 'Playback available' : resource.capabilities.preview ? 'Preview available' : 'No preview'}</span>
        <span><ShieldCheck size={15} />Read only</span>
      </div>
      {resource.notice && <div className="detail-notice"><Info size={17} /><p>{resource.notice}</p></div>}
      <section className="detail-section"><h3>Details</h3><dl>{resource.facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl></section>
      <section className="detail-section provenance"><h3>Provenance</h3><p>{resource.provenance}</p><small>Provider indicates where this resource was observed. It does not change how Jarvis presents it.</small></section>
    </div>
  )
}
