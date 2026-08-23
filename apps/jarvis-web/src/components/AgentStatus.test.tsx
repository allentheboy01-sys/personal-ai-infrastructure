import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AgentProgress } from '../models/chat'
import { progressWording } from '../features/chat/progressWording'
import { AgentStatus } from './AgentStatus'

describe('AgentStatus safe progress', () => {
  afterEach(() => vi.useRealTimers())

  it('renders deterministic safe progress labels without claiming results', async () => {
    const view = render(<AgentStatus phase="searching" progress="searching" />)
    expect(screen.getByRole('status')).toHaveTextContent(progressWording('searching'))
    view.rerender(<AgentStatus phase="searching" progress="search_complete" />)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(progressWording('search_complete')))
    expect(screen.getByRole('status')).not.toHaveTextContent(/found|result count|successful|found items/i)
    view.rerender(<AgentStatus phase="composing" progress="composing" />)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(progressWording('composing')))
  })

  it('maps every safe semantic phase to a human-readable stable phrase', () => {
    const states: AgentProgress[] = ['processing', 'searching', 'search_complete', 'computing', 'reviewing', 'composing']
    for (const state of states) {
      const first = progressWording(state, 'turn-stable')
      expect(first).toMatch(/\S+ \S+/)
      expect(progressWording(state, 'turn-stable')).toBe(first)
    }
  })

  it('keeps wording stable while elapsed time rerenders the same phase', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-23T00:00:00Z'))
    render(<AgentStatus phase="searching" progress="searching" startedAtMs={Date.now()} />)
    const before = screen.getByRole('status').textContent?.replace(/ · \d+s$/, '')
    act(() => { vi.advanceTimersByTime(2100) })
    expect(screen.getByRole('status').textContent?.replace(/ · \d+s$/, '')).toBe(before)
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
