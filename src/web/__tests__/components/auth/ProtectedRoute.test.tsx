import { render, screen, waitFor } from '@testing-library/react'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { useSession } from 'next-auth/react'
import type { Session } from 'next-auth'
import type { SessionContextValue } from 'next-auth/react'

const mockReplace = jest.fn()

jest.mock('next-auth/react', () => ({
  useSession: jest.fn(),
}))

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
    push: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
  }),
}))

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

describe('ProtectedRoute', () => {
  const mockUseSession = useSession as jest.MockedFunction<typeof useSession>
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

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders children for authenticated sessions', () => {
    const session: Session = {
      user: baseUser,
      expires: new Date(Date.now() + 3600_000).toISOString(),
    }
    mockUseSession.mockReturnValue(buildSessionValue(session, 'authenticated'))

    render(
      <ProtectedRoute>
        <div>Protected content</div>
      </ProtectedRoute>,
    )

    expect(screen.getByText('Protected content')).toBeInTheDocument()
    expect(mockReplace).not.toHaveBeenCalled()
  })

  it('redirects when unauthenticated', async () => {
    mockUseSession.mockReturnValue(buildSessionValue(null, 'unauthenticated'))

    render(
      <ProtectedRoute>
        <div>Protected content</div>
      </ProtectedRoute>,
    )

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/auth/login?error=SessionExpired')
    })
  })

  it('redirects when session is expired', async () => {
    const expiredSession: Session = {
      user: {
        ...baseUser,
        expires_at: Date.now() - 1000,
      },
      expires: new Date(Date.now() - 1000).toISOString(),
    }
    mockUseSession.mockReturnValue(buildSessionValue(expiredSession, 'authenticated'))

    render(
      <ProtectedRoute>
        <div>Protected content</div>
      </ProtectedRoute>,
    )

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/auth/login?error=SessionExpired')
    })
  })
})
