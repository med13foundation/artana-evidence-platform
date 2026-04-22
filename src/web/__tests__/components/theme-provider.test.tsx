import { render } from '@testing-library/react'
import { ThemeProvider } from '@/components/theme-provider'

describe('ThemeProvider', () => {
  it('renders children with theme provider', () => {
    const { container } = render(
      <ThemeProvider>
        <div>Test content</div>
      </ThemeProvider>
    )

    expect(container.firstChild).toBeInTheDocument()
    expect(container.firstChild).toHaveTextContent('Test content')
  })

  it('renders with different children types', () => {
    const { container } = render(
      <ThemeProvider>
        <span>Span content</span>
        <p>Paragraph content</p>
      </ThemeProvider>
    )

    expect(container.firstChild).toHaveTextContent('Span contentParagraph content')
  })
})
