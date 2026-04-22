import { apiGet, type ApiRequestOptions } from '@/lib/api/client'
import type {
  AuditExportFormat,
  AuditLogListResponse,
  AuditLogQueryParams,
} from '@/types/audit'

const DEFAULT_EXPORT_LIMIT = 10000

function buildAuditQueryParams(
  params: AuditLogQueryParams,
): Record<string, string | number | boolean> {
  const queryParams: Record<string, string | number | boolean> = {
    page: params.page ?? 1,
    per_page: params.per_page ?? 50,
  }

  if (params.action) {
    queryParams.action = params.action
  }
  if (params.entity_type) {
    queryParams.entity_type = params.entity_type
  }
  if (params.entity_id) {
    queryParams.entity_id = params.entity_id
  }
  if (params.actor_id) {
    queryParams.actor_id = params.actor_id
  }
  if (params.request_id) {
    queryParams.request_id = params.request_id
  }
  if (params.ip_address) {
    queryParams.ip_address = params.ip_address
  }
  if (typeof params.success === 'boolean') {
    queryParams.success = params.success
  }
  if (params.created_after) {
    queryParams.created_after = params.created_after
  }
  if (params.created_before) {
    queryParams.created_before = params.created_before
  }

  return queryParams
}

export async function fetchAuditLogs(
  params: AuditLogQueryParams = {},
  token?: string,
): Promise<AuditLogListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchAuditLogs')
  }

  const options: ApiRequestOptions<AuditLogListResponse> = {
    token,
    params: buildAuditQueryParams(params),
  }

  return apiGet<AuditLogListResponse>('/admin/audit/logs', options)
}

export function buildAuditExportQueryString(
  params: AuditLogQueryParams = {},
  exportFormat: AuditExportFormat = 'csv',
  exportLimit: number = DEFAULT_EXPORT_LIMIT,
): string {
  const searchParams = new URLSearchParams()
  const normalized = buildAuditQueryParams(params)
  Object.entries(normalized).forEach(([key, value]) => {
    searchParams.set(key, String(value))
  })
  searchParams.set('export_format', exportFormat)
  searchParams.set('export_limit', String(exportLimit))
  return searchParams.toString()
}
