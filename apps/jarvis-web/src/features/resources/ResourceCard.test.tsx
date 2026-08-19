import { render, screen } from '@testing-library/react'
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
})
