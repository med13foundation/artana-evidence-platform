import type { ReactNode } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import LoginPage from '@/app/auth/login/page'
import { signIn, getSession, useSession } from 'next-auth/react'
import { useSearchParams } from 'next/navigation'
import type { Session } from 'next-auth'
import { UserRole } from '@/types/auth'

const pushMock = jest.fn()
const updateSessionMock = jest.fn()
const navigateToPathWithReloadMock = jest.fn()

jest.mock('next-auth/react', () => ({
  signIn: jest.fn(),
  getSession: jest.fn(),
  useSession: jest.fn(),
}))

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
    replace: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
  }),
  useSearchParams: jest.fn(),
}))

jest.mock('@/lib/navigation', () => ({
  navigateToPathWithReload: (...args: unknown[]) => navigateToPathWithReloadMock(...args),
}))

jest.mock('@/components/auth/AuthShell', () => ({
  AuthShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

jest.mock('@/components/auth/LoginForm', () => ({
  LoginForm: ({
    onSubmit,
    isLoading,
  }: {
    onSubmit: (email: string, password: string) => Promise<void>
    isLoading: boolean
  }) => (
    <button
      type="button"
      disabled={isLoading}
      onClick={() => {
        void onSubmit('user@example.com', 'secret-password')
      }}
    >
      Submit login
    </button>
  ),
}))

function buildAuthenticatedSession(role: UserRole): Session {
  return {
    user: {
      id: 'user-1',
      email: 'user@example.com',
      username: 'user',
      full_name: 'User Name',
      role,
      email_verified: true,
      access_token: 'token-part1.token-part2.token-part3',
      expires_at: Date.now() + 3_600_000,
    },
    expires: new Date(Date.now() + 3_600_000).toISOString(),
  }
}

function createSearchParams(
  value = '',
): ReturnType<typeof useSearchParams> {
  return new URLSearchParams(value) as unknown as ReturnType<typeof useSearchParams>
}

describe('LoginPage', () => {
  const signInMock = jest.mocked(signIn)
  const getSessionMock = jest.mocked(getSession)
  const useSessionMock = jest.mocked(useSession)
  const useSearchParamsMock = jest.mocked(useSearchParams)
  let consoleWarnSpy: jest.SpyInstance

  beforeEach(() => {
    jest.clearAllMocks()
    consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined)

    useSessionMock.mockReturnValue({
      data: null,
      status: 'unauthenticated',
      update: updateSessionMock,
    })
    useSearchParamsMock.mockReturnValue(createSearchParams())
    updateSessionMock.mockResolvedValue(null)
    signInMock.mockResolvedValue({
      error: null,
      ok: true,
      status: 200,
      url: null,
    })
  })

  afterEach(() => {
    consoleWarnSpy.mockRestore()
  })

  it('pushes admins to the dashboard when no callback is provided', async () => {
    getSessionMock.mockResolvedValue(buildAuthenticatedSession(UserRole.ADMIN))

    render(<LoginPage />)
    fireEvent.click(screen.getByRole('button', { name: /submit login/i }))

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/dashboard')
    })

    expect(signInMock).toHaveBeenCalledWith(
      'credentials',
      expect.objectContaining({
        email: 'user@example.com',
        password: 'secret-password',
        redirect: false,
        callbackUrl: '/',
      }),
    )
    expect(navigateToPathWithReloadMock).not.toHaveBeenCalled()
  })

  it('falls back non-admin users to spaces when the callback URL is external', async () => {
    useSearchParamsMock.mockReturnValue(
      createSearchParams('callbackUrl=https%3A%2F%2Fevil.example%2Fphishing'),
    )
    getSessionMock.mockResolvedValue(buildAuthenticatedSession(UserRole.VIEWER))

    render(<LoginPage />)
    fireEvent.click(screen.getByRole('button', { name: /submit login/i }))

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/spaces')
    })

    expect(signInMock).toHaveBeenCalledWith(
      'credentials',
      expect.objectContaining({
        callbackUrl: '/',
      }),
    )
    expect(navigateToPathWithReloadMock).not.toHaveBeenCalled()
  })

  it('uses only safe fallback destinations when the session never becomes ready', async () => {
    useSearchParamsMock.mockReturnValue(
      createSearchParams('callbackUrl=https%3A%2F%2Fevil.example%2Fphishing'),
    )
    getSessionMock.mockResolvedValue(null)

    render(<LoginPage />)
    fireEvent.click(screen.getByRole('button', { name: /submit login/i }))

    await waitFor(
      () => {
        expect(navigateToPathWithReloadMock).toHaveBeenCalledWith('/')
      },
      { timeout: 2_000 },
    )

    expect(navigateToPathWithReloadMock).not.toHaveBeenCalledWith(
      'https://evil.example/phishing',
    )
    expect(pushMock).not.toHaveBeenCalled()
    expect(consoleWarnSpy).toHaveBeenCalled()
  })
})
