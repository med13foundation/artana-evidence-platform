"use client"

import { useState, useCallback } from 'react'
import { signOut as nextAuthSignOut } from 'next-auth/react'
import { useSpaceContext } from '@/components/space-context-provider'
import { navigateToLogin } from '@/lib/navigation'

interface UseSignOutReturn {
  signOut: () => Promise<void>
  isSigningOut: boolean
}

/**
 * Custom hook for handling user sign-out flow.
 *
 * Features:
 * - Clears space context and localStorage
 * - Handles NextAuth sign-out
 * - Navigates to login page with proper error handling
 * - Provides loading state for UI feedback
 *
 * @returns Object with signOut function and isSigningOut state
 */
export function useSignOut(): UseSignOutReturn {
  const { setCurrentSpaceId } = useSpaceContext()
  const [isSigningOut, setIsSigningOut] = useState(false)

  const signOut = useCallback(async () => {
    setIsSigningOut(true)
    try {
      // Clear local state first
      setCurrentSpaceId(null)
      localStorage.removeItem('currentSpaceId')

      // Sign out without redirect - NextAuth's redirect uses NEXTAUTH_URL which may be wrong
      await nextAuthSignOut({
        redirect: false,
      })

      // Navigate to login page using navigation utility
      navigateToLogin()
    } catch (error: unknown) {
      // Proper error typing with instanceof check
      if (error instanceof Error) {
        console.error('Error signing out:', error.message, error.stack)
      } else {
        console.error('Unknown error during sign out:', error)
      }

      // Fallback: ensure navigation happens even if signOut fails
      navigateToLogin()
    }
    // Note: setIsSigningOut won't execute after navigateToLogin
    // but that's fine since we're navigating away
  }, [setCurrentSpaceId])

  return {
    signOut,
    isSigningOut,
  }
}
