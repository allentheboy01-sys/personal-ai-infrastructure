import { render, screen } from '@testing-library/react'
import { providers } from '../../mocks/providers'
import { ProviderCard } from './ProviderCard'

it.each(providers)('renders $status as product language', (provider) => {
  render(<ProviderCard provider={provider} />)
  expect(screen.getByRole('button', { name: `View ${provider.displayName}` })).toBeInTheDocument()
  expect(screen.getByText(provider.accessMode)).toBeInTheDocument()
  expect(screen.queryByText(/pipeline|credential|server url/i)).not.toBeInTheDocument()
})
