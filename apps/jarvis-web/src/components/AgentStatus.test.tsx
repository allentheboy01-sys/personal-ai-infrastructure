import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AgentStatus } from './AgentStatus'

describe('AgentStatus safe progress', () => {
  afterEach(() => vi.useRealTimers())

  it('renders deterministic safe progress labels without claiming results', async () => {
    const view = render(<AgentStatus phase="searching" progress="searching" />)
    expect(screen.getByRole('status')).toHaveTextContent('Searching your resources')
    view.rerender(<AgentStatus phase="searching" progress="search_complete" />)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Finished searching, organizing'))
    expect(screen.getByRole('status')).not.toHaveTextContent(/found|result count|successful/i)
    view.rerender(<AgentStatus phase="composing" progress="composing" />)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Composing an answer'))
  })

  it('shows process-local whole-second elapsed time and stops with unmount', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-23T00:00:00Z'))
    const view = render(<AgentStatus phase="thinking" progress="processing" startedAtMs={Date.now()} />)
    expect(screen.getByRole('status')).not.toHaveTextContent('1s')
    act(() => { vi.advanceTimersByTime(2100) })
    expect(screen.getByRole('status')).toHaveTextContent('2s')
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
