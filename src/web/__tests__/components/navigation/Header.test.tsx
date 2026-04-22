import { render, screen } from '@testing-library/react'
import { Header } from '@/components/navigation/Header'
import { useSignOut } from '@/hooks/use-sign-out'
import { useSpaceContext } from '@/components/space-context-provider'
import { SpaceSelector } from '@/components/research-spaces/SpaceSelector'
import { ADMIN_BRAND_NAME } from '@/lib/branding'

// Mock dependencies
jest.mock('next-auth/react', () => ({
  useSession: jest.fn(),
}))

jest.mock('@/hooks/use-sign-out', () => ({
  useSignOut: jest.fn(),
}))

jest.mock('@/components/space-context-provider', () => ({
  useSpaceContext: jest.fn(),
}))

jest.mock('@/components/research-spaces/SpaceSelector', () => ({
  SpaceSelector: jest.fn(({ currentSpaceId }) => (
    <div data-testid="space-selector">Space Selector {currentSpaceId || 'none'}</div>
  )),
}))

jest.mock('@/components/navigation/UserMenu', () => ({
  UserMenu: () => <button data-testid="user-menu">User Menu</button>,
}))

import { useSession } from 'next-auth/react'
import type { Session } from 'next-auth'
import type { SessionContextValue } from 'next-auth/react'

describe('Header Component', () => {
  const mockUseSession = useSession as jest.MockedFunction<typeof useSession>
  const mockUseSignOut = useSignOut as jest.MockedFunction<typeof useSignOut>
  const mockUseSpaceContext = useSpaceContext as jest.MockedFunction<typeof useSpaceContext>

  const mockSignOut = jest.fn()
  const baseUser = {
    id: 'user-1',
    email: 'test@example.com',
    username: 'test-user',
    full_name: 'Test User',
    role: 'admin',
    email_verified: true,
    access_token: 'token-part1.token-part2.token-part3',
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

  beforeEach(() => {
    jest.clearAllMocks()

    mockUseSession.mockReturnValue(buildSessionValue(mockSession, 'authenticated'))

    mockUseSignOut.mockReturnValue({
      signOut: mockSignOut,
      isSigningOut: false,
    })

    mockUseSpaceContext.mockReturnValue({
      currentSpaceId: null,
      setCurrentSpaceId: jest.fn(),
      isLoading: false,
      spaces: [],
      spaceTotal: 0,
    })
  })

  describe('Rendering', () => {
    it('renders all navigation elements', () => {
      render(<Header />)

      expect(screen.getByText(ADMIN_BRAND_NAME)).toBeInTheDocument()
      expect(screen.getByTestId('space-selector')).toBeInTheDocument()
      expect(screen.getByTestId('user-menu')).toBeInTheDocument()
    })

    it('does not show Data Sources button in header (moved to dashboard)', () => {
      mockUseSpaceContext.mockReturnValue({
        currentSpaceId: 'space-123',
        setCurrentSpaceId: jest.fn(),
        isLoading: false,
        spaces: [],
        spaceTotal: 0,
      })

      render(<Header />)

      // Data Sources button is no longer in the header
      expect(screen.queryByRole('link', { name: /data sources/i })).not.toBeInTheDocument()
    })

    it('renders UserMenu component', () => {
      render(<Header />)

      expect(screen.getByTestId('user-menu')).toBeInTheDocument()
    })

    it('renders dashboard logo link', () => {
      render(<Header />)

      const logoLink = screen.getByRole('link', { name: /artana\.bio admin/i })
      expect(logoLink).toBeInTheDocument()
      expect(logoLink).toHaveAttribute('href', '/dashboard')
    })
  })

  describe('UserMenu Integration', () => {
    it('renders UserMenu component', () => {
      render(<Header />)

      expect(screen.getByTestId('user-menu')).toBeInTheDocument()
    })
  })

  describe('Space Selector Integration', () => {
    it('passes currentSpaceId to SpaceSelector', () => {
      mockUseSpaceContext.mockReturnValue({
        currentSpaceId: 'space-456',
        setCurrentSpaceId: jest.fn(),
        isLoading: false,
        spaces: [],
        spaceTotal: 0,
      })

      render(<Header />)

      expect(SpaceSelector).toHaveBeenCalledWith(
        { currentSpaceId: 'space-456' },
        expect.any(Object)
      )
    })

    it('passes undefined to SpaceSelector when no space is selected', () => {
      mockUseSpaceContext.mockReturnValue({
        currentSpaceId: null,
        setCurrentSpaceId: jest.fn(),
        isLoading: false,
        spaces: [],
        spaceTotal: 0,
      })

      render(<Header />)

      expect(SpaceSelector).toHaveBeenCalledWith(
        { currentSpaceId: undefined },
        expect.any(Object)
      )
    })
  })

  describe('User Session Handling', () => {
    it('handles missing session gracefully', () => {
      mockUseSession.mockReturnValue(buildSessionValue(null, 'unauthenticated'))

      render(<Header />)

      // Should still render, but role might not be visible
      expect(screen.getByText(ADMIN_BRAND_NAME)).toBeInTheDocument()
    })

    it('handles different user roles', () => {
      const researcherSession: Session = {
        user: {
          ...baseUser,
          id: 'user-2',
          email: 'researcher@example.com',
          username: 'researcher',
          full_name: 'Researcher',
          role: 'researcher',
        },
        expires: mockSession.expires,
      }
      mockUseSession.mockReturnValue(buildSessionValue(researcherSession, 'authenticated'))

      render(<Header />)

      // UserMenu component handles role display now
      expect(screen.getByTestId('user-menu')).toBeInTheDocument()
    })
  })
})
