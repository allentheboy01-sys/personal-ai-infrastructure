import { ArrowUp, Paperclip, Square } from 'lucide-react'
import { useId, useState } from 'react'

export function Composer({ centered = false, running = false, stopping = false, onSubmit, onStop }: { centered?: boolean; running?: boolean; stopping?: boolean; onSubmit?: (value: string) => void; onStop?: () => void }) {
  const [value, setValue] = useState('')
  const id = useId()
  const submit = () => { const clean = value.trim(); if (clean && !running) { onSubmit?.(clean); setValue('') } }
  return (
    <div className={`composer-wrap ${centered ? 'centered' : ''}`}>
      <div className={`composer ${running ? 'is-running' : ''}`}>
        <label htmlFor={id} className="sr-only">Message Jarvis</label>
        <textarea id={id} rows={1} value={value} disabled={running} placeholder={running ? 'Jarvis is working…' : 'Ask Jarvis anything…'} onChange={(event) => setValue(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() } }} />
        <div className="composer-actions">
          <button className="attach-button" aria-label="Attachments coming later" title="Attachments coming later" disabled><Paperclip size={18} /></button>
          {running ? <button className="send-button stop" aria-label={stopping ? 'Stopping response' : 'Stop response'} onClick={onStop} disabled={stopping}><Square size={13} fill="currentColor" /></button> : <button className="send-button" aria-label="Send message" onClick={submit} disabled={!value.trim()}><ArrowUp size={18} /></button>}
        </div>
      </div>
    </div>
  )
}
