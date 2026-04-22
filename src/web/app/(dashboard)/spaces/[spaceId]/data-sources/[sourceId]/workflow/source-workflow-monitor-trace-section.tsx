import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { ArtanaRunTraceResponse } from '@/types/artana'

import { CountCard } from './source-workflow-monitor-section-primitives'
import { SummaryRow, TableCard } from './source-workflow-monitor-primitives'
import { displayValue, type MonitorRow } from './source-workflow-monitor-utils'

interface TraceTabSectionProps {
  selectedRunId?: string
  trace: ArtanaRunTraceResponse | null
  traceError: string | null
}

function toMonitorRows(rows: unknown[]): MonitorRow[] {
  return rows.map((row) => ({ ...(row as MonitorRow) }))
}

export function TraceTabSection({
  selectedRunId,
  trace,
  traceError,
}: TraceTabSectionProps) {
  if (!selectedRunId) {
    return (
      <Card>
        <CardContent className="py-8 text-sm text-muted-foreground">
          Select a pipeline run to inspect Artana trace detail.
        </CardContent>
      </Card>
    )
  }

  if (traceError) {
    return (
      <Card>
        <CardContent className="py-8 text-sm text-destructive">{traceError}</CardContent>
      </Card>
    )
  }

  if (!trace) {
    return (
      <Card>
        <CardContent className="py-8 text-sm text-muted-foreground">
          No Artana trace detail is available for this run yet.
        </CardContent>
      </Card>
    )
  }

  const eventRows = toMonitorRows(trace.events)
  const summaryRows = toMonitorRows(trace.summaries)
  const linkedRecordRows = toMonitorRows(trace.linked_records)
  const alertRows = toMonitorRows(trace.alerts)

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-4">
        <CountCard title="Status" value={displayValue(trace.status)} />
        <CountCard title="Alerts" value={String(trace.alerts.length)} />
        <CountCard title="Events" value={String(trace.events.length)} />
        <CountCard title="Linked records" value={String(trace.linked_records.length)} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Run health</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <SummaryRow label="Requested run" value={displayValue(trace.requested_run_id)} mono />
          <SummaryRow label="Resolved run" value={displayValue(trace.run_id)} mono />
          <SummaryRow label="Space" value={displayValue(trace.space_id)} mono />
          <SummaryRow label="Current stage" value={displayValue(trace.current_stage)} />
          <SummaryRow label="Progress" value={displayValue(trace.progress_percent)} />
          <SummaryRow
            label="Completed stages"
            value={trace.completed_stages.length > 0 ? trace.completed_stages.join(', ') : '—'}
          />
          <SummaryRow label="Updated" value={displayValue(trace.updated_at)} />
          <SummaryRow label="Failure reason" value={displayValue(trace.failure_reason)} />
          <SummaryRow
            label="Candidate run ids"
            value={trace.candidate_run_ids.length > 0 ? trace.candidate_run_ids.join(', ') : '—'}
            mono
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Alerts</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {trace.alerts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No derived observability alerts.</p>
          ) : (
            alertRows.map((alert, index) => (
              <div
                key={`${displayValue(alert.code)}-${index}`}
                className="rounded border p-3 text-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={alert.severity === 'error' ? 'destructive' : 'outline'}>
                    {displayValue(alert.code)}
                  </Badge>
                  <span className="font-medium">{displayValue(alert.title)}</span>
                </div>
                <p className="mt-2 text-muted-foreground">{displayValue(alert.description)}</p>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <TableCard
        title="Recent Artana events"
        rows={eventRows}
        emptyText="No Artana events recorded."
        rowKey={(row, index) => `${displayValue(row.event_id)}-${index}`}
        limit={50}
        columns={[
          { header: 'Seq', render: (row) => displayValue(row.seq) },
          {
            header: 'Type',
            render: (row) => <Badge variant="outline">{displayValue(row.event_type)}</Badge>,
          },
          { header: 'Step', render: (row) => displayValue(row.step_key) },
          { header: 'Timestamp', render: (row) => displayValue(row.timestamp) },
        ]}
      />

      <TableCard
        title="Summaries"
        rows={summaryRows}
        emptyText="No Artana summaries recorded."
        rowKey={(row, index) => `${displayValue(row.summary_type)}-${index}`}
        columns={[
          {
            header: 'Summary type',
            className: 'font-mono text-xs',
            render: (row) => displayValue(row.summary_type),
          },
          { header: 'Step', render: (row) => displayValue(row.step_key) },
          { header: 'Timestamp', render: (row) => displayValue(row.timestamp) },
          {
            header: 'Payload',
            className: 'max-w-[520px] truncate font-mono text-xs',
            render: (row) => displayValue(row.payload),
          },
        ]}
      />

      <TableCard
        title="Linked MED13 records"
        rows={linkedRecordRows}
        emptyText="No linked MED13 records found."
        rowKey={(row, index) => `${displayValue(row.record_id)}-${index}`}
        columns={[
          {
            header: 'Type',
            render: (row) => <Badge variant="outline">{displayValue(row.record_type)}</Badge>,
          },
          {
            header: 'Record ID',
            className: 'font-mono text-xs',
            render: (row) => displayValue(row.record_id),
          },
          { header: 'Label', render: (row) => displayValue(row.label) },
          { header: 'Status', render: (row) => displayValue(row.status) },
          { header: 'Source type', render: (row) => displayValue(row.source_type) },
        ]}
      />
    </div>
  )
}
