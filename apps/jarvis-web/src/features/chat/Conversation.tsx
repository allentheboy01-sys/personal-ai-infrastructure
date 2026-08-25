import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ReactNode } from 'react'
import { JarvisMark } from '../../components/JarvisMark'
import type { ConversationMessage } from '../../models/chat'
import type { ResourceView } from '../../models/resource'
import { ResourceStrip } from '../resources/ResourceCard'

const trailingCjkPunctuation = /[。！？；，、]+$/u

function normalizedBareLink(href: string, children: ReactNode) {
  if (typeof children !== 'string' || !/^https?:\/\//i.test(children)) return null
  const punctuation = children.match(trailingCjkPunctuation)?.[0]
  if (!punctuation) return null
  try {
    if (new URL(children).href !== new URL(href).href) return null
    const text = children.slice(0, -punctuation.length)
    return { href: new URL(text).href, text, punctuation }
  } catch {
    return null
  }
}

function MarkdownLink({ href, children }: { href?: string; children?: ReactNode }) {
  if (!href) return <span>{children}</span>
  const external = /^https?:\/\//i.test(href)
  if (/^[a-z][a-z0-9+.-]*:/i.test(href) && !external) return <span>{children}</span>
  const normalized = external ? normalizedBareLink(href, children) : null
  const link = <a href={normalized?.href ?? href} target={external ? '_blank' : undefined} rel={external ? 'noopener noreferrer' : undefined}>{normalized?.text ?? children}</a>
  return normalized ? <>{link}{normalized.punctuation}</> : link
}

export function UserMessage({ body }: { body: string }) { return <div className="user-message"><p>{body}</p></div> }
export function AssistantMessage({ message, onResource }: { message: ConversationMessage; onResource?: (resource: ResourceView) => void }) {
  return <div className="assistant-message"><span className="assistant-mark" aria-hidden="true"><JarvisMark size={17} /></span><div className="assistant-body"><div className="markdown-body"><ReactMarkdown skipHtml remarkPlugins={[remarkGfm]} components={{ a: MarkdownLink }}>{message.body}</ReactMarkdown></div>{message.resources && <ResourceStrip resources={message.resources} moreCount={message.moreCount} onOpen={onResource} />}</div></div>
}

export function Conversation({ messages, onResource }: { messages: ConversationMessage[]; onResource?: (resource: ResourceView) => void }) {
  return <div className="conversation" aria-label="Conversation">{messages.map((message) => message.role === 'user' ? <UserMessage key={message.id} body={message.body} /> : <AssistantMessage key={message.id} message={message} onResource={onResource} />)}</div>
}
