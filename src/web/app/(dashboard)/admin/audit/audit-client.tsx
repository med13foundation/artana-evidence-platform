import { buildAuditExportQueryString } from '@/lib/api/audit'
import type { AuditLogListResponse, AuditLogQueryParams } from '@/types/audit'

import { AuditEventsCard } from './audit-events-card'
import { AuditFiltersCard } from './audit-filters-card'

interface AuditClientProps {
  filters: AuditLogQueryParams
  logs: AuditLogListResponse | null
  logsError?: string | null
}

export default function AuditClient({
  filters,
  logs,
  logsError,
}: AuditClientProps) {
  const pageSize = logs?.per_page ?? filters.per_page ?? 50
  const exportBaseFilters: AuditLogQueryParams = {
    ...filters,
    page: undefined,
    per_page: undefined,
  }
  const exportCsvHref = `/api/admin/audit/export?${buildAuditExportQueryString(
    exportBaseFilters,
    'csv',
  )}`
  const exportJsonHref = `/api/admin/audit/export?${buildAuditExportQueryString(
    exportBaseFilters,
    'json',
  )}`

  return (
    <div className="space-y-6">
      <AuditFiltersCard
        filters={filters}
        exportCsvHref={exportCsvHref}
        exportJsonHref={exportJsonHref}
        pageSize={pageSize}
      />
      <AuditEventsCard filters={filters} logs={logs} logsError={logsError} />
    </div>
  )
}
