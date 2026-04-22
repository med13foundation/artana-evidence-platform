import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeToggle } from '@/components/theme-toggle'

// Mock next-themes at the module level
jest.mock('next-themes', () => ({
  useTheme: jest.fn(),
}))

import { useTheme } from 'next-themes'

describe('ThemeToggle', () => {
  const mockUseTheme = useTheme as jest.MockedFunction<typeof useTheme>

  beforeEach(() => {
    mockUseTheme.mockClear()
  })

  it('renders with sun icon for light theme', () => {
    mockUseTheme.mockReturnValue({
      theme: 'light',
      setTheme: jest.fn(),
      themes: ['light', 'dark', 'system'],
    })

    render(<ThemeToggle />)
    const button = screen.getByRole('button')
    expect(button).toBeInTheDocument()

    // Should have both sun and moon icons
    const icons = button.querySelectorAll('svg')
    expect(icons).toHaveLength(2)
  })

  it('renders with moon icon for dark theme', () => {
    mockUseTheme.mockReturnValue({
      theme: 'dark',
      setTheme: jest.fn(),
      themes: ['light', 'dark', 'system'],
    })

    render(<ThemeToggle />)
    const button = screen.getByRole('button')
    expect(button).toBeInTheDocument()

    // Should have both sun and moon icons
    const icons = button.querySelectorAll('svg')
    expect(icons).toHaveLength(2)
  })

  it('has screen reader text', () => {
    mockUseTheme.mockReturnValue({
      theme: 'light',
      setTheme: jest.fn(),
      themes: ['light', 'dark', 'system'],
    })

    render(<ThemeToggle />)
    expect(screen.getByText('Toggle theme')).toBeInTheDocument()
    expect(screen.getByText('Toggle theme')).toHaveClass('sr-only')
  })

  it('applies correct button styling', () => {
    mockUseTheme.mockReturnValue({
      theme: 'light',
      setTheme: jest.fn(),
      themes: ['light', 'dark', 'system'],
    })

    render(<ThemeToggle />)
    const button = screen.getByRole('button')

    expect(button).toHaveClass(
      'inline-flex',
      'items-center',
      'justify-center',
      'whitespace-nowrap',
      'text-sm',
      'font-medium',
      'transition-all',
      'hover:bg-primary/5',
      'h-9',
      'rounded-xl',
      'w-9',
      'px-0'
    )
  })

  it('calls setTheme when clicked', async () => {
    const user = userEvent.setup()
    const mockSetTheme = jest.fn()

    mockUseTheme.mockReturnValue({
      theme: 'light',
      setTheme: mockSetTheme,
      themes: ['light', 'dark', 'system'],
    })

    render(<ThemeToggle />)
    const button = screen.getByRole('button')

    await user.click(button)
    expect(mockSetTheme).toHaveBeenCalledWith('dark')
  })

  it('toggles from dark to light theme', async () => {
    const user = userEvent.setup()
    const mockSetTheme = jest.fn()

    mockUseTheme.mockReturnValue({
      theme: 'dark',
      setTheme: mockSetTheme,
      themes: ['light', 'dark', 'system'],
    })

    render(<ThemeToggle />)
    const button = screen.getByRole('button')

    await user.click(button)
    expect(mockSetTheme).toHaveBeenCalledWith('light')
  })
})
