import { render, screen } from '@testing-library/react'
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

  it('does not infer structured resources from prose identifiers', () => {
    render(<AssistantMessage message={{ id: 'assistant-1', role: 'assistant', body: 'Reference: pdi:resource:11111111-1111-4111-8111-111111111111' }} />)

    expect(screen.getByText(/pdi:resource:/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /view/i })).not.toBeInTheDocument()
  })
})
