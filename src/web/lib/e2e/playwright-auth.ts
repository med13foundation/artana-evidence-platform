import type { Session } from 'next-auth'

const PLAYWRIGHT_SESSION_DURATION_MS = 60 * 60 * 1000

export const PLAYWRIGHT_ACCESS_TOKEN = 'playwright-token'
export const PLAYWRIGHT_ADMIN_ID = 'playwright-admin'

export function isPlaywrightE2EMode(): boolean {
  return process.env.E2E_TEST_MODE === 'playwright'
}

export function buildPlaywrightSession(): Session {
  const expiresAt = Date.now() + PLAYWRIGHT_SESSION_DURATION_MS
  return {
    user: {
      id: PLAYWRIGHT_ADMIN_ID,
      role: 'admin',
      email: 'playwright@artana.dev',
      username: 'playwright-admin',
      full_name: 'Playwright Admin',
      email_verified: true,
      name: 'Playwright Admin',
      access_token: PLAYWRIGHT_ACCESS_TOKEN,
      expires_at: expiresAt,
    },
    expires: new Date(expiresAt).toISOString(),
  }
}

export function isSessionExpired(session: Session | null | undefined): boolean {
  const expiresAt = session?.user?.expires_at
  return typeof expiresAt !== 'number' || Date.now() >= expiresAt
}
