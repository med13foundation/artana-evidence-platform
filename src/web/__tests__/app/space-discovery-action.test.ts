import { fetchSpaceDiscoveryState } from '@/app/actions/space-discovery'

const requireAccessTokenMock = jest.fn()
const authHeadersMock = jest.fn()
const apiClientGetMock = jest.fn()
const revalidatePathMock = jest.fn()

jest.mock('next/cache', () => ({
  revalidatePath: (...args: unknown[]) => revalidatePathMock(...args),
}))

jest.mock('@/app/actions/action-utils', () => ({
  requireAccessToken: () => requireAccessTokenMock(),
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: (...args: unknown[]) => apiClientGetMock(...args),
    post: jest.fn(),
  },
  authHeaders: (...args: unknown[]) => authHeadersMock(...args),
}))

describe('fetchSpaceDiscoveryState', () => {
  const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined)
  const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined)

  beforeEach(() => {
    jest.clearAllMocks()
    requireAccessTokenMock.mockResolvedValue('token-123')
    authHeadersMock.mockReturnValue({
      headers: {
        Authorization: 'Bearer token-123',
      },
    })
  })

  afterAll(() => {
    consoleErrorSpy.mockRestore()
    consoleWarnSpy.mockRestore()
  })

  it('returns a limited-access message without logging a server error for 403 responses', async () => {
    apiClientGetMock.mockRejectedValueOnce({
      response: {
        status: 403,
        data: {
          detail: 'You do not have access to this research space',
        },
      },
      message: 'Request failed with status code 403',
    })

    const result = await fetchSpaceDiscoveryState('space-123')

    expect(result).toEqual({
      success: false,
      error: 'You do not have access to this research space.',
    })
    expect(consoleErrorSpy).not.toHaveBeenCalled()
    expect(consoleWarnSpy).not.toHaveBeenCalled()
  })
})
