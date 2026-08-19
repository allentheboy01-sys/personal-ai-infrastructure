import { render, screen } from '@testing-library/react'
import { resources } from '../../mocks/resources'
import { ResourceDetail } from './ResourceDetail'

it('keeps Gmail message detail metadata-only', () => {
  render(<ResourceDetail resource={resources[2]} />)
  expect(screen.getByText(/message body is unavailable/i)).toBeInTheDocument()
  expect(screen.getByText('No preview')).toBeInTheDocument()
  expect(screen.queryByText(/pdi:resource:/i)).not.toBeInTheDocument()
})
