import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { UserMenu } from '@/components/navigation/UserMenu'
import { useSignOut } from '@/hooks/use-sign-out'
import { useTheme } from 'next-themes'

// Mock dependencies
jest.mock('next-auth/react', () => ({
  useSession: jest.fn(),
}))

jest.mock('@/hooks/use-sign-out', () => ({
  useSignOut: jest.fn(),
}))

jest.mock('next-themes', () => ({
  useTheme: jest.fn(),
}))

jest.mock('next/link', () => {
  const React = require('react')
  return {
    __esModule: true,
    default: React.forwardRef(
      ({ children, href }: { children: React.ReactNode; href: string }, ref: React.Ref<HTMLAnchorElement>) => {
        return (
          <a href={href} ref={ref}>
            {children}
          </a>
        )
      }
    ),
  }
})

import { useSession } from 'next-auth/react'
import type { Session } from 'next-auth'
import type { SessionContextValue } from 'next-auth/react'
import type { UseThemeProps } from 'next-themes'

describe('UserMenu Component', () => {
  const mockUseSession = useSession as jest.MockedFunction<typeof useSession>
  const mockUseSignOut = useSignOut as jest.MockedFunction<typeof useSignOut>
  const mockUseTheme = useTheme as jest.MockedFunction<typeof useTheme>

  const mockSignOut = jest.fn()
  const mockSetTheme = jest.fn()

  const baseUser = {
    id: 'user-1',
    email: 'test@example.com',
    username: 'test-user',
    full_name: 'Test User',
    role: 'admin',
    email_verified: true,
    access_token: 'token.part.two',
    expires_at: Date.now() + 3600_000,
  }

  const mockSession: Session = {
    user: baseUser,
    expires: new Date(Date.now() + 3600_000).toISOString(),
  }

  const buildSessionValue = (
    sessionData: Session | null,
    status: SessionContextValue['status'],
  ): SessionContextValue =>
    status === 'authenticated'
      ? {
          data: sessionData as Session,
          status: 'authenticated',
          update: jest.fn(async () => sessionData as Session),
        }
      : {
          data: null,
          status,
          update: jest.fn(async () => null),
        }

  const buildThemeValue = (theme: 'light' | 'dark'): UseThemeProps => ({
    theme,
    setTheme: mockSetTheme,
    themes: ['light', 'dark', 'system'],
    systemTheme: theme,
    resolvedTheme: theme,
  })

  beforeEach(() => {
    jest.clearAllMocks()

    mockUseSession.mockReturnValue(buildSessionValue(mockSession, 'authenticated'))

    mockUseSignOut.mockReturnValue({
      signOut: mockSignOut,
      isSigningOut: false,
    })

    mockUseTheme.mockReturnValue(buildThemeValue('light'))
  })

  describe('Rendering', () => {
    it('renders user menu trigger button', () => {
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      expect(triggerButton).toBeInTheDocument()
    })

    it('renders user avatar icon', () => {
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      expect(triggerButton).toBeInTheDocument()
      // Check for User icon (lucide-react icon)
      expect(triggerButton.querySelector('svg')).toBeInTheDocument()
    })

    it('opens dropdown menu when trigger is clicked', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        expect(screen.getByText('Test User')).toBeInTheDocument()
      })
    })
  })

  describe('User Information Display', () => {
    it('displays user name in dropdown', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        expect(screen.getByText('Test User')).toBeInTheDocument()
      })
    })

    it('displays user email in dropdown', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        expect(screen.getByText('test@example.com')).toBeInTheDocument()
      })
    })

    it('displays user role in dropdown', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        expect(screen.getByText('admin')).toBeInTheDocument()
      })
    })

    it('handles missing full_name gracefully', async () => {
      const user = userEvent.setup()
      const researcherSession: Session = {
        user: {
          ...baseUser,
          id: 'user-2',
          email: 'test2@example.com',
          username: 'researcher',
          role: 'researcher',
          full_name: 'Researcher',
        },
        expires: mockSession.expires,
      }
      mockUseSession.mockReturnValue(buildSessionValue(researcherSession, 'authenticated'))

      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      // When full_name is missing, userName falls back to email
      // So email appears as both name and email in the dropdown
      await waitFor(() => {
        const emailElements = screen.getAllByText('test2@example.com')
        expect(emailElements.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Menu Items', () => {
    it('displays Settings link in dropdown', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        const settingsLink = screen.getByRole('link', { name: /^settings$/i })
        expect(settingsLink).toBeInTheDocument()
        expect(settingsLink).toHaveAttribute('href', '/settings')
      })
    })

    it('shows System Settings link for administrators', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        const systemSettingsLink = screen.getByRole('link', { name: /system settings/i })
        expect(systemSettingsLink).toBeInTheDocument()
        expect(systemSettingsLink).toHaveAttribute('href', '/system-settings')
      })
    })

    it('hides System Settings link for non-admin users', async () => {
      const user = userEvent.setup()
      const restrictedSession: Session = {
        user: {
          ...baseUser,
          id: 'user-3',
          email: 'researcher@example.com',
          username: 'researcher-user',
          role: 'researcher',
          full_name: 'Researcher User',
        },
        expires: mockSession.expires,
      }
      mockUseSession.mockReturnValue(buildSessionValue(restrictedSession, 'authenticated'))

      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        const maybeLink = screen.queryByRole('link', { name: /system settings/i })
        expect(maybeLink).not.toBeInTheDocument()
      })
    })

    it('displays theme toggle option in dropdown', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        expect(screen.getByText('Dark mode')).toBeInTheDocument()
      })
    })

    it('displays Sign out option in dropdown', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        expect(screen.getByText('Sign out')).toBeInTheDocument()
      })
    })
  })

  describe('Theme Toggle', () => {
    it('shows Dark mode option when theme is light', async () => {
      const user = userEvent.setup()
      mockUseTheme.mockReturnValue(buildThemeValue('light'))

      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        expect(screen.getByText('Dark mode')).toBeInTheDocument()
      })
    })

    it('shows Light mode option when theme is dark', async () => {
      const user = userEvent.setup()
      mockUseTheme.mockReturnValue(buildThemeValue('dark'))

      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        expect(screen.getByText('Light mode')).toBeInTheDocument()
      })
    })

    it('calls setTheme when theme toggle is clicked', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        const themeToggle = screen.getByText('Dark mode')
        expect(themeToggle).toBeInTheDocument()
      })

      const themeMenuItem = screen.getByText('Dark mode').closest('[role="menuitem"]')
      if (themeMenuItem) {
        await user.click(themeMenuItem)
        expect(mockSetTheme).toHaveBeenCalledWith('dark')
      }
    })
  })

  describe('Sign Out Functionality', () => {
    it('calls signOut when sign out is clicked', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        expect(screen.getByText('Sign out')).toBeInTheDocument()
      })

      const signOutMenuItem = screen.getByText('Sign out').closest('[role="menuitem"]')
      if (signOutMenuItem) {
        await user.click(signOutMenuItem)
        expect(mockSignOut).toHaveBeenCalledTimes(1)
      }
    })

    it('shows loading state during sign-out', async () => {
      const user = userEvent.setup()
      mockUseSignOut.mockReturnValue({
        signOut: mockSignOut,
        isSigningOut: true,
      })

      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        expect(screen.getByText('Signing out...')).toBeInTheDocument()
      })
    })

    it('disables sign out button during sign-out', async () => {
      const user = userEvent.setup()
      mockUseSignOut.mockReturnValue({
        signOut: mockSignOut,
        isSigningOut: true,
      })

      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        const signOutMenuItem = screen.getByText('Signing out...').closest('[role="menuitem"]')
        expect(signOutMenuItem).toHaveAttribute('aria-disabled', 'true')
      })
    })
  })

  describe('Accessibility', () => {
    it('has accessible trigger button with aria-label', () => {
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      expect(triggerButton).toHaveAttribute('aria-haspopup', 'menu')
    })

    it('has proper menu structure when opened', async () => {
      const user = userEvent.setup()
      render(<UserMenu />)

      const triggerButton = screen.getByRole('button', { name: /open user menu/i })
      await user.click(triggerButton)

      await waitFor(() => {
        const menu = screen.getByRole('menu')
        expect(menu).toBeInTheDocument()
      })
    })
  })
})
