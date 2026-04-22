const LOCAL_GRAPH_API_BASE_URL = 'http://localhost:8090'
const ADMIN_HOST_PREFIX = 'artana-admin'
const GRAPH_API_HOST_PREFIX = 'artana-evidence-db'

function isLocalRuntime(): boolean {
  return process.env.NODE_ENV === 'development' || process.env.NODE_ENV === 'test'
}

function isLocalHostname(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]'
}

function isLocalGraphApiUrl(url: string): boolean {
  try {
    return isLocalHostname(new URL(url).hostname)
  } catch {
    return false
  }
}

function inferGraphApiBaseUrlFromHostname(hostname: string): string | null {
  if (!hostname.startsWith(ADMIN_HOST_PREFIX)) {
    return null
  }

  const graphApiHostname = hostname.replace(ADMIN_HOST_PREFIX, GRAPH_API_HOST_PREFIX)
  return `https://${graphApiHostname}`
}

function inferGraphApiBaseUrlFromNextAuthUrl(nextAuthUrl: string): string | null {
  try {
    const nextAuthHostname = new URL(nextAuthUrl).hostname
    return inferGraphApiBaseUrlFromHostname(nextAuthHostname)
  } catch {
    return null
  }
}

export function resolveBrowserGraphApiBaseUrl(
  browserHostname: string,
  configuredGraphApiUrl?: string,
): string | null {
  const normalizedConfiguredGraphApiUrl =
    typeof configuredGraphApiUrl === 'string' ? configuredGraphApiUrl.trim() : ''
  const shouldUseConfiguredGraphApiUrl =
    normalizedConfiguredGraphApiUrl.length > 0 &&
    (!isLocalGraphApiUrl(normalizedConfiguredGraphApiUrl) || isLocalHostname(browserHostname))

  if (shouldUseConfiguredGraphApiUrl) {
    return normalizedConfiguredGraphApiUrl
  }

  const inferredFromBrowserHost = inferGraphApiBaseUrlFromHostname(browserHostname)
  if (inferredFromBrowserHost) {
    return inferredFromBrowserHost
  }

  return normalizedConfiguredGraphApiUrl.length > 0 ? normalizedConfiguredGraphApiUrl : null
}

export function resolveGraphApiBaseUrl(): string {
  const runtimeGraphApiUrl =
    process.env.GRAPH_API_BASE_URL || process.env.INTERNAL_GRAPH_API_URL
  if (typeof runtimeGraphApiUrl === 'string' && runtimeGraphApiUrl.trim().length > 0) {
    return runtimeGraphApiUrl
  }

  const configuredGraphApiUrl = process.env.NEXT_PUBLIC_GRAPH_API_URL
  const normalizedConfiguredGraphApiUrl =
    typeof configuredGraphApiUrl === 'string' ? configuredGraphApiUrl.trim() : ''

  if (typeof window !== 'undefined') {
    const browserGraphApiUrl = resolveBrowserGraphApiBaseUrl(
      window.location.hostname,
      normalizedConfiguredGraphApiUrl,
    )
    if (browserGraphApiUrl) {
      return browserGraphApiUrl
    }
    if (!isLocalRuntime()) {
      throw new Error(
        'NEXT_PUBLIC_GRAPH_API_URL is required outside local development for browser graph calls',
      )
    }
  }

  if (normalizedConfiguredGraphApiUrl.length > 0) {
    return normalizedConfiguredGraphApiUrl
  }

  const nextAuthUrl = process.env.NEXTAUTH_URL
  if (typeof nextAuthUrl === 'string' && nextAuthUrl.trim().length > 0) {
    const inferredFromNextAuth = inferGraphApiBaseUrlFromNextAuthUrl(nextAuthUrl)
    if (inferredFromNextAuth) {
      return inferredFromNextAuth
    }
  }

  if (!isLocalRuntime()) {
    throw new Error(
      'INTERNAL_GRAPH_API_URL or GRAPH_API_BASE_URL is required outside local development',
    )
  }

  return LOCAL_GRAPH_API_BASE_URL
}
