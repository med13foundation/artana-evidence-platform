import { UserRole } from '@/types/auth'

const ADMIN_ONLY_PATH_PREFIXES = ['/dashboard', '/system-settings', '/admin']
const ADMIN_DEFAULT_DESTINATION = '/dashboard'
const NON_ADMIN_DEFAULT_DESTINATION = '/spaces'

function isAdminOnlyPath(pathname: string): boolean {
  return ADMIN_ONLY_PATH_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  )
}

function toPathname(path: string): string {
  try {
    return new URL(path, 'http://localhost:3000').pathname
  } catch {
    return path
  }
}

function isHttpProtocol(protocol: string): boolean {
  return protocol === 'http:' || protocol === 'https:'
}

export function getDefaultPostLoginDestination(
  role: UserRole | string | undefined,
): string {
  return role === UserRole.ADMIN
    ? ADMIN_DEFAULT_DESTINATION
    : NON_ADMIN_DEFAULT_DESTINATION
}

export function normalizePostLoginCallbackPath(
  callbackUrl: string | null,
  currentOrigin: string,
): string | null {
  if (!callbackUrl) {
    return null
  }

  const trimmedCallbackUrl = callbackUrl.trim()
  const trimmedOrigin = currentOrigin.trim()

  if (
    trimmedCallbackUrl.length === 0 ||
    trimmedOrigin.length === 0 ||
    trimmedCallbackUrl.startsWith('//')
  ) {
    return null
  }

  try {
    if (trimmedCallbackUrl.startsWith('/')) {
      const parsedUrl = new URL(trimmedCallbackUrl, trimmedOrigin)
      return `${parsedUrl.pathname}${parsedUrl.search}${parsedUrl.hash}`
    }

    const parsedOrigin = new URL(trimmedOrigin)
    const parsedUrl = new URL(trimmedCallbackUrl)

    if (!isHttpProtocol(parsedUrl.protocol) || parsedUrl.origin !== parsedOrigin.origin) {
      return null
    }

    return `${parsedUrl.pathname}${parsedUrl.search}${parsedUrl.hash}`
  } catch {
    return null
  }
}

export function resolvePostLoginDestination(
  callbackUrl: string | null,
  role: UserRole | string | undefined,
  currentOrigin: string,
): string {
  const defaultDestination = getDefaultPostLoginDestination(role)
  const callbackPath = normalizePostLoginCallbackPath(callbackUrl, currentOrigin)

  if (!callbackPath) {
    return defaultDestination
  }

  const isAdmin = role === UserRole.ADMIN
  const callbackPathname = toPathname(callbackPath)

  if (!isAdmin && isAdminOnlyPath(callbackPathname)) {
    return NON_ADMIN_DEFAULT_DESTINATION
  }

  return callbackPath
}
