import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactNode } from 'react'
import DashboardLayout from '@/app/(dashboard)/layout'
import { fetchMyMembership, fetchResearchSpaces } from '@/lib/api/research-spaces'
import { getServerSession } from 'next-auth'

const redirectMock = jest.fn()

jest.mock('next/navigation', () => ({
  redirect: (...args: unknown[]) => redirectMock(...args),
  usePathname: () => '/dashboard',
}))

jest.mock('@/components/ErrorBoundary', () => ({
  ErrorBoundary: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

jest.mock('@/components/auth/ProtectedRoute', () => ({
  ProtectedRoute: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

jest.mock('@/components/navigation/sidebar/SidebarWrapper', () => ({
  SidebarWrapper: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

jest.mock('@/components/space-context-provider', () => ({
  SpaceContextProvider: ({
    children,
    initialSpaces,
  }: {
    children: ReactNode
    initialSpaces: unknown
  }) => (
    <>
      <div data-testid="initial-space-count">{JSON.stringify(initialSpaces)}</div>
      {children}
    </>
  ),
}))

jest.mock('@/lib/api/research-spaces', () => ({
  fetchResearchSpaces: jest.fn(),
  fetchMyMembership: jest.fn(),
}))

jest.mock('next-auth', () => ({
  getServerSession: jest.fn(),
}))

const getServerSessionMock = jest.mocked(getServerSession)

describe('DashboardLayout', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    getServerSessionMock.mockResolvedValue({
      user: {
        id: 'test-user-id',
        email: 'user@example.com',
        username: 'user',
        full_name: 'User',
        role: 'researcher',
        email_verified: true,
        access_token: 'valid-token',
        expires_at: Date.now() + 3600 * 1000,
      },
    })
  })

  it('redirects to login when research space fetch returns 401', async () => {
    ;(fetchResearchSpaces as jest.Mock).mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 401,
        data: { detail: 'User not found' },
      },
    })
    redirectMock.mockImplementation(() => {
      throw new Error('redirect')
    })

    await expect(DashboardLayout({ children: <main /> })).rejects.toThrow('redirect')
    expect(redirectMock).toHaveBeenCalledWith(
      '/auth/login?error=SessionExpired&message=User%20not%20found',
    )
  })

  it('returns layout content when research spaces request fails for non-auth reasons', async () => {
    ;(fetchResearchSpaces as jest.Mock).mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 500,
        data: { error: 'temporary server issue' },
      },
    })

    const result = await DashboardLayout({ children: <main /> })
    expect(renderToStaticMarkup(result)).toContain('<main>')
    expect(redirectMock).not.toHaveBeenCalled()
  })

  it('loads spaces on success and renders layout', async () => {
    ;(fetchResearchSpaces as jest.Mock).mockResolvedValue({
      spaces: [
        {
          id: 'space-1',
          name: 'Space One',
        },
      ],
      total: 1,
      skip: 0,
      limit: 100,
    })
    ;(fetchMyMembership as jest.Mock).mockResolvedValue(null)

    const result = await DashboardLayout({
      children: <main />,
      params: Promise.resolve({ spaceId: 'space-1' }),
    })

    expect(fetchResearchSpaces).toHaveBeenCalledWith(undefined, 'valid-token')
    expect(redirectMock).not.toHaveBeenCalled()
    expect(renderToStaticMarkup(result)).toContain('Space One')
  })
})
