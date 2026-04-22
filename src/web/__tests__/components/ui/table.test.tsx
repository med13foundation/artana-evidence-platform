import { render, screen } from '@testing-library/react'
import {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
} from '@/components/ui/table'

describe('Table Components', () => {
  describe('Table', () => {
    it('renders table with default styling', () => {
      render(
        <Table data-testid="table">
          <TableBody>
            <TableRow>
              <TableCell>Content</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      const table = screen.getByTestId('table')
      expect(table).toBeInTheDocument()
      expect(table.tagName).toBe('TABLE')
    })

    it('applies custom className', () => {
      render(
        <Table className="custom-table-class" data-testid="table">
          <TableBody>
            <TableRow>
              <TableCell>Content</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      const table = screen.getByTestId('table')
      expect(table).toHaveClass('custom-table-class')
    })

    it('wraps table in scrollable container', () => {
      const { container } = render(
        <Table>
          <TableBody>
            <TableRow>
              <TableCell>Content</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveClass('relative', 'w-full', 'overflow-auto')
    })
  })

  describe('TableHeader', () => {
    it('renders table header', () => {
      render(
        <Table>
          <TableHeader data-testid="header">
            <TableRow>
              <TableHead>Header</TableHead>
            </TableRow>
          </TableHeader>
        </Table>
      )

      const header = screen.getByTestId('header')
      expect(header.tagName).toBe('THEAD')
      expect(header).toBeInTheDocument()
    })

    it('applies custom className', () => {
      render(
        <Table>
          <TableHeader className="custom-header-class" data-testid="header">
            <TableRow>
              <TableHead>Header</TableHead>
            </TableRow>
          </TableHeader>
        </Table>
      )

      expect(screen.getByTestId('header')).toHaveClass('custom-header-class')
    })
  })

  describe('TableBody', () => {
    it('renders table body', () => {
      render(
        <Table>
          <TableBody data-testid="body">
            <TableRow>
              <TableCell>Content</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      const body = screen.getByTestId('body')
      expect(body.tagName).toBe('TBODY')
      expect(body).toBeInTheDocument()
    })

    it('applies custom className', () => {
      render(
        <Table>
          <TableBody className="custom-body-class" data-testid="body">
            <TableRow>
              <TableCell>Content</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      expect(screen.getByTestId('body')).toHaveClass('custom-body-class')
    })
  })

  describe('TableFooter', () => {
    it('renders table footer', () => {
      render(
        <Table>
          <TableFooter data-testid="footer">
            <TableRow>
              <TableCell>Footer</TableCell>
            </TableRow>
          </TableFooter>
        </Table>
      )

      const footer = screen.getByTestId('footer')
      expect(footer.tagName).toBe('TFOOT')
      expect(footer).toBeInTheDocument()
    })

    it('applies custom className', () => {
      render(
        <Table>
          <TableFooter className="custom-footer-class" data-testid="footer">
            <TableRow>
              <TableCell>Footer</TableCell>
            </TableRow>
          </TableFooter>
        </Table>
      )

      expect(screen.getByTestId('footer')).toHaveClass('custom-footer-class')
    })
  })

  describe('TableRow', () => {
    it('renders table row', () => {
      render(
        <Table>
          <TableBody>
            <TableRow data-testid="row">
              <TableCell>Content</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      const row = screen.getByTestId('row')
      expect(row.tagName).toBe('TR')
      expect(row).toBeInTheDocument()
    })

    it('applies custom className', () => {
      render(
        <Table>
          <TableBody>
            <TableRow className="custom-row-class" data-testid="row">
              <TableCell>Content</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      expect(screen.getByTestId('row')).toHaveClass('custom-row-class')
    })

    it('has hover styles', () => {
      render(
        <Table>
          <TableBody>
            <TableRow data-testid="row">
              <TableCell>Content</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      const row = screen.getByTestId('row')
      expect(row).toHaveClass('hover:bg-muted/50')
    })
  })

  describe('TableHead', () => {
    it('renders table header cell', () => {
      render(
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead data-testid="head">Header Cell</TableHead>
            </TableRow>
          </TableHeader>
        </Table>
      )

      const head = screen.getByTestId('head')
      expect(head.tagName).toBe('TH')
      expect(head).toHaveTextContent('Header Cell')
    })

    it('applies custom className', () => {
      render(
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="custom-head-class" data-testid="head">
                Header
              </TableHead>
            </TableRow>
          </TableHeader>
        </Table>
      )

      expect(screen.getByTestId('head')).toHaveClass('custom-head-class')
    })

    it('has proper styling for header cells', () => {
      render(
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead data-testid="head">Header</TableHead>
            </TableRow>
          </TableHeader>
        </Table>
      )

      const head = screen.getByTestId('head')
      expect(head).toHaveClass('font-medium', 'text-muted-foreground')
    })
  })

  describe('TableCell', () => {
    it('renders table cell', () => {
      render(
        <Table>
          <TableBody>
            <TableRow>
              <TableCell data-testid="cell">Cell Content</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      const cell = screen.getByTestId('cell')
      expect(cell.tagName).toBe('TD')
      expect(cell).toHaveTextContent('Cell Content')
    })

    it('applies custom className', () => {
      render(
        <Table>
          <TableBody>
            <TableRow>
              <TableCell className="custom-cell-class" data-testid="cell">
                Content
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      expect(screen.getByTestId('cell')).toHaveClass('custom-cell-class')
    })
  })

  describe('TableCaption', () => {
    it('renders table caption', () => {
      render(
        <Table>
          <TableCaption data-testid="caption">Table Caption</TableCaption>
          <TableBody>
            <TableRow>
              <TableCell>Content</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      const caption = screen.getByTestId('caption')
      expect(caption.tagName).toBe('CAPTION')
      expect(caption).toHaveTextContent('Table Caption')
    })

    it('applies custom className', () => {
      render(
        <Table>
          <TableCaption className="custom-caption-class" data-testid="caption">
            Caption
          </TableCaption>
          <TableBody>
            <TableRow>
              <TableCell>Content</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      expect(screen.getByTestId('caption')).toHaveClass('custom-caption-class')
    })
  })

  describe('Table composition', () => {
    it('renders complete table structure', () => {
      render(
        <Table>
          <TableCaption>Test Table</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell>John Doe</TableCell>
              <TableCell>john@example.com</TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Jane Smith</TableCell>
              <TableCell>jane@example.com</TableCell>
            </TableRow>
          </TableBody>
          <TableFooter>
            <TableRow>
              <TableCell colSpan={2}>Total: 2 users</TableCell>
            </TableRow>
          </TableFooter>
        </Table>
      )

      expect(screen.getByText('Test Table')).toBeInTheDocument()
      expect(screen.getByText('Name')).toBeInTheDocument()
      expect(screen.getByText('Email')).toBeInTheDocument()
      expect(screen.getByText('John Doe')).toBeInTheDocument()
      expect(screen.getByText('john@example.com')).toBeInTheDocument()
      expect(screen.getByText('Jane Smith')).toBeInTheDocument()
      expect(screen.getByText('jane@example.com')).toBeInTheDocument()
      expect(screen.getByText('Total: 2 users')).toBeInTheDocument()
    })

    it('forwards HTML attributes correctly', () => {
      render(
        <Table data-testid="table" aria-label="Test table">
          <TableBody>
            <TableRow data-testid="row" onClick={() => {}}>
              <TableCell data-testid="cell" colSpan={2}>
                Content
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )

      const table = screen.getByTestId('table')
      expect(table).toHaveAttribute('aria-label', 'Test table')

      const row = screen.getByTestId('row')
      expect(row).toBeInTheDocument()

      const cell = screen.getByTestId('cell')
      expect(cell).toHaveAttribute('colSpan', '2')
    })
  })
})
