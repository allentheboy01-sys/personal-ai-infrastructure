import { AlertCircle, LoaderCircle, Search } from 'lucide-react'

export function EmptyState({ title, body }: { title: string; body: string }) {
  return <div className="state-card"><span className="state-icon"><Search size={20} /></span><h2>{title}</h2><p>{body}</p></div>
}

export function ErrorState({ title = 'Something went quiet', body = 'This view could not be prepared.' }: { title?: string; body?: string }) {
  return <div className="state-card" role="alert"><span className="state-icon error"><AlertCircle size={20} /></span><h2>{title}</h2><p>{body}</p></div>
}

export function LoadingState({ label = 'Preparing your view' }: { label?: string }) {
  return <div className="loading-state" role="status"><LoaderCircle className="spin" size={18} /><span>{label}</span></div>
}
