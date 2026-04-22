/**
 * Centralized authentication error handling
 *
 * Provides a single point of control for handling 401 errors
 * to prevent multiple simultaneous redirects and improve UX.
 */

let isHandlingAuthError = false

/**
 * Handles authentication errors gracefully
 *
 * Features:
 * - Prevents multiple simultaneous redirects
 * - Uses NextAuth signOut for clean session cleanup
 * - Shows user-friendly toast notifications
 * - Navigates to login with proper error state
 */
export async function handleAuthError(errorMessage?: string): Promise<void> {
  // Prevent multiple simultaneous redirects
  if (isHandlingAuthError) {
    return
  }

  // Only handle in browser environment
  if (typeof window === 'undefined') {
    return
  }

  // Don't redirect if already on auth pages
  if (window.location.pathname.startsWith('/auth')) {
    return
  }

  isHandlingAuthError = true

  try {
    // Show toast notification (dynamically import to avoid SSR issues)
    const { toast } = await import('sonner')
    toast.error('Session expired', {
      description: 'Your session has expired. Please log in again.',
      duration: 3000,
    })

    // Small delay to show toast before redirect
    await new Promise(resolve => setTimeout(resolve, 500))

    // Dynamically import NextAuth to avoid SSR issues
    const { signOut } = await import('next-auth/react')

    // Sign out without redirect (we'll handle navigation ourselves)
    await signOut({
      redirect: false,
    })

    // Navigate to login with error message
    const loginUrl = new URL('/auth/login', window.location.origin)
    loginUrl.searchParams.set('error', 'SessionExpired')
    if (errorMessage) {
      loginUrl.searchParams.set('message', errorMessage)
    }

    window.location.href = loginUrl.toString()
  } catch (error) {
    // Fallback: direct navigation if signOut fails
    console.error('Error during auth error handling:', error)
    const loginUrl = new URL('/auth/login', window.location.origin)
    loginUrl.searchParams.set('error', 'SessionExpired')
    window.location.href = loginUrl.toString()
  } finally {
    // Reset flag after a delay to allow navigation
    setTimeout(() => {
      isHandlingAuthError = false
    }, 1000)
  }
}

/**
 * Resets the auth error handling flag (useful for testing)
 */
export function resetAuthErrorHandler(): void {
  isHandlingAuthError = false
}
