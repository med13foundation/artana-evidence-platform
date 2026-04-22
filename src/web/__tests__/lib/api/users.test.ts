import type { AxiosError } from 'axios'
import { apiGet, apiPost } from '@/lib/api/client'
import { activateUser, fetchUserStatistics } from '@/lib/api/users'

jest.mock('@/lib/api/client', () => ({
  apiGet: jest.fn(),
  apiPost: jest.fn(),
  apiPut: jest.fn(),
  apiDelete: jest.fn(),
}))

const TOKEN = 'admin-token'

const buildAxiosError = (status: number): AxiosError =>
  ({
    name: 'AxiosError',
    message: 'request failed',
    isAxiosError: true,
    toJSON: () => ({}),
    response: {
      status,
      statusText: 'error',
      headers: {},
      config: {},
      data: {},
    },
  }) as AxiosError

describe('users api', () => {
  const mockApiGet = apiGet as jest.MockedFunction<typeof apiGet>
  const mockApiPost = apiPost as jest.MockedFunction<typeof apiPost>

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('returns empty stats when endpoint responds 500', async () => {
    mockApiGet.mockRejectedValue(buildAxiosError(500))

    await expect(fetchUserStatistics(TOKEN)).resolves.toEqual({
      total_users: 0,
      active_users: 0,
      inactive_users: 0,
      suspended_users: 0,
      pending_verification: 0,
      by_role: {},
      recent_registrations: 0,
      recent_logins: 0,
    })
  })

  it('rethrows non-fallback errors', async () => {
    mockApiGet.mockRejectedValue(buildAxiosError(401))

    await expect(fetchUserStatistics(TOKEN)).rejects.toMatchObject({
      response: { status: 401 },
    })
  })

  it('posts to the admin activation endpoint', async () => {
    mockApiPost.mockResolvedValue({ message: 'ok' })

    await expect(activateUser('user-123', TOKEN)).resolves.toEqual({ message: 'ok' })

    expect(mockApiPost).toHaveBeenCalledWith('/users/user-123/activate', {}, { token: TOKEN })
  })
})
