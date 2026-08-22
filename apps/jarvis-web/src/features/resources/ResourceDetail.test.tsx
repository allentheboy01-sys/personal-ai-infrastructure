import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { resources } from '../../mocks/resources'
import { ResourceDetail } from './ResourceDetail'

it('keeps Gmail message detail metadata-only', () => {
  render(<ResourceDetail resource={resources[2]} />)
  expect(screen.getByText(/message body is unavailable/i)).toBeInTheDocument()
  expect(screen.getByText('No preview')).toBeInTheDocument()
  expect(screen.queryByText(/pdi:resource:/i)).not.toBeInTheDocument()
})

it('truthfully keeps video preview unavailable', () => {
  const video = { ...resources[4], title: 'QuickTime clip', presentation: { kind: 'generic' as const, label: 'Video' }, capabilities: { detail: true, preview: false, open: false }, facts: [{ label: 'Type', value: 'video/quicktime' }] }
  render(<ResourceDetail resource={video} />)

  expect(screen.getByText('No preview')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /enlarge/i })).not.toBeInTheDocument()
})

it('uses the preview representation and opens an accessible lightbox', async () => {
  const resource = { ...resources[0], presentation: { ...resources[0].presentation, thumbnail: '/representation?kind=thumbnail', preview: '/representation?kind=preview' } }
  render(<ResourceDetail resource={resource} />)

  const trigger = screen.getByRole('button', { name: `Enlarge ${resource.title}` })
  expect(trigger.querySelector('img')).toHaveAttribute('src', '/representation?kind=preview')
  await userEvent.click(trigger)
  expect(screen.getByRole('dialog', { name: resource.title })).toBeInTheDocument()
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('dialog', { name: resource.title })).not.toBeInTheDocument()
})

it('falls back cleanly when the detail preview fails', () => {
  render(<ResourceDetail resource={resources[0]} />)
  fireEvent.error(screen.getByRole('img', { name: resources[0].title }))
  expect(screen.getByText('Preview unavailable')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: `Enlarge ${resources[0].title}` })).not.toBeInTheDocument()
})
