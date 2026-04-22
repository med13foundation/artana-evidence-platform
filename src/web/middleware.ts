import { withAuth } from "next-auth/middleware"
import type { JWT } from "next-auth/jwt"
import { isPlaywrightE2EMode } from "@/lib/e2e/playwright-auth"

function hasValidTokenExpiry(token: JWT): boolean {
  const now = Date.now()
  if (Number.isFinite(token.expires_at)) {
    return now < token.expires_at
  }
  const exp = token.exp
  if (typeof exp === "number" && Number.isFinite(exp)) {
    return now < exp * 1000
  }
  return false
}

export default withAuth(
  function middleware(req) {
    // Add any additional middleware logic here
  },
  {
    callbacks: {
      authorized: ({ token }) =>
        isPlaywrightE2EMode() || (token ? hasValidTokenExpiry(token) : false),
    },
  }
)

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api/auth (NextAuth.js routes)
     * - _next/* (Next.js internals: static, image, HMR, etc.)
     * - auth/* (login, register, forgot-password pages)
     * - e2e/* (Playwright-only routes)
     * - any file request containing an extension (public assets like .svg, .png, .ico)
     */
    "/((?!api/auth|auth/|_next/|e2e/|.*\\..*).*)",
  ],
}
