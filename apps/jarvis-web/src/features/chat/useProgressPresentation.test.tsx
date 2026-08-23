import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PROGRESS_MIN_VISIBLE_MS, useProgressPresentation } from './useProgressPresentation'

describe('progress presentation controller', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-23T00:00:00Z'))
  })

  afterEach(() => vi.useRealTimers())

  it('keeps searching observable across a non-terminal replay burst', () => {
    const { result } = renderHook(() => useProgressPresentation('processing'))

    act(() => {
      result.current.presentProgress('searching')
      result.current.presentProgress('search_complete')
      result.current.presentProgress('composing')
    })
    expect(result.current.progress).toBe('searching')

    act(() => vi.advanceTimersByTime(PROGRESS_MIN_VISIBLE_MS - 1))
    expect(result.current.progress).toBe('searching')
    act(() => vi.advanceTimersByTime(1))
    expect(result.current.progress).toBe('composing')
  })

  it('coalesces repeated semantic states without extending their lifetime', () => {
    const { result } = renderHook(() => useProgressPresentation('processing'))

    act(() => {
      result.current.presentProgress('searching')
      vi.advanceTimersByTime(100)
      result.current.presentProgress('searching')
      result.current.presentProgress('searching')
      result.current.presentProgress('composing')
    })
    expect(vi.getTimerCount()).toBe(1)
    act(() => vi.advanceTimersByTime(PROGRESS_MIN_VISIBLE_MS - 100))
    expect(result.current.progress).toBe('composing')
  })

  it('lets terminal cleanup preempt cosmetic progress immediately', () => {
    const { result } = renderHook(() => useProgressPresentation('processing'))

    act(() => {
      result.current.presentProgress('searching')
      result.current.presentProgress('composing')
      result.current.clearProgress()
    })
    expect(result.current.progress).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not leak a queued state across a Conversation or Turn reset', () => {
    const { result } = renderHook(() => useProgressPresentation('processing'))

    act(() => {
      result.current.presentProgress('searching')
      result.current.presentProgress('composing')
      result.current.resetProgress(null)
      result.current.resetProgress('computing')
      vi.advanceTimersByTime(PROGRESS_MIN_VISIBLE_MS)
    })
    expect(result.current.progress).toBe('computing')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('clears pending presentation on cancellation', () => {
    const { result } = renderHook(() => useProgressPresentation('processing'))

    act(() => {
      result.current.presentProgress('searching')
      result.current.presentProgress('reviewing')
      result.current.clearProgress()
      vi.runAllTimers()
    })
    expect(result.current.progress).toBeNull()
  })
})
