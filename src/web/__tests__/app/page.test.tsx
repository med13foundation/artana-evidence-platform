import HomePage from '@/app/page'
import { getServerSession } from 'next-auth'

const redirectMock = jest.fn()

jest.mock('next/navigation', () => ({
  redirect: (...args: unknown[]) => redirectMock(...args),
}))

jest.mock('next-auth', () => ({
  getServerSession: jest.fn(),
}))

const getServerSessionMock = jest.mocked(getServerSession)

describe('HomePage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    redirectMock.mockImplementation(() => {
      throw new Error('redirect')
    })
  })

  it('redirects to login when no session is found', async () => {
    getServerSessionMock.mockResolvedValue(null)

    await expect(HomePage()).rejects.toThrow('redirect')

    expect(redirectMock).toHaveBeenCalledWith('/auth/login')
  })

  it('redirects to login when the session is expired', async () => {
    getServerSessionMock.mockResolvedValue({
      user: {
        role: 'admin',
        access_token: 'token-part1.token-part2.token-part3',
        expires_at: Date.now() - 1_000,
      },
    })

    await expect(HomePage()).rejects.toThrow('redirect')

    expect(redirectMock).toHaveBeenCalledWith('/auth/login')
  })

  it('redirects admins to the dashboard', async () => {
    getServerSessionMock.mockResolvedValue({
      user: {
        role: 'admin',
        access_token: 'token-part1.token-part2.token-part3',
        expires_at: Date.now() + 3_600_000,
      },
    })

    await expect(HomePage()).rejects.toThrow('redirect')

    expect(redirectMock).toHaveBeenCalledWith('/dashboard')
  })

  it('redirects non-admin users to spaces', async () => {
    getServerSessionMock.mockResolvedValue({
      user: {
        role: 'researcher',
        access_token: 'token-part1.token-part2.token-part3',
        expires_at: Date.now() + 3_600_000,
      },
    })

    await expect(HomePage()).rejects.toThrow('redirect')

    expect(redirectMock).toHaveBeenCalledWith('/spaces')
  })
})
