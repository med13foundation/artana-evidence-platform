import { render, screen } from '@testing-library/react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'

describe('Card Components', () => {
  describe('Card', () => {
    it('renders with default styling', () => {
      render(<Card>Card content</Card>)
      const card = screen.getByText('Card content')
      expect(card).toBeInTheDocument()
      expect(card).toHaveClass('rounded-xl', 'border', 'bg-card', 'text-card-foreground', 'shadow-brand-sm')
    })

    it('applies custom className', () => {
      render(<Card className="custom-class">Content</Card>)
      expect(screen.getByText('Content')).toHaveClass('custom-class')
    })

    it('forwards other props', () => {
      render(<Card data-testid="card-test">Content</Card>)
      expect(screen.getByTestId('card-test')).toBeInTheDocument()
    })
  })

  describe('CardHeader', () => {
    it('renders with default styling', () => {
      render(<CardHeader>Header content</CardHeader>)
      const header = screen.getByText('Header content')
      expect(header).toHaveClass('flex', 'flex-col', 'space-y-1.5', 'p-6')
    })

    it('applies custom className', () => {
      render(<CardHeader className="custom-header">Header</CardHeader>)
      expect(screen.getByText('Header')).toHaveClass('custom-header')
    })
  })

  describe('CardTitle', () => {
    it('renders with default styling', () => {
      render(<CardTitle>Title text</CardTitle>)
      const title = screen.getByRole('heading', { level: 3 })
      expect(title).toHaveClass('text-2xl', 'font-semibold', 'leading-none', 'tracking-tight')
    })

    it('applies custom className', () => {
      render(<CardTitle className="custom-title">Title</CardTitle>)
      expect(screen.getByRole('heading', { level: 3 })).toHaveClass('custom-title')
    })
  })

  describe('CardDescription', () => {
    it('renders with default styling', () => {
      render(<CardDescription>Description text</CardDescription>)
      const description = screen.getByText('Description text')
      expect(description).toHaveClass('text-sm', 'text-muted-foreground')
    })

    it('applies custom className', () => {
      render(<CardDescription className="custom-desc">Description</CardDescription>)
      expect(screen.getByText('Description')).toHaveClass('custom-desc')
    })
  })

  describe('CardContent', () => {
    it('renders with default styling', () => {
      render(<CardContent>Content text</CardContent>)
      const content = screen.getByText('Content text')
      expect(content).toHaveClass('p-6', 'pt-0')
    })

    it('applies custom className', () => {
      render(<CardContent className="custom-content">Content</CardContent>)
      expect(screen.getByText('Content')).toHaveClass('custom-content')
    })
  })

  describe('CardFooter', () => {
    it('renders with default styling', () => {
      render(<CardFooter>Footer content</CardFooter>)
      const footer = screen.getByText('Footer content')
      expect(footer).toHaveClass('flex', 'items-center', 'p-6', 'pt-0')
    })

    it('applies custom className', () => {
      render(<CardFooter className="custom-footer">Footer</CardFooter>)
      expect(screen.getByText('Footer')).toHaveClass('custom-footer')
    })
  })

  describe('Card composition', () => {
    it('renders complete card structure', () => {
      render(
        <Card>
          <CardHeader>
            <CardTitle>Test Card</CardTitle>
            <CardDescription>A test card description</CardDescription>
          </CardHeader>
          <CardContent>
            <p>This is the main content of the card.</p>
          </CardContent>
          <CardFooter>
            <button>Action</button>
          </CardFooter>
        </Card>
      )

      expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Test Card')
      expect(screen.getByText('A test card description')).toBeInTheDocument()
      expect(screen.getByText('This is the main content of the card.')).toBeInTheDocument()
      expect(screen.getByRole('button')).toHaveTextContent('Action')
    })
  })
})
