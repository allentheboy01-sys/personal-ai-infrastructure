import ReactMarkdown from 'react-markdown'
import { JarvisMark } from '../../components/JarvisMark'
import type { ConversationMessage } from '../../models/chat'
import type { ResourceView } from '../../models/resource'
import { ResourceStrip } from '../resources/ResourceCard'

export function UserMessage({ body }: { body: string }) { return <div className="user-message"><p>{body}</p></div> }
export function AssistantMessage({ message, onResource }: { message: ConversationMessage; onResource?: (resource: ResourceView) => void }) {
  return <div className="assistant-message"><span className="assistant-mark" aria-hidden="true"><JarvisMark size={17} /></span><div className="assistant-body"><div className="markdown-body"><ReactMarkdown skipHtml components={{ a: ({ href, children }) => { if (!href) return <span>{children}</span>; const external = /^https?:\/\//i.test(href); return <a href={href} target={external ? '_blank' : undefined} rel={external ? 'noopener noreferrer' : undefined}>{children}</a> } }}>{message.body}</ReactMarkdown></div>{message.resources && <ResourceStrip resources={message.resources} moreCount={message.moreCount} onOpen={onResource} />}</div></div>
}

export function Conversation({ messages, onResource }: { messages: ConversationMessage[]; onResource?: (resource: ResourceView) => void }) {
  return <div className="conversation" aria-label="Conversation">{messages.map((message) => message.role === 'user' ? <UserMessage key={message.id} body={message.body} /> : <AssistantMessage key={message.id} message={message} onResource={onResource} />)}</div>
}
