import type {
  OrchestratedSessionState,
  UpdateSelectionRequest,
} from '@/types/generated'

type SpaceDiscoverySelectionResult =
  | { success: true; state: OrchestratedSessionState }
  | { success: false; error: string }

type SpaceDiscoveryAddResult =
  | { success: true; addedCount: number }
  | { success: false; error: string }

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
    // Ignore JSON parsing failures and fall back to the response status.
  }

  if (response.status === 401) {
    return 'Session expired. Please sign in again.'
  }
  if (response.status === 403) {
    return 'You do not have access to this research space.'
  }
  if (response.status === 404) {
    return 'Research space or discovery session not found.'
  }

  return fallback
}

export async function updateSpaceDiscoverySelectionClient(
  spaceId: string,
  sessionId: string,
  sourceIds: string[],
): Promise<SpaceDiscoverySelectionResult> {
  const payload: UpdateSelectionRequest = { source_ids: sourceIds }
  const response = await fetch(
    `/api/research-spaces/${encodeURIComponent(spaceId)}/discovery/sessions/${encodeURIComponent(sessionId)}/selection`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
    },
  )

  if (!response.ok) {
    return {
      success: false,
      error: await getResponseErrorMessage(response, 'Failed to update selection'),
    }
  }

  const state = (await response.json()) as OrchestratedSessionState
  return { success: true, state }
}

export async function addSpaceDiscoverySourcesClient(
  spaceId: string,
  sessionId: string,
  sourceIds: string[],
): Promise<SpaceDiscoveryAddResult> {
  const response = await fetch(
    `/api/research-spaces/${encodeURIComponent(spaceId)}/discovery/sessions/${encodeURIComponent(sessionId)}/add-to-space`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ source_ids: sourceIds }),
    },
  )

  if (!response.ok) {
    return {
      success: false,
      error: await getResponseErrorMessage(response, 'Failed to add sources to this space'),
    }
  }

  const payload = (await response.json()) as { added_count?: number }
  return {
    success: true,
    addedCount: typeof payload.added_count === 'number' ? payload.added_count : sourceIds.length,
  }
}
