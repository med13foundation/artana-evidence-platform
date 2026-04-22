import type { AvailableModelsResponse } from '@/types/ai-models'

type ErrorDetailObject = {
  detail?: unknown
}

type IssueObject = {
  msg: string
  loc?: unknown
}

function isIssueObject(value: unknown): value is IssueObject {
  return (
    typeof value === 'object' &&
    value !== null &&
    'msg' in value &&
    typeof (value as IssueObject).msg === 'string'
  )
}

function formatErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return detail
  }
  if (isIssueObject(detail)) {
    const location = Array.isArray(detail.loc) ? detail.loc.join('.') : ''
    return location ? `${location}: ${detail.msg}` : detail.msg
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((issue) => formatErrorDetail(issue))
      .filter((value): value is string => Boolean(value))
    return messages.length > 0 ? messages.join('; ') : null
  }
  return null
}

async function getResponseErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const errorBody = (await response.json()) as ErrorDetailObject
    const formatted = formatErrorDetail(errorBody.detail)
    if (formatted) {
      return formatted
    }
  } catch {
    // Fall back to status-specific messages below.
  }

  if (response.status === 401) {
    return 'Session expired. Please sign in again.'
  }
  if (response.status === 403) {
    return 'You do not have permission to load available models.'
  }

  return fallback
}

export async function fetchAvailableModelsClient(): Promise<AvailableModelsResponse> {
  const response = await fetch('/api/ai-models/available', {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
    cache: 'no-store',
  })

  if (!response.ok) {
    throw new Error(
      await getResponseErrorMessage(response, 'Failed to load available models'),
    )
  }

  return (await response.json()) as AvailableModelsResponse
}
