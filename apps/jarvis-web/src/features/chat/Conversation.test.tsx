import { render, screen } from '@testing-library/react'
import { resources } from '../../mocks/resources'
import { AssistantMessage } from './Conversation'

describe('assistant Markdown', () => {
  it('renders the supported safe Markdown surface', () => {
    render(<AssistantMessage message={{ id: 'assistant-1', role: 'assistant', body: '**bold**\n\n## Heading\n\n`inline`\n\n```ts\nconst answer = 42\n```\n\n- one\n- two\n\n> quoted' }} />)

    expect(screen.getByText('bold').tagName).toBe('STRONG')
    expect(screen.getByRole('heading', { name: 'Heading', level: 2 })).toBeInTheDocument()
    expect(screen.getByText('inline').tagName).toBe('CODE')
    expect(screen.getByText('const answer = 42').tagName).toBe('CODE')
    expect(screen.getByText('quoted').closest('blockquote')).toBeInTheDocument()
  })

  it('keeps arbitrary raw HTML inert', () => {
    const { container } = render(<AssistantMessage message={{ id: 'assistant-1', role: 'assistant', body: 'Safe text <img src=x onerror="alert(1)"><script>alert(2)</script>' }} />)

    expect(screen.getByText(/safe text/i)).toBeInTheDocument()
    expect(container.querySelector('img')).not.toBeInTheDocument()
    expect(container.querySelector('script')).not.toBeInTheDocument()
  })

  it('opens external links with safe isolation and rejects executable URLs', () => {
    render(<AssistantMessage message={{ id: 'assistant-1', role: 'assistant', body: '[Safe](https://example.com) [Unsafe](javascript:alert(1))' }} />)

    expect(screen.getByRole('link', { name: 'Safe' })).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByRole('link', { name: 'Safe' })).toHaveAttribute('target', '_blank')
    expect(screen.getByText('Unsafe').tagName).not.toBe('A')
  })

  it('autolinks bare HTTP and HTTPS source URLs with external-link isolation', () => {
    render(<AssistantMessage message={{ id: 'assistant-1', role: 'assistant', body: 'HTTPS: https://secure.example/a\n\nHTTP: http://public.example/b' }} />)

    const https = screen.getByRole('link', { name: 'https://secure.example/a' })
    const http = screen.getByRole('link', { name: 'http://public.example/b' })
    expect(https).toHaveAttribute('href', 'https://secure.example/a')
    expect(http).toHaveAttribute('href', 'http://public.example/b')
    for (const link of [https, http]) {
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    }
  })

  it('keeps Chinese and English punctuation outside bare source links', () => {
    render(<AssistantMessage message={{ id: 'assistant-1', role: 'assistant', body: '来源：https://source.example/zh。\n\nSource: https://source.example/en.' }} />)

    expect(screen.getByRole('link', { name: 'https://source.example/zh' })).toHaveAttribute('href', 'https://source.example/zh')
    expect(screen.getByRole('link', { name: 'https://source.example/en' })).toHaveAttribute('href', 'https://source.example/en')
  })

  it('autolinks multiple sources without double-linkifying Markdown links', () => {
    const { container } = render(<AssistantMessage message={{ id: 'assistant-1', role: 'assistant', body: 'A: https://a.example/x\nB: https://b.example/y\n[Example](https://example.com)' }} />)

    expect(screen.getAllByRole('link')).toHaveLength(3)
    expect(screen.getByRole('link', { name: 'Example' })).toHaveAttribute('href', 'https://example.com')
    expect(container.querySelectorAll('a a')).toHaveLength(0)
  })

  it('does not autolink unsafe schemes, email literals, or malformed URL-like text', () => {
    render(<AssistantMessage message={{ id: 'assistant-1', role: 'assistant', body: 'javascript:alert(1) file:///etc/passwd data:text/html,unsafe ftp://example.com person@example.com malformed://example.com' }} />)

    expect(screen.queryAllByRole('link')).toHaveLength(0)
  })

  it('does not infer structured resources from prose identifiers', () => {
    render(<AssistantMessage message={{ id: 'assistant-1', role: 'assistant', body: 'Reference: pdi:resource:11111111-1111-4111-8111-111111111111' }} />)

    expect(screen.getByText(/pdi:resource:/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /view/i })).not.toBeInTheDocument()
  })

  it('reuses the unified resource strip for canonical mixed structured resources', () => {
    render(<AssistantMessage message={{ id: 'assistant-1', role: 'assistant', body: 'Structured results', resources: [resources[0], resources[1], resources[2]] }} />)

    const cards = screen.getAllByRole('article')
    expect(cards).toHaveLength(3)
    expect(cards.map((card) => card.textContent)).toEqual(expect.arrayContaining([
      expect.stringContaining(resources[0].title),
      expect.stringContaining(resources[1].title),
      expect.stringContaining(resources[2].title),
    ]))
    expect(cards[0]).toHaveTextContent(resources[0].title)
    expect(cards[1]).toHaveTextContent(resources[1].title)
    expect(cards[2]).toHaveTextContent(resources[2].title)
  })
})
