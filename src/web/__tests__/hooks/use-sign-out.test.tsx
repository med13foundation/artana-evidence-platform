import { renderHook, act } from '@testing-library/react'
import { useSignOut } from '@/hooks/use-sign-out'
import { signOut as nextAuthSignOut } from 'next-auth/react'
import { useSpaceContext } from '@/components/space-context-provider'
import { navigateToLogin } from '@/lib/navigation'

// Mock dependencies
jest.mock('next-auth/react', () => ({
  signOut: jest.fn(),
}))

jest.mock('@/components/space-context-provider', () => ({
  useSpaceContext: jest.fn(),
}))

jest.mock('@/lib/navigation', () => ({
  navigateToLogin: jest.fn(),
}))

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}

  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value.toString()
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      store = {}
    },
  }
})()

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
})

describe('useSignOut', () => {
  const mockSetCurrentSpaceId = jest.fn()
  const mockNextAuthSignOut = nextAuthSignOut as jest.MockedFunction<typeof nextAuthSignOut>
  const mockNavigateToLogin = navigateToLogin as jest.MockedFunction<typeof navigateToLogin>

  beforeEach(() => {
    jest.clearAllMocks()
    localStorageMock.clear()

    ;(useSpaceContext as jest.MockedFunction<typeof useSpaceContext>).mockReturnValue({
      currentSpaceId: 'test-space-id',
      setCurrentSpaceId: mockSetCurrentSpaceId,
      isLoading: false,
      spaces: [],
      spaceTotal: 0,
    })

    mockNextAuthSignOut.mockResolvedValue(undefined)
    mockNavigateToLogin.mockImplementation(() => {})
  })

  it('returns correct initial state', () => {
    const { result } = renderHook(() => useSignOut())

    expect(result.current.isSigningOut).toBe(false)
    expect(typeof result.current.signOut).toBe('function')
  })

  it('sets isSigningOut to true during sign-out', async () => {
    const { result } = renderHook(() => useSignOut())

    act(() => {
      result.current.signOut()
    })

    expect(result.current.isSigningOut).toBe(true)
  })

  it('clears space context on sign-out', async () => {
    localStorageMock.setItem('currentSpaceId', 'test-space-id')

    const { result } = renderHook(() => useSignOut())

    await act(async () => {
      await result.current.signOut()
    })

    expect(mockSetCurrentSpaceId).toHaveBeenCalledWith(null)
  })

  it('removes localStorage item on sign-out', async () => {
    localStorageMock.setItem('currentSpaceId', 'test-space-id')

    const { result } = renderHook(() => useSignOut())

    await act(async () => {
      await result.current.signOut()
    })

    expect(localStorageMock.getItem('currentSpaceId')).toBeNull()
  })

  it('calls NextAuth signOut with correct options', async () => {
    const { result } = renderHook(() => useSignOut())

    await act(async () => {
      await result.current.signOut()
    })

    expect(mockNextAuthSignOut).toHaveBeenCalledWith({
      redirect: false,
    })
  })

  it('navigates to login URL on success', async () => {
    const { result } = renderHook(() => useSignOut())

    await act(async () => {
      await result.current.signOut()
    })

    expect(mockNavigateToLogin).toHaveBeenCalled()
  })

  it('handles errors and navigates on failure', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
    const testError = new Error('Sign out failed')
    mockNextAuthSignOut.mockRejectedValue(testError)

    const { result } = renderHook(() => useSignOut())

    await act(async () => {
      await result.current.signOut()
    })

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Error signing out:',
      testError.message,
      testError.stack
    )
    expect(mockNavigateToLogin).toHaveBeenCalled()

    consoleErrorSpy.mockRestore()
  })

  it('handles unknown error types', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
    const unknownError = 'String error'
    mockNextAuthSignOut.mockRejectedValue(unknownError)

    const { result } = renderHook(() => useSignOut())

    await act(async () => {
      await result.current.signOut()
    })

    expect(consoleErrorSpy).toHaveBeenCalledWith('Unknown error during sign out:', unknownError)
    expect(mockNavigateToLogin).toHaveBeenCalled()

    consoleErrorSpy.mockRestore()
  })

  it('properly types error handling with instanceof check', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
    const error = new Error('Test error')
    mockNextAuthSignOut.mockRejectedValue(error)

    const { result } = renderHook(() => useSignOut())

    await act(async () => {
      await result.current.signOut()
    })

    // Verify error was handled as Error instance
    expect(consoleErrorSpy).toHaveBeenCalled()
    const errorCall = consoleErrorSpy.mock.calls.find(call =>
      call[0] === 'Error signing out:'
    )
    expect(errorCall).toBeDefined()
    if (errorCall) {
      expect(errorCall[1]).toBe(error.message)
      expect(errorCall[2]).toBe(error.stack)
    }

    consoleErrorSpy.mockRestore()
  })

  it('clears context and localStorage even if signOut fails', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
    localStorageMock.setItem('currentSpaceId', 'test-space-id')
    mockNextAuthSignOut.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useSignOut())

    await act(async () => {
      await result.current.signOut()
    })

    expect(mockSetCurrentSpaceId).toHaveBeenCalledWith(null)
    expect(localStorageMock.getItem('currentSpaceId')).toBeNull()
    expect(mockNavigateToLogin).toHaveBeenCalled()

    consoleErrorSpy.mockRestore()
  })
})
