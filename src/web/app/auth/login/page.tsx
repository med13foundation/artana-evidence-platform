"use client"

import { useState, useEffect, Suspense } from "react"
import { signIn, useSession, getSession } from "next-auth/react"
import { useRouter, useSearchParams } from "next/navigation"
import Link from "next/link"
import { LoginForm } from "@/components/auth/LoginForm"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { AlertCircle } from "lucide-react"
import { AuthShell } from "@/components/auth/AuthShell"
import { ADMIN_BRAND_NAME } from "@/lib/branding"
import { navigateToPathWithReload } from "@/lib/navigation"
import {
  normalizePostLoginCallbackPath,
  resolvePostLoginDestination,
} from "@/lib/post-login-destination"

function LoginContent() {
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const router = useRouter()
  const searchParams = useSearchParams()
  const { update: updateSession } = useSession()
  const requestedCallbackUrl = searchParams.get("callbackUrl")
  const currentOrigin =
    typeof window === "undefined" ? "" : window.location.origin
  const sanitizedCallbackPath = currentOrigin
    ? normalizePostLoginCallbackPath(requestedCallbackUrl, currentOrigin)
    : null
  const signInCallbackUrl = sanitizedCallbackPath ?? "/"

  useEffect(() => {
    // Check if redirected due to session expiration
    const sessionError = searchParams.get('error')
    const errorMessage = searchParams.get('message')

    if (sessionError === 'SessionExpired') {
      const message = errorMessage
        ? `Your session has expired: ${errorMessage}`
        : 'Your session has expired. Please log in again.'
      setError(message)
    }
  }, [searchParams])

  const handleLogin = async (email: string, password: string) => {
    setIsLoading(true)
    setError(null)

    try {
      // Attempt sign in
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
        callbackUrl: signInCallbackUrl,
      })

      if (result?.error) {
        setError("Invalid email or password")
        setIsLoading(false)
        return
      }

      if (result?.ok) {
        // Force session refresh using NextAuth's update method
        // This ensures the session is immediately available to all components
        await updateSession()

        // Wait for session to be fully established before navigating
        // This prevents race conditions where queries fire before token is available
        let sessionReady = false
        for (let attempt = 0; attempt < 10; attempt++) {
          // Get fresh session to check if token is available
          const session = await getSession()

          if (session?.user?.access_token && typeof session.user.access_token === 'string' && session.user.access_token.length > 0) {
            const destination = resolvePostLoginDestination(
              sanitizedCallbackPath,
              session.user.role,
              currentOrigin,
            )
            sessionReady = true
            router.push(destination)
            break
          }

          // Wait before retrying
          await new Promise((resolve) => setTimeout(resolve, 100))
        }

        if (!sessionReady) {
          // Fallback: session not ready after retries
          // Use full page reload as last resort to ensure session is established
          console.warn('Session not ready after retries, using full page reload')
          navigateToPathWithReload(signInCallbackUrl)
        }

        // Note: setIsLoading(false) is intentionally omitted here
        // because we're navigating away, so the component will unmount
      }
    } catch (error) {
      console.error("Login error:", error)
      setError("An unexpected error occurred")
      setIsLoading(false)
    }
  }

  return (
    <AuthShell
      title={ADMIN_BRAND_NAME}
      description="Sign in to access Research Spaces."
    >
      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertCircle className="size-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <LoginForm onSubmit={handleLogin} isLoading={isLoading} />

      <div className="mt-2 text-center text-sm text-muted-foreground">
        Don&apos;t have an account?{" "}
        <Link href="/auth/register" className="text-primary hover:underline">
          Sign up
        </Link>
      </div>
    </AuthShell>
  )
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <AuthShell
          title={ADMIN_BRAND_NAME}
          description="Sign in to access Research Spaces."
          isLoading
        >
          <div />
        </AuthShell>
      }
    >
      <LoginContent />
    </Suspense>
  )
}
