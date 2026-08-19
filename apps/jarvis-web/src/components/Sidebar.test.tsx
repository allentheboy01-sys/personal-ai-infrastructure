import { render, screen } from '@testing-library/react'
import { Sidebar } from './Sidebar'

it('contains only the frozen primary navigation', () => {
  render(<Sidebar page="chat" onNavigate={() => undefined} />)
  const nav = screen.getByRole('navigation', { name: 'Primary navigation' })
  expect(nav).toHaveTextContent('Chat')
  expect(nav).toHaveTextContent('Resources')
  expect(nav).toHaveTextContent('Providers')
  expect(nav).not.toHaveTextContent(/activity|memory|tasks|marketplace/i)
})
