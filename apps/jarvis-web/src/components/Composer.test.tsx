import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Composer } from './Composer'

describe('Composer', () => {
  it('submits with Enter and clears the input', async () => {
    const onSubmit = vi.fn()
    render(<Composer onSubmit={onSubmit} />)
    const input = screen.getByLabelText('Message Jarvis')
    await userEvent.type(input, 'Find my notes{enter}')
    expect(onSubmit).toHaveBeenCalledWith('Find my notes')
    expect(input).toHaveValue('')
  })

  it('exposes a stop affordance while running', () => {
    const view = render(<Composer running />)
    expect(screen.getByRole('button', { name: 'Stop response' })).toBeInTheDocument()
    expect(screen.getByLabelText('Message Jarvis')).toBeDisabled()
    view.rerender(<Composer running stopping />)
    expect(screen.getByRole('button', { name: 'Stopping response' })).toBeDisabled()
  })

  it('keeps attachments explicitly deferred', () => {
    render(<Composer />)
    expect(screen.getByRole('button', { name: 'Attachments coming later' })).toBeDisabled()
  })
})
