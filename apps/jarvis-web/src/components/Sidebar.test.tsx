import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Sidebar } from './Sidebar'

it('contains only the frozen primary navigation', () => {
  render(<Sidebar page="chat" onNavigate={() => undefined} onNewConversation={() => undefined} />)
  const nav = screen.getByRole('navigation', { name: 'Primary navigation' })
  expect(nav).toHaveTextContent('Chat')
  expect(nav).toHaveTextContent('Resources')
  expect(nav).toHaveTextContent('Providers')
  expect(nav).not.toHaveTextContent(/activity|memory|tasks|marketplace/i)
})

it('renders canonical Recent conversations and opens the exact id', async () => {
  const onConversation = vi.fn()
  render(<Sidebar page="chat" onNavigate={() => undefined} onNewConversation={() => undefined} conversations={[{ id: 'conversation-real', title: 'Canonical history', created_at: '2026-08-22T00:00:00Z', updated_at: '2026-08-22T00:00:00Z', archived_at: null }]} onConversation={onConversation} />)

  expect(screen.getByText('Canonical history')).toBeInTheDocument()
  expect(screen.queryByText('Interface review')).not.toBeInTheDocument()
  expect(screen.queryByText('Trip references')).not.toBeInTheDocument()
  expect(screen.queryByText('Reading notes')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: /canonical history/i }))
  expect(onConversation).toHaveBeenCalledWith('conversation-real')
})

it('keeps running state scoped to each Conversation across selection and terminal updates', () => {
  const conversations = [
    { id: 'conversation-a', title: 'Conversation A', created_at: '2026-08-22T00:00:00Z', updated_at: '2026-08-22T00:00:00Z', archived_at: null },
    { id: 'conversation-b', title: 'Conversation B', created_at: '2026-08-22T00:01:00Z', updated_at: '2026-08-22T00:01:00Z', archived_at: null },
  ]
  const view = render(<Sidebar page="chat" onNavigate={() => undefined} onNewConversation={() => undefined} conversations={conversations} activeConversationId="conversation-b" runningConversationIds={new Set(['conversation-a'])} />)
  const conversationA = screen.getByRole('button', { name: /conversation a/i })
  const conversationB = screen.getByRole('button', { name: /conversation b/i })
  expect(within(conversationA).getByText('Running')).toBeInTheDocument()
  expect(within(conversationB).queryByText('Running')).not.toBeInTheDocument()
  expect(conversationB).toHaveAttribute('aria-current', 'page')

  view.rerender(<Sidebar page="chat" onNavigate={() => undefined} onNewConversation={() => undefined} conversations={conversations} activeConversationId="conversation-b" runningConversationIds={new Set(['conversation-a', 'conversation-b'])} />)
  expect(within(screen.getByRole('button', { name: /conversation a/i })).getByText('Running')).toBeInTheDocument()
  expect(within(screen.getByRole('button', { name: /conversation b/i })).getByText('Running')).toBeInTheDocument()

  view.rerender(<Sidebar page="chat" onNavigate={() => undefined} onNewConversation={() => undefined} conversations={conversations} activeConversationId="conversation-a" runningConversationIds={new Set()} />)
  expect(screen.queryByText('Running')).not.toBeInTheDocument()
})

it('scrolls a newly selected off-screen Conversation into the independent list viewport', () => {
  const conversations = Array.from({ length: 18 }, (_, index) => ({
    id: `conversation-${index}`,
    title: `Conversation ${index}`,
    created_at: '2026-08-22T00:00:00Z',
    updated_at: '2026-08-22T00:00:00Z',
    archived_at: null,
  }))
  const view = render(<Sidebar page="chat" onNavigate={() => undefined} onNewConversation={() => undefined} conversations={conversations} activeConversationId="conversation-0" />)
  const list = screen.getByTestId('conversation-list')
  const target = screen.getByRole('button', { name: /conversation 17/i })
  vi.spyOn(list, 'getBoundingClientRect').mockReturnValue({ top: 100, bottom: 400 } as DOMRect)
  vi.spyOn(target, 'getBoundingClientRect').mockReturnValue({ top: 700, bottom: 740 } as DOMRect)
  const scrollIntoView = vi.fn()
  Object.defineProperty(target, 'scrollIntoView', { configurable: true, value: scrollIntoView })

  view.rerender(<Sidebar page="chat" onNavigate={() => undefined} onNewConversation={() => undefined} conversations={conversations} activeConversationId="conversation-17" />)
  expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' })
})
