const LOCAL_ARTANA_EVIDENCE_API_BASE_URL = 'http://localhost:8091'
const ADMIN_HOST_PREFIX = 'artana-admin'
const ARTANA_EVIDENCE_API_HOST_PREFIX = 'artana-evidence-api'

function isLocalRuntime(): boolean {
  return process.env.NODE_ENV === 'development' || process.env.NODE_ENV === 'test'
}

function inferArtanaEvidenceApiBaseUrlFromHostname(
  hostname: string,
): string | null {
  if (!hostname.startsWith(ADMIN_HOST_PREFIX)) {
    return null
  }

  const harnessHostname = hostname.replace(
    ADMIN_HOST_PREFIX,
    ARTANA_EVIDENCE_API_HOST_PREFIX,
  )
  return `https://${harnessHostname}`
}

function inferArtanaEvidenceApiBaseUrlFromNextAuthUrl(
  nextAuthUrl: string,
): string | null {
  try {
    return inferArtanaEvidenceApiBaseUrlFromHostname(
      new URL(nextAuthUrl).hostname,
    )
  } catch {
    return null
  }
}

export function resolveArtanaEvidenceApiBaseUrl(): string {
  const runtimeHarnessApiUrl =
    process.env.ARTANA_EVIDENCE_API_BASE_URL ||
    process.env.INTERNAL_ARTANA_EVIDENCE_API_URL
  if (
    typeof runtimeHarnessApiUrl === 'string' &&
    runtimeHarnessApiUrl.trim().length > 0
  ) {
    return runtimeHarnessApiUrl
  }

  const configuredHarnessApiUrl = process.env.NEXT_PUBLIC_ARTANA_EVIDENCE_API_URL
  if (
    typeof configuredHarnessApiUrl === 'string' &&
    configuredHarnessApiUrl.trim().length > 0
  ) {
    return configuredHarnessApiUrl
  }

  const nextAuthUrl = process.env.NEXTAUTH_URL
  if (typeof nextAuthUrl === 'string' && nextAuthUrl.trim().length > 0) {
    const inferredFromNextAuth =
      inferArtanaEvidenceApiBaseUrlFromNextAuthUrl(nextAuthUrl)
    if (inferredFromNextAuth) {
      return inferredFromNextAuth
    }
  }

  if (typeof window !== 'undefined') {
    const inferredFromHostname = inferArtanaEvidenceApiBaseUrlFromHostname(
      window.location.hostname,
    )
    if (inferredFromHostname) {
      return inferredFromHostname
    }
    if (!isLocalRuntime()) {
      throw new Error(
        'NEXT_PUBLIC_ARTANA_EVIDENCE_API_URL is required outside local development for browser harness calls',
      )
    }
  }

  if (!isLocalRuntime()) {
    throw new Error(
      'INTERNAL_ARTANA_EVIDENCE_API_URL or ARTANA_EVIDENCE_API_BASE_URL is required outside local development',
    )
  }

  return LOCAL_ARTANA_EVIDENCE_API_BASE_URL
}
