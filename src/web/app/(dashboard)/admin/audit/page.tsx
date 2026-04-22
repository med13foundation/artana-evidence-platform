import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'

import { authOptions } from '@/lib/auth'
import { fetchAuditLogs } from '@/lib/api/audit'
import { UserRole } from '@/types/auth'
import type { AuditLogListResponse, AuditLogQueryParams } from '@/types/audit'

import AuditClient from './audit-client'

interface AuditPageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}

function _readSingleParam(
  value: string | string[] | undefined,
): string | undefined {
  if (Array.isArray(value)) {
    return value[0]
  }
  return value
}

function _parseBooleanParam(
  value: string | undefined,
): boolean | undefined {
  if (value === 'true') {
    return true
  }
  if (value === 'false') {
    return false
  }
  return undefined
}

function _parsePositiveInt(
  value: string | undefined,
  fallback: number,
): number {
  if (!value) {
    return fallback
  }
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

export default async function AdminAuditPage({
  searchParams,
}: AuditPageProps) {
  const resolvedSearchParams = await searchParams
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  if (session.user.role !== UserRole.ADMIN) {
    redirect('/dashboard?error=AdminOnly')
  }

  const filters: AuditLogQueryParams = {
    action: _readSingleParam(resolvedSearchParams.action),
    entity_type: _readSingleParam(resolvedSearchParams.entity_type),
    entity_id: _readSingleParam(resolvedSearchParams.entity_id),
    actor_id: _readSingleParam(resolvedSearchParams.actor_id),
    request_id: _readSingleParam(resolvedSearchParams.request_id),
    ip_address: _readSingleParam(resolvedSearchParams.ip_address),
    success: _parseBooleanParam(_readSingleParam(resolvedSearchParams.success)),
    created_after: _readSingleParam(resolvedSearchParams.created_after),
    created_before: _readSingleParam(resolvedSearchParams.created_before),
    page: _parsePositiveInt(_readSingleParam(resolvedSearchParams.page), 1),
    per_page: _parsePositiveInt(_readSingleParam(resolvedSearchParams.per_page), 50),
  }

  let logs: AuditLogListResponse | null = null
  let logsError: string | null = null

  try {
    logs = await fetchAuditLogs(filters, token)
  } catch (error) {
    logsError = error instanceof Error ? error.message : 'Unable to load audit logs.'
    console.error('[AdminAuditPage] Failed to fetch audit logs', error)
  }

  return (
    <AuditClient
      filters={filters}
      logs={logs}
      logsError={logsError}
    />
  )
}
