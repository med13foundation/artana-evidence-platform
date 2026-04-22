const LOCAL_API_BASE_URL = 'http://localhost:8080'
const ADMIN_HOST_PREFIX = 'artana-admin'
const API_HOST_PREFIX = 'artana-resource-library'

function isLocalHostname(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]'
}

function isLocalApiUrl(url: string): boolean {
  try {
    return isLocalHostname(new URL(url).hostname)
  } catch {
    return false
  }
}

function inferApiBaseUrlFromHostname(hostname: string): string | null {
  if (!hostname.startsWith(ADMIN_HOST_PREFIX)) {
    return null
  }

  const apiHostname = hostname.replace(ADMIN_HOST_PREFIX, API_HOST_PREFIX)
  return `https://${apiHostname}`
}

function inferApiBaseUrlFromNextAuthUrl(nextAuthUrl: string): string | null {
  try {
    const nextAuthHostname = new URL(nextAuthUrl).hostname
    return inferApiBaseUrlFromHostname(nextAuthHostname)
  } catch {
    return null
  }
}

export function resolveBrowserApiBaseUrl(
  browserHostname: string,
  configuredApiUrl?: string,
): string | null {
  const normalizedConfiguredApiUrl =
    typeof configuredApiUrl === 'string' ? configuredApiUrl.trim() : ''
  const shouldUseConfiguredApiUrl =
    normalizedConfiguredApiUrl.length > 0 &&
    (!isLocalApiUrl(normalizedConfiguredApiUrl) || isLocalHostname(browserHostname))
  if (shouldUseConfiguredApiUrl) {
    return normalizedConfiguredApiUrl
  }

  const inferredFromBrowserHost = inferApiBaseUrlFromHostname(browserHostname)
  if (inferredFromBrowserHost) {
    return inferredFromBrowserHost
  }

  return normalizedConfiguredApiUrl.length > 0 ? normalizedConfiguredApiUrl : null
}

export function resolveApiBaseUrl(): string {
  const runtimeApiUrl = process.env.API_BASE_URL || process.env.INTERNAL_API_URL
  if (typeof runtimeApiUrl === 'string' && runtimeApiUrl.trim().length > 0) {
    return runtimeApiUrl
  }

  const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL
  const normalizedConfiguredApiUrl =
    typeof configuredApiUrl === 'string' ? configuredApiUrl.trim() : ''

  if (typeof window !== 'undefined') {
    const browserApiUrl = resolveBrowserApiBaseUrl(
      window.location.hostname,
      normalizedConfiguredApiUrl,
    )
    if (browserApiUrl) {
      return browserApiUrl
    }
  }

  if (normalizedConfiguredApiUrl.length > 0) {
    return normalizedConfiguredApiUrl
  }

  const nextAuthUrl = process.env.NEXTAUTH_URL
  if (typeof nextAuthUrl === 'string' && nextAuthUrl.trim().length > 0) {
    const inferredFromNextAuth = inferApiBaseUrlFromNextAuthUrl(nextAuthUrl)
    if (inferredFromNextAuth) {
      return inferredFromNextAuth
    }
  }

  return LOCAL_API_BASE_URL
}
