import { apiGet, type ApiRequestOptions } from '@/lib/api/client'
import type {
  ArtanaRunListParams,
  ArtanaRunListResponse,
  ArtanaRunTraceResponse,
} from '@/types/artana'

function buildArtanaRunListParams(
  params: ArtanaRunListParams,
): Record<string, string | number> {
  const queryParams: Record<string, string | number> = {
    page: params.page ?? 1,
    per_page: params.per_page ?? 25,
  }

  if (params.q) {
    queryParams.q = params.q
  }
  if (params.status) {
    queryParams.status = params.status
  }
  if (params.space_id) {
    queryParams.space_id = params.space_id
  }
  if (params.source_type) {
    queryParams.source_type = params.source_type
  }
  if (params.alert_code) {
    queryParams.alert_code = params.alert_code
  }
  if (typeof params.since_hours === 'number') {
    queryParams.since_hours = params.since_hours
  }

  return queryParams
}

export async function fetchSpaceArtanaRunTrace(
  spaceId: string,
  runId: string,
  token?: string,
): Promise<ArtanaRunTraceResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSpaceArtanaRunTrace')
  }
  return apiGet<ArtanaRunTraceResponse>(
    `/research-spaces/${spaceId}/artana-runs/${encodeURIComponent(runId)}`,
    { token },
  )
}

export async function fetchAdminArtanaRuns(
  params: ArtanaRunListParams = {},
  token?: string,
): Promise<ArtanaRunListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchAdminArtanaRuns')
  }
  const options: ApiRequestOptions<ArtanaRunListResponse> = {
    token,
    params: buildArtanaRunListParams(params),
  }
  return apiGet<ArtanaRunListResponse>('/admin/artana/runs', options)
}

export async function fetchAdminArtanaRunTrace(
  runId: string,
  token?: string,
): Promise<ArtanaRunTraceResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchAdminArtanaRunTrace')
  }
  return apiGet<ArtanaRunTraceResponse>(
    `/admin/artana/runs/${encodeURIComponent(runId)}`,
    { token },
  )
}
