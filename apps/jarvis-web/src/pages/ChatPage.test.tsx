import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatPage } from './ChatPage'
import type { ConversationMessage } from '../models/chat'

class MockResizeObserver {
  static instances: MockResizeObserver[] = []
  callback: ResizeObserverCallback
  observe = vi.fn()
  disconnect = vi.fn()
  unobserve = vi.fn()

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
    MockResizeObserver.instances.push(this)
  }

  resize(height: number) {
    this.callback([{ contentRect: { height } } as ResizeObserverEntry], this as unknown as ResizeObserver)
  }
}

const userMessage: ConversationMessage = { id: 'user-1', role: 'user', body: 'Hello' }
const assistantMessage: ConversationMessage = { id: 'assistant-1', role: 'assistant', body: 'A growing answer' }

function geometry(element: HTMLElement, values: { height: number; top: number; viewport: number }, smoothImmediate = true) {
  let scrollTop = values.top
  let scrollHeight = values.height
  const scrollTo = vi.fn(({ top, behavior }: ScrollToOptions) => {
    if (behavior !== 'smooth' || smoothImmediate) scrollTop = Number(top)
  })
  Object.defineProperties(element, {
    scrollHeight: { configurable: true, get: () => scrollHeight },
    clientHeight: { configurable: true, get: () => values.viewport },
    scrollTop: { configurable: true, get: () => scrollTop, set: (value: number) => { scrollTop = value } },
    scrollTo: { configurable: true, value: scrollTo },
  })
  return { scrollTo, getTop: () => scrollTop, setTop: (value: number) => { scrollTop = value }, setHeight: (value: number) => { scrollHeight = value } }
}

describe('ChatPage auto-follow', () => {
  beforeEach(() => vi.stubGlobal('ResizeObserver', MockResizeObserver))
  afterEach(() => { vi.unstubAllGlobals(); MockResizeObserver.instances = [] })

  it('keeps a near-bottom viewport pinned as assistant content grows', () => {
    const view = render(<ChatPage working={false} conversationKey="conversation-a" messages={[userMessage]} onResource={() => undefined} />)
    const scroller = view.container.querySelector('.chat-scroll') as HTMLElement
    const box = geometry(scroller, { height: 1000, top: 800, viewport: 200 })
    fireEvent.scroll(scroller)
    box.setHeight(1240)
    view.rerender(<ChatPage working conversationKey="conversation-a" messages={[userMessage, assistantMessage]} progress="composing" onResource={() => undefined} />)

    expect(box.scrollTo).toHaveBeenLastCalledWith({ top: 1240, behavior: 'auto' })
    expect(screen.queryByRole('button', { name: 'Jump to latest' })).not.toBeInTheDocument()
  })

  it('respects upward user scrolling and offers a jump that resumes following', () => {
    const view = render(<ChatPage working conversationKey="conversation-a" messages={[userMessage]} progress="processing" onResource={() => undefined} />)
    const scroller = view.container.querySelector('.chat-scroll') as HTMLElement
    const box = geometry(scroller, { height: 1000, top: 250, viewport: 200 })
    fireEvent.scroll(scroller)
    const callsBeforeGrowth = box.scrollTo.mock.calls.length
    box.setHeight(1200)
    view.rerender(<ChatPage working conversationKey="conversation-a" messages={[userMessage, assistantMessage]} progress="composing" onResource={() => undefined} />)

    expect(box.scrollTo).toHaveBeenCalledTimes(callsBeforeGrowth)
    const jump = screen.getByRole('button', { name: 'Jump to latest' })
    fireEvent.click(jump)
    expect(box.scrollTo).toHaveBeenLastCalledWith({ top: 1200, behavior: 'smooth' })
    expect(screen.queryByRole('button', { name: 'Jump to latest' })).not.toBeInTheDocument()
  })

  it('retains pinned ownership while a smooth jump emits intermediate scroll events', () => {
    const view = render(<ChatPage working conversationKey="conversation-a" messages={[userMessage]} progress="processing" onResource={() => undefined} />)
    const scroller = view.container.querySelector('.chat-scroll') as HTMLElement
    const box = geometry(scroller, { height: 1000, top: 200, viewport: 200 }, false)
    fireEvent.scroll(scroller)
    box.setHeight(1200)
    view.rerender(<ChatPage working conversationKey="conversation-a" messages={[userMessage, assistantMessage]} progress="searching" onResource={() => undefined} />)

    fireEvent.click(screen.getByRole('button', { name: 'Jump to latest' }))
    fireEvent.scroll(scroller)
    box.setHeight(1400)
    view.rerender(<ChatPage working conversationKey="conversation-a" messages={[userMessage, { ...assistantMessage, body: 'A longer answer' }]} progress="composing" onResource={() => undefined} />)

    expect(box.scrollTo).toHaveBeenLastCalledWith({ top: 1400, behavior: 'auto' })
    expect(screen.queryByRole('button', { name: 'Jump to latest' })).not.toBeInTheDocument()
  })

  it('releases a smooth jump when genuine user input takes ownership', () => {
    const view = render(<ChatPage working conversationKey="conversation-a" messages={[userMessage]} progress="processing" onResource={() => undefined} />)
    const scroller = view.container.querySelector('.chat-scroll') as HTMLElement
    const box = geometry(scroller, { height: 1000, top: 200, viewport: 200 }, false)
    fireEvent.scroll(scroller)
    box.setHeight(1200)
    view.rerender(<ChatPage working conversationKey="conversation-a" messages={[userMessage, assistantMessage]} progress="searching" onResource={() => undefined} />)

    fireEvent.click(screen.getByRole('button', { name: 'Jump to latest' }))
    fireEvent.wheel(scroller)
    box.setTop(250)
    fireEvent.scroll(scroller)
    const callsBeforeGrowth = box.scrollTo.mock.calls.length
    box.setHeight(1400)
    view.rerender(<ChatPage working conversationKey="conversation-a" messages={[userMessage, { ...assistantMessage, body: 'A longer answer' }]} progress="composing" onResource={() => undefined} />)

    expect(box.scrollTo).toHaveBeenCalledTimes(callsBeforeGrowth)
    expect(screen.getByRole('button', { name: 'Jump to latest' })).toBeInTheDocument()
  })

  it('resumes automatic following when the user manually returns near the bottom', () => {
    const view = render(<ChatPage working conversationKey="conversation-a" messages={[userMessage]} progress="processing" onResource={() => undefined} />)
    const scroller = view.container.querySelector('.chat-scroll') as HTMLElement
    const box = geometry(scroller, { height: 1000, top: 200, viewport: 200 })
    fireEvent.scroll(scroller)
    box.setHeight(1100)
    view.rerender(<ChatPage working conversationKey="conversation-a" messages={[userMessage, assistantMessage]} progress="composing" onResource={() => undefined} />)
    expect(screen.getByRole('button', { name: 'Jump to latest' })).toBeInTheDocument()

    box.setTop(900)
    fireEvent.scroll(scroller)
    expect(screen.queryByRole('button', { name: 'Jump to latest' })).not.toBeInTheDocument()
    box.setHeight(1300)
    view.rerender(<ChatPage working conversationKey="conversation-a" messages={[userMessage, { ...assistantMessage, body: 'A longer growing answer' }]} progress="composing" onResource={() => undefined} />)
    expect(box.scrollTo).toHaveBeenLastCalledWith({ top: 1300, behavior: 'auto' })
  })

  it('follows asynchronous resource layout growth only while pinned', () => {
    const view = render(<ChatPage working conversationKey="conversation-a" messages={[userMessage]} progress="searching" onResource={() => undefined} />)
    const scroller = view.container.querySelector('.chat-scroll') as HTMLElement
    const box = geometry(scroller, { height: 900, top: 700, viewport: 200 })
    fireEvent.scroll(scroller)
    box.setHeight(1100)
    act(() => MockResizeObserver.instances.at(-1)?.resize(1100))
    expect(box.scrollTo).toHaveBeenLastCalledWith({ top: 1100, behavior: 'auto' })

    box.setTop(200)
    fireEvent.scroll(scroller)
    box.setHeight(1300)
    act(() => MockResizeObserver.instances.at(-1)?.resize(1300))
    expect(screen.getByRole('button', { name: 'Jump to latest' })).toBeInTheDocument()
  })
})
