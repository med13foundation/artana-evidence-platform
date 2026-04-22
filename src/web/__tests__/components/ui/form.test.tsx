import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

const testSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  optional: z.string().optional(),
})

type TestFormData = z.infer<typeof testSchema>

function TestForm() {
  const form = useForm<TestFormData>({
    resolver: zodResolver(testSchema),
    mode: 'onBlur',
    defaultValues: {
      email: '',
      password: '',
      optional: '',
    },
  })

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(() => {})}>
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email</FormLabel>
              <FormControl>
                <Input placeholder="Enter email" {...field} />
              </FormControl>
              <FormDescription>Enter your email address</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Password</FormLabel>
              <FormControl>
                <Input type="password" placeholder="Enter password" {...field} />
              </FormControl>
              <FormDescription>Enter your password</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="optional"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Optional Field</FormLabel>
              <FormControl>
                <Input placeholder="Optional" {...field} />
              </FormControl>
              <FormDescription>This field is optional</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit">Submit</Button>
      </form>
    </Form>
  )
}

describe('Form Components', () => {
  describe('Form', () => {
    it('renders form with all fields', () => {
      render(<TestForm />)

      expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/optional field/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument()
    })

    it('displays form descriptions', () => {
      render(<TestForm />)

      expect(screen.getByText('Enter your email address')).toBeInTheDocument()
      expect(screen.getByText('Enter your password')).toBeInTheDocument()
      expect(screen.getByText('This field is optional')).toBeInTheDocument()
    })

    it('displays validation errors on invalid input', async () => {
      const user = userEvent.setup()
      render(<TestForm />)

      const emailInput = screen.getByLabelText(/email/i)
      await user.type(emailInput, 'invalid-email')
      await user.tab()

      await waitFor(() => {
        expect(screen.getByText('Invalid email address')).toBeInTheDocument()
      })
    })

    it('displays validation errors for password length', async () => {
      const user = userEvent.setup()
      render(<TestForm />)

      const passwordInput = screen.getByLabelText(/password/i)
      await user.type(passwordInput, 'short')
      await user.tab()

      await waitFor(() => {
        expect(
          screen.getByText('Password must be at least 8 characters')
        ).toBeInTheDocument()
      })
    })

    it('does not display errors for valid input', async () => {
      const user = userEvent.setup()
      render(<TestForm />)

      const emailInput = screen.getByLabelText(/email/i)
      await user.type(emailInput, 'test@example.com')
      await user.tab()

      await waitFor(() => {
        expect(screen.queryByText('Invalid email address')).not.toBeInTheDocument()
      })
    })

    it('applies custom className to FormItem', () => {
      function TestComponent() {
        const form = useForm<TestFormData>({
          resolver: zodResolver(testSchema),
          mode: 'onBlur',
          defaultValues: {
            email: '',
          },
        })

        return (
          <Form {...form}>
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem className="custom-item-class" data-testid="form-item">
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value || ''} />
                  </FormControl>
                </FormItem>
              )}
            />
          </Form>
        )
      }

      render(<TestComponent />)

      expect(screen.getByTestId('form-item')).toHaveClass('custom-item-class')
    })

    it('applies custom className to FormLabel', () => {
      function TestComponent() {
        const form = useForm<TestFormData>({
          resolver: zodResolver(testSchema),
          mode: 'onBlur',
          defaultValues: {
            email: '',
          },
        })

        return (
          <Form {...form}>
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="custom-label-class" data-testid="form-label">
                    Email
                  </FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value || ''} />
                  </FormControl>
                </FormItem>
              )}
            />
          </Form>
        )
      }

      render(<TestComponent />)

      expect(screen.getByTestId('form-label')).toHaveClass('custom-label-class')
    })

    it('applies custom className to FormDescription', () => {
      function TestComponent() {
        const form = useForm<TestFormData>({
          resolver: zodResolver(testSchema),
          mode: 'onBlur',
          defaultValues: {
            email: '',
          },
        })

        return (
          <Form {...form}>
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value || ''} />
                  </FormControl>
                  <FormDescription className="custom-desc-class" data-testid="form-desc">
                    Description
                  </FormDescription>
                </FormItem>
              )}
            />
          </Form>
        )
      }

      render(<TestComponent />)

      expect(screen.getByTestId('form-desc')).toHaveClass('custom-desc-class')
    })

    it('applies custom className to FormMessage', async () => {
      const user = userEvent.setup()

      function TestComponent() {
        const form = useForm<TestFormData>({
          resolver: zodResolver(testSchema),
          mode: 'onBlur',
          defaultValues: {
            email: '',
          },
        })

        return (
          <Form {...form}>
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value || ''} />
                  </FormControl>
                  <FormMessage className="custom-message-class" data-testid="form-message" />
                </FormItem>
              )}
            />
          </Form>
        )
      }

      render(<TestComponent />)

      const emailInput = screen.getByLabelText(/email/i)
      await user.type(emailInput, 'invalid')
      await user.tab()

      await waitFor(() => {
        const message = screen.getByTestId('form-message')
        expect(message).toHaveClass('custom-message-class')
        expect(message).toHaveTextContent('Invalid email address')
      })
    })

    it('applies error styling to FormLabel when field has error', async () => {
      const user = userEvent.setup()

      function TestComponent() {
        const form = useForm<TestFormData>({
          resolver: zodResolver(testSchema),
          mode: 'onBlur',
          defaultValues: {
            email: '',
          },
        })

        return (
          <Form {...form}>
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel data-testid="form-label">Email</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value || ''} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </Form>
        )
      }

      render(<TestComponent />)

      const emailInput = screen.getByLabelText(/email/i)
      await user.type(emailInput, 'invalid')
      await user.tab()

      await waitFor(() => {
        const label = screen.getByTestId('form-label')
        expect(label).toHaveClass('text-destructive')
      })
    })

    it('sets aria-invalid on FormControl when field has error', async () => {
      const user = userEvent.setup()

      function TestComponent() {
        const form = useForm<TestFormData>({
          resolver: zodResolver(testSchema),
          mode: 'onBlur',
          defaultValues: {
            email: '',
          },
        })

        return (
          <Form {...form}>
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input data-testid="form-input" {...field} value={field.value || ''} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </Form>
        )
      }

      render(<TestComponent />)

      const emailInput = screen.getByTestId('form-input')
      await user.type(emailInput, 'invalid')
      await user.tab()

      await waitFor(() => {
        expect(emailInput).toHaveAttribute('aria-invalid', 'true')
      })
    })

    it('handles form submission with valid data', async () => {
      const user = userEvent.setup()
      const handleSubmit = jest.fn()

      function TestComponent() {
        const form = useForm<TestFormData>({
          resolver: zodResolver(testSchema),
          mode: 'onBlur',
          defaultValues: {
            email: '',
            password: '',
          },
        })

        return (
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleSubmit)}>
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Password</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit">Submit</Button>
            </form>
          </Form>
        )
      }

      render(<TestComponent />)

      await user.type(screen.getByLabelText(/email/i), 'test@example.com')
      await user.type(screen.getByLabelText(/password/i), 'password123')
      await user.click(screen.getByRole('button', { name: /submit/i }))

      await waitFor(() => {
        expect(handleSubmit).toHaveBeenCalledWith(
          {
            email: 'test@example.com',
            password: 'password123',
            optional: undefined,
          },
          expect.anything()
        )
      })
    })
  })
})
