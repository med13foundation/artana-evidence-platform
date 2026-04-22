import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import { CountCard } from './source-workflow-monitor-section-primitives'
import { SummaryRow, TableCard } from './source-workflow-monitor-primitives'
import type { RunMonitorTabSectionProps } from './source-workflow-monitor-run-tab-types'
import {
  buildStageTimingRows,
  formatCurrency,
  formatDuration,
  formatMeasuredDuration,
  formatPhaseSummaryValue,
  resolveQueueWaitMs,
  toNumber,
} from './source-workflow-monitor-run-tab-utils'
import { asRecord, displayValue, type MonitorRow } from './source-workflow-monitor-utils'

type RunMonitorOverviewProps = Omit<RunMonitorTabSectionProps, 'runRows' | 'warnings'>

export function RunMonitorOverview({
  counters,
  eventRows,
  extractionRows,
  queueRows,
  documentRows,
  lastRun,
}: RunMonitorOverviewProps) {
  const timingSummary = asRecord(lastRun.timing_summary)
  const costSummary = asRecord(lastRun.cost_summary)
  const diagnosticSignals = asRecord(lastRun.diagnostic_signals)
  const stageStatuses = asRecord(lastRun.stage_statuses)
  const stageCosts = asRecord(costSummary.stage_costs_usd)
  const stageTimingRows = buildStageTimingRows(lastRun)
  const completedStageTimingRows = stageTimingRows.filter((row) => toNumber(row.duration_ms) > 0)
  const slowestStageRow =
    completedStageTimingRows.length > 0
      ? completedStageTimingRows.reduce((currentSlowest, row) =>
          toNumber(row.duration_ms) > toNumber(currentSlowest.duration_ms)
            ? row
            : currentSlowest,
        )
      : null
  const fastestStageRow =
    completedStageTimingRows.length > 0
      ? completedStageTimingRows.reduce((currentFastest, row) =>
          toNumber(row.duration_ms) < toNumber(currentFastest.duration_ms)
            ? row
            : currentFastest,
        )
      : null
  const longestGapRow = stageTimingRows.reduce<MonitorRow | null>((currentLongest, row) => {
    const gapMs = row.gap_since_previous_ms
    if (typeof gapMs !== 'number' || gapMs < 0) {
      return currentLongest
    }
    if (currentLongest === null) {
      return row
    }
    return gapMs > toNumber(currentLongest.gap_since_previous_ms) ? row : currentLongest
  }, null)
  const queueWaitMs = resolveQueueWaitMs(lastRun, eventRows)

  return (
    <>
      <div className="grid gap-4 lg:grid-cols-4">
        <CountCard title="Run status" value={displayValue(lastRun.status)} />
        <CountCard title="Total duration" value={formatDuration(timingSummary.total_duration_ms)} />
        <CountCard title="Direct cost" value={formatCurrency(costSummary.total_cost_usd)} />
        <CountCard title="Extracted docs" value={displayValue(counters.extraction_extracted_count)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <SummaryRow label="Run id" value={displayValue(lastRun.run_id)} mono />
            <SummaryRow label="Owner user" value={displayValue(lastRun.run_owner_user_id)} mono />
            <SummaryRow label="Owner source" value={displayValue(lastRun.run_owner_source)} />
            <SummaryRow label="Executed query" value={displayValue(lastRun.executed_query)} mono />
            <SummaryRow label="Ingestion" value={displayValue(stageStatuses.ingestion)} />
            <SummaryRow label="Enrichment" value={displayValue(stageStatuses.enrichment)} />
            <SummaryRow label="Extraction" value={displayValue(stageStatuses.extraction)} />
            <SummaryRow label="Graph" value={displayValue(stageStatuses.graph)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Cost And Diagnostics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <SummaryRow label="Total cost (USD)" value={formatCurrency(costSummary.total_cost_usd)} />
            <SummaryRow label="Ingestion cost" value={formatCurrency(stageCosts.ingestion)} />
            <SummaryRow label="Query generation cost" value={formatCurrency(stageCosts.query_generation)} />
            <SummaryRow label="Enrichment cost" value={formatCurrency(stageCosts.enrichment)} />
            <SummaryRow label="Extraction cost" value={formatCurrency(stageCosts.extraction)} />
            <SummaryRow label="Graph cost" value={formatCurrency(stageCosts.graph)} />
            <SummaryRow label="Extraction failure ratio" value={displayValue(diagnosticSignals.extraction_failure_ratio)} />
            <SummaryRow label="Cost / extracted doc" value={formatCurrency(diagnosticSignals.cost_per_extracted_document)} />
            <SummaryRow label="Cost / relation" value={formatCurrency(diagnosticSignals.cost_per_persisted_relation)} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <CountCard title="Slowest phase" value={formatPhaseSummaryValue(slowestStageRow)} />
        <CountCard title="Fastest phase" value={formatPhaseSummaryValue(fastestStageRow)} />
        <CountCard
          title="Longest handoff gap"
          value={
            longestGapRow === null
              ? '—'
              : `${formatMeasuredDuration(longestGapRow.gap_since_previous_ms)}`
          }
        />
        <CountCard title="Queue wait" value={formatMeasuredDuration(queueWaitMs)} />
      </div>

      <TableCard
        title="Stage Timing"
        rows={stageTimingRows}
        emptyText="No stage timing captured yet."
        limit={8}
        rowKey={(row, index) => `${displayValue(row.stage_key)}-${index}`}
        columns={[
          { header: 'Stage', render: (row) => <Badge variant="outline">{displayValue(row.stage_label)}</Badge> },
          { header: 'Status', render: (row) => displayValue(row.status) },
          { header: 'Started', render: (row) => displayValue(row.started_at) },
          { header: 'Completed', render: (row) => displayValue(row.completed_at) },
          { header: 'Duration', render: (row) => formatMeasuredDuration(row.duration_ms) },
          { header: 'Gap From Previous', render: (row) => formatMeasuredDuration(row.gap_since_previous_ms) },
          { header: 'Stage Queue Wait', render: (row) => formatMeasuredDuration(row.queue_wait_ms) },
          { header: 'Timeout Budget', render: (row) => formatMeasuredDuration(row.timeout_budget_ms) },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-4">
        <CountCard title="Documents" value={String(documentRows.length)} />
        <CountCard title="Queue rows" value={String(queueRows.length)} />
        <CountCard title="Extraction rows" value={String(extractionRows.length)} />
        <CountCard title="Timeline events" value={String(eventRows.length)} />
      </div>
    </>
  )
}
