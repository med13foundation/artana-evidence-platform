import type { JSONValue } from '@/types/generated'

export type AuditExportFormat = 'json' | 'csv'

export interface AuditLogResponse {
  id: number
  action: string
  entity_type: string
  entity_id: string
  user: string | null
  request_id: string | null
  ip_address: string | null
  user_agent: string | null
  success: boolean | null
  details: JSONValue | null
  created_at: string | null
}

export interface AuditLogListResponse {
  logs: AuditLogResponse[]
  total: number
  page: number
  per_page: number
}

export interface AuditLogQueryParams {
  action?: string
  entity_type?: string
  entity_id?: string
  actor_id?: string
  request_id?: string
  ip_address?: string
  success?: boolean
  created_after?: string
  created_before?: string
  page?: number
  per_page?: number
}
