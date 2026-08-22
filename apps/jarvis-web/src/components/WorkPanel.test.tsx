import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ExecutionPanel } from './WorkPanel'

const steps = [{ id: 'tool:1', label: 'Run Python', detail: 'Running', state: 'current' as const }]

describe('production ExecutionPanel', () => {
  it('uses the canonical Stop callback and exposes Stopping state', () => {
    const stop = vi.fn()
    const view = render(<ExecutionPanel steps={steps} onStop={stop} />)
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    expect(stop).toHaveBeenCalledOnce()

    view.rerender(<ExecutionPanel steps={steps} onStop={stop} stopping />)
    expect(screen.getByRole('button', { name: 'Stopping' })).toBeDisabled()
  })

  it('uses truthful terminal language without a success claim', () => {
    render(<ExecutionPanel steps={[{ id: 'terminal:cancelled', label: 'Cancelled', detail: 'Cancelled', state: 'cancelled' }]} status="cancelled" />)
    expect(screen.getAllByText('Cancelled').length).toBeGreaterThan(0)
    expect(screen.queryByText(/successful/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument()
  })
})
