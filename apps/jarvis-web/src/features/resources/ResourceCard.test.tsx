import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { resources } from '../../mocks/resources'
import { ResourceCard } from './ResourceCard'

describe('ResourceCard', () => {
  it.each(resources.slice(0, 4))('renders $presentation.kind through the shared card', (resource) => {
    render(<ResourceCard resource={resource} />)
    expect(screen.getByRole('article')).toHaveTextContent(resource.title)
    expect(screen.getByText(resource.provider)).toBeInTheDocument()
  })

  it('opens a resource through an accessible button', async () => {
    const onOpen = vi.fn()
    render(<ResourceCard resource={resources[1]} onOpen={onOpen} />)
    await userEvent.click(screen.getByRole('button', { name: /view research notes/i }))
    expect(onOpen).toHaveBeenCalledWith(resources[1])
  })

  it('uses only the thumbnail representation in the grid', () => {
    const resource = { ...resources[0], presentation: { ...resources[0].presentation, thumbnail: '/representation?kind=thumbnail', preview: '/representation?kind=preview' } }
    render(<ResourceCard resource={resource} />)
    expect(screen.getByRole('img', { name: resource.title })).toHaveAttribute('src', '/representation?kind=thumbnail')
  })

  it('replaces a failed thumbnail with a graceful placeholder', () => {
    render(<ResourceCard resource={resources[0]} />)
    fireEvent.error(screen.getByRole('img', { name: resources[0].title }))
    expect(screen.queryByRole('img', { name: resources[0].title })).not.toBeInTheDocument()
    expect(screen.getByRole('img', { name: `${resources[0].title} preview unavailable` })).toBeInTheDocument()
  })
})
