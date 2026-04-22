export function firstString(value: string | string[] | undefined): string | undefined {
  if (typeof value === 'string') {
    return value
  }
  return Array.isArray(value) ? value[0] : undefined
}

export function parseStringList(value: string | string[] | undefined): string[] {
  if (value === undefined) {
    return []
  }
  const raw = typeof value === 'string' ? [value] : value
  return raw
    .flatMap((entry) => entry.split(','))
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0)
}

export function parseIntParam(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback
  }
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback
}

export function isTimeoutLikeError(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) {
    return false
  }
  const payload = error as Record<string, unknown>
  const code = payload.code
  if (typeof code === 'string' && code === 'ECONNABORTED') {
    return true
  }
  const message = payload.message
  if (typeof message === 'string') {
    return message.toLowerCase().includes('timeout')
  }
  return false
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message
  }
  return 'Unable to load relations for this space.'
}

export function errorStatusCode(error: unknown): number | null {
  if (typeof error !== 'object' || error === null) {
    return null
  }
  if (!('response' in error)) {
    return null
  }
  const response = (error as { response?: { status?: unknown } }).response
  if (!response || typeof response.status !== 'number') {
    return null
  }
  return response.status
}
