import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

describe('Dialog Components', () => {
  describe('Dialog', () => {
    it('renders dialog trigger', () => {
      render(
        <Dialog>
          <DialogTrigger asChild>
            <Button>Open Dialog</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Test Dialog</DialogTitle>
              <DialogDescription>Test description</DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>
      )

      expect(screen.getByRole('button', { name: /open dialog/i })).toBeInTheDocument()
    })

    it('opens dialog when trigger is clicked', async () => {
      const user = userEvent.setup()
      render(
        <Dialog>
          <DialogTrigger asChild>
            <Button>Open Dialog</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Test Dialog</DialogTitle>
              <DialogDescription>Test description</DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>
      )

      const trigger = screen.getByRole('button', { name: /open dialog/i })
      await user.click(trigger)

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })
      expect(screen.getByText('Test Dialog')).toBeInTheDocument()
      expect(screen.getByText('Test description')).toBeInTheDocument()
    })

    it('closes dialog when close button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <Dialog defaultOpen>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Test Dialog</DialogTitle>
              <DialogDescription>Test description</DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>
      )

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      const closeButton = screen.getByRole('button', { name: /close/i })
      await user.click(closeButton)

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      })
    })

    it('closes dialog when Escape key is pressed', async () => {
      const user = userEvent.setup()
      render(
        <Dialog defaultOpen>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Test Dialog</DialogTitle>
              <DialogDescription>Test description</DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>
      )

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      await user.keyboard('{Escape}')

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      })
    })

    it('renders dialog with footer', async () => {
      const user = userEvent.setup()
      render(
        <Dialog defaultOpen>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Test Dialog</DialogTitle>
              <DialogDescription>Test description</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button>Cancel</Button>
              <Button>Confirm</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /confirm/i })).toBeInTheDocument()
    })

    it('applies custom className to DialogContent', async () => {
      render(
        <Dialog defaultOpen>
          <DialogContent className="custom-dialog-class" data-testid="dialog-content">
            <DialogHeader>
              <DialogTitle>Test Dialog</DialogTitle>
              <DialogDescription>Test description</DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>
      )

      await waitFor(() => {
        const content = screen.getByTestId('dialog-content')
        expect(content).toHaveClass('custom-dialog-class')
      })
    })

    it('applies custom className to DialogHeader', async () => {
      render(
        <Dialog defaultOpen>
          <DialogContent>
            <DialogHeader className="custom-header-class" data-testid="dialog-header">
              <DialogTitle>Test Dialog</DialogTitle>
              <DialogDescription>Test description</DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>
      )

      await waitFor(() => {
        const header = screen.getByTestId('dialog-header')
        expect(header).toHaveClass('custom-header-class')
      })
    })

    it('applies custom className to DialogTitle', async () => {
      render(
        <Dialog defaultOpen>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="custom-title-class" data-testid="dialog-title">
                Test Dialog
              </DialogTitle>
              <DialogDescription>Test description</DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>
      )

      await waitFor(() => {
        const title = screen.getByTestId('dialog-title')
        expect(title).toHaveClass('custom-title-class')
      })
    })

    it('applies custom className to DialogDescription', async () => {
      render(
        <Dialog defaultOpen>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Test Dialog</DialogTitle>
              <DialogDescription className="custom-desc-class" data-testid="dialog-desc">
                Test description
              </DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>
      )

      await waitFor(() => {
        const desc = screen.getByTestId('dialog-desc')
        expect(desc).toHaveClass('custom-desc-class')
      })
    })

    it('applies custom className to DialogFooter', async () => {
      render(
        <Dialog defaultOpen>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Test Dialog</DialogTitle>
              <DialogDescription>Test description</DialogDescription>
            </DialogHeader>
            <DialogFooter className="custom-footer-class" data-testid="dialog-footer">
              <Button>Action</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )

      await waitFor(() => {
        const footer = screen.getByTestId('dialog-footer')
        expect(footer).toHaveClass('custom-footer-class')
      })
    })

    it('renders complete dialog structure', async () => {
      render(
        <Dialog defaultOpen>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Complete Dialog</DialogTitle>
              <DialogDescription>This is a complete dialog structure</DialogDescription>
            </DialogHeader>
            <div>Dialog content goes here</div>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline">Cancel</Button>
              </DialogClose>
              <Button>Confirm</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      expect(screen.getByText('Complete Dialog')).toBeInTheDocument()
      expect(screen.getByText('This is a complete dialog structure')).toBeInTheDocument()
      expect(screen.getByText('Dialog content goes here')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /confirm/i })).toBeInTheDocument()
    })
  })
})
