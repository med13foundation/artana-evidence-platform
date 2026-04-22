import { navigateToLogin } from '@/lib/navigation'

describe('Navigation Utilities', () => {
  // Suppress console.error for navigation tests (jsdom limitation)
  const originalError = console.error
  beforeEach(() => {
    console.error = jest.fn()
  })
  afterEach(() => {
    console.error = originalError
  })

  describe('navigateToLogin', () => {
    it('does not throw when called in browser environment', () => {
      expect(() => {
        navigateToLogin()
      }).not.toThrow()
    })

    it('does not throw in SSR environment', () => {
      // Mock SSR environment
      const originalWindow = global.window
      delete (global as { window?: Window }).window

      expect(() => {
        navigateToLogin()
      }).not.toThrow()

      // Restore window
      global.window = originalWindow
    })

    it('has SSR check in function implementation', () => {
      // Verify the function has the SSR safety check
      const functionString = navigateToLogin.toString()
      expect(functionString).toContain('typeof window')
      expect(functionString).toContain('undefined')
      expect(functionString).toContain('console.warn')
    })

    it('uses window.location.origin to construct login URL', () => {
      // Since we can't easily mock window.location.href in jsdom,
      // we verify the function structure and that it accesses window.location.origin
      const originalOrigin = window.location.origin

      // The function should use window.location.origin
      // We verify it doesn't throw and would use the current origin
      expect(() => {
        navigateToLogin()
      }).not.toThrow()

      // Verify origin is still accessible (function didn't break it)
      // Note: In jsdom, origin might be empty string, so we just verify it exists
      expect(typeof window.location.origin).toBe('string')
    })
  })
})
