import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { RunMonitorTabSectionProps } from './source-workflow-monitor-run-tab-types'
import {
  asRecord,
  displayValue,
  type MonitorRow,
} from './source-workflow-monitor-utils'

interface ErrorsAndWarningsCardProps
  extends Pick<RunMonitorTabSectionProps, 'warnings'> {
  eventRows: MonitorRow[]
}

export function ErrorsAndWarningsCard({
  eventRows,
  warnings,
}: ErrorsAndWarningsCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Errors And Warnings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {warnings.length === 0 && eventRows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No warnings or errors recorded for this run.
          </p>
        ) : (
          <div className="space-y-2">
            {warnings.map((warning, index) => (
              <div
                key={`${warning}-${index}`}
                className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
              >
                {warning}
              </div>
            ))}
            {eventRows.slice(0, 10).map((row, index) => (
              <div
                key={`${displayValue(row.event_id)}-${index}`}
                className={getEventCardClassName(row)}
              >
                <div className="font-medium">{displayEventMessage(row)}</div>
                <div className="mt-1 text-xs">
                  {displayValue(row.stage)} ·{' '}
                  {displayEventQualifier(row)} ·{' '}
                  {displayValue(row.occurred_at)}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function getEventCardClassName(row: MonitorRow): string {
  return isErrorRow(row)
    ? 'rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900'
    : 'rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900'
}

function isErrorRow(row: MonitorRow): boolean {
  const level = String(row.level ?? '').toLowerCase()
  const status = String(row.status ?? '').toLowerCase()
  return level === 'error' || status === 'failed'
}

function displayEventMessage(row: MonitorRow): string {
  const eventType = String(row.event_type ?? '').toLowerCase()
  const payload = asRecord(row.payload)
  const fallbackReason = payload.query_generation_fallback_reason

  if (
    eventType === 'query_resolved' &&
    typeof fallbackReason === 'string' &&
    fallbackReason.length > 0
  ) {
    return 'Fell back to base PubMed query configuration.'
  }

  return displayValue(row.message)
}

function displayEventQualifier(row: MonitorRow): string {
  const payload = asRecord(row.payload)
  const fallbackReason = payload.query_generation_fallback_reason

  if (typeof fallbackReason === 'string' && fallbackReason.length > 0) {
    return `fallback: ${fallbackReason}`
  }

  return displayValue(row.error_code ?? row.status)
}
