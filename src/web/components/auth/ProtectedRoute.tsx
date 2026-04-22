"use client"

import { useSession } from "next-auth/react"
import { useRouter } from "next/navigation"
import { useEffect, ReactNode } from "react"
import { Loader2 } from "lucide-react"

interface ProtectedRouteProps {
  children: ReactNode
  requiredRole?: string
  fallback?: ReactNode
}

export function ProtectedRoute({
  children,
  requiredRole,
  fallback
}: ProtectedRouteProps) {
  const { data: session, status } = useSession()
  const router = useRouter()
  const expiresAt = session?.user?.expires_at
  const isExpired = typeof expiresAt === "number" && Date.now() >= expiresAt

  useEffect(() => {
    if (status === "loading") return // Still loading

    const sessionExpired =
      typeof session?.user?.expires_at === "number" && Date.now() >= session.user.expires_at

    if (!session || sessionExpired) {
      // Use replace instead of push to prevent back navigation
      router.replace("/auth/login?error=SessionExpired")
      return
    }

    // Check role if required
    if (requiredRole && session.user?.role !== requiredRole) {
      router.replace("/dashboard") // Redirect to dashboard if insufficient permissions
      return
    }
  }, [session, status, router, requiredRole])

  // Show loading spinner while checking authentication
  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="size-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading...</p>
        </div>
      </div>
    )
  }

  // Don't render anything if not authenticated - redirect is happening
  if (!session || isExpired) {
    return fallback || (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="size-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Redirecting to login...</p>
        </div>
      </div>
    )
  }

  // Check role permissions
  if (requiredRole && session.user?.role !== requiredRole) {
    return fallback || (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="size-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Checking permissions...</p>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
