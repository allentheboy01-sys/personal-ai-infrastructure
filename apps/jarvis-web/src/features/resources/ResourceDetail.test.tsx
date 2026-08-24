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

it('truthfully keeps unsupported video playback unavailable', () => {
  const video = { ...resources[5], title: 'QuickTime clip', presentation: { kind: 'video' as const, label: 'Video' }, capabilities: { detail: true, preview: false, open: false, playback: false }, facts: [{ label: 'Type', value: 'video/quicktime' }] }
  render(<ResourceDetail resource={video} />)

  expect(screen.getByText('Video playback unavailable')).toBeInTheDocument()
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

it('renders native video playback through the Jarvis ResourceRef endpoint', () => {
  const { container } = render(<ResourceDetail resource={resources[5]} />)
  const video = container.querySelector('video')
  const source = container.querySelector('video source')
  expect(video).toHaveAttribute('controls')
  expect(video).toHaveAttribute('preload', 'metadata')
  expect(source).toHaveAttribute('src', expect.stringMatching(/^\/api\/v1\/resources\/.+\/video$/))
  expect(source?.getAttribute('src')).not.toContain('immich')
  expect(screen.getByText('Playback available')).toBeInTheDocument()
})

it('shows a bounded unavailable state when video playback fails', () => {
  const { container } = render(<ResourceDetail resource={resources[5]} />)
  fireEvent.error(container.querySelector('video') as HTMLVideoElement)
  expect(screen.getByText('Video playback unavailable')).toBeInTheDocument()
  expect(container.querySelector('video')).toBeInTheDocument()
})
