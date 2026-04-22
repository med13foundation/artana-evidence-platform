const CLOUD_RUN_METADATA_IDENTITY_URL =
  'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity'
const CLOUD_RUN_RUNTIME_ENV_VARS = ['K_SERVICE', 'K_REVISION', 'K_CONFIGURATION'] as const
const REFRESH_BUFFER_MS = 5 * 60 * 1000

interface CachedIdentityToken {
  expiresAt: number
  value: string
}

const identityTokenCache = new Map<string, CachedIdentityToken>()

function isCloudRunRuntime(): boolean {
  if (process.env.ARTANA_DISABLE_CLOUD_RUN_SERVICE_AUTH === '1') {
    return false
  }

  if (process.env.ARTANA_ENABLE_CLOUD_RUN_SERVICE_AUTH === '1') {
    return true
  }

  return CLOUD_RUN_RUNTIME_ENV_VARS.some((envVar) => {
    const value = process.env[envVar]
    return typeof value === 'string' && value.trim().length > 0
  })
}

function isLocalHostname(hostname: string): boolean {
  return (
    hostname === 'localhost' ||
    hostname === '127.0.0.1' ||
    hostname === '[::1]' ||
    hostname.endsWith('.internal')
  )
}

function resolveAudience(target: URL): string {
  const configuredAudience = process.env.ARTANA_CLOUD_RUN_SERVICE_AUTH_AUDIENCE
  if (typeof configuredAudience === 'string' && configuredAudience.trim().length > 0) {
    return configuredAudience.trim()
  }

  return target.origin
}

function decodeTokenExpiry(token: string): number {
  try {
    const [, payload] = token.split('.')
    if (!payload) {
      return Date.now() + REFRESH_BUFFER_MS
    }

    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = `${base64}${'='.repeat((4 - (base64.length % 4)) % 4)}`
    const payloadJson = Buffer.from(padded, 'base64').toString('utf8')
    const parsed = JSON.parse(payloadJson) as { exp?: number | string }
    const expValue = parsed.exp

    if (typeof expValue === 'number' && Number.isFinite(expValue)) {
      return expValue * 1000
    }

    if (typeof expValue === 'string') {
      const parsedExp = Number(expValue)
      if (Number.isFinite(parsedExp)) {
        return parsedExp * 1000
      }
    }
  } catch {
    return Date.now() + REFRESH_BUFFER_MS
  }

  return Date.now() + REFRESH_BUFFER_MS
}

async function fetchIdentityToken(audience: string): Promise<string> {
  const metadataUrl = new URL(CLOUD_RUN_METADATA_IDENTITY_URL)
  metadataUrl.searchParams.set('audience', audience)
  metadataUrl.searchParams.set('format', 'full')

  const response = await fetch(metadataUrl, {
    headers: {
      'Metadata-Flavor': 'Google',
    },
    cache: 'no-store',
  })

  if (!response.ok) {
    throw new Error(
      `Cloud Run identity token request failed with status ${response.status}`,
    )
  }

  const token = (await response.text()).trim()
  if (token.length === 0) {
    throw new Error('Cloud Run identity token request returned an empty token')
  }

  identityTokenCache.set(audience, {
    value: token,
    expiresAt: decodeTokenExpiry(token),
  })

  return token
}

async function getIdentityToken(audience: string): Promise<string> {
  const cached = identityTokenCache.get(audience)
  if (cached && cached.expiresAt - Date.now() > REFRESH_BUFFER_MS) {
    return cached.value
  }

  return fetchIdentityToken(audience)
}

export async function getCloudRunServiceAuthorization(
  target: string | URL,
): Promise<string | null> {
  if (!isCloudRunRuntime()) {
    return null
  }

  const resolvedTarget = target instanceof URL ? target : new URL(target)
  if (resolvedTarget.protocol !== 'https:' || isLocalHostname(resolvedTarget.hostname)) {
    return null
  }

  const audience = resolveAudience(resolvedTarget)
  const token = await getIdentityToken(audience)
  return `Bearer ${token}`
}

export function clearCloudRunServiceAuthCache(): void {
  identityTokenCache.clear()
}
