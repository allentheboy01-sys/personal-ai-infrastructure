import { render, screen } from '@testing-library/react'
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
