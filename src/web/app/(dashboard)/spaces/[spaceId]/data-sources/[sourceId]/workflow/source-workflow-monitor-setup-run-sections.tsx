import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import { ErrorsAndWarningsCard } from './source-workflow-monitor-run-tab-errors'
import { SummaryRow } from './source-workflow-monitor-primitives'
import { ChecklistItem } from './source-workflow-monitor-section-primitives'
import {
  displayValue,
  type MonitorRow,
} from './source-workflow-monitor-utils'
import { filterWarningRows } from './source-workflow-monitor-warning-rows'

interface SetupTabSectionProps {
  sourceSnapshot: MonitorRow
  schedule: MonitorRow
  selectedRunId?: string
  warnings: string[]
  eventRows: MonitorRow[]
}

export function SetupTabSection({
  sourceSnapshot,
  schedule,
  selectedRunId,
  warnings,
  eventRows,
}: SetupTabSectionProps) {
  const queryValue = String(sourceSnapshot.query ?? '').trim()
  const hasQuery = queryValue.length > 0
  const scheduleEnabled = schedule.enabled === true
  const scheduleRunnable = scheduleEnabled && String(schedule.frequency ?? '') !== 'manual'
  const hasModel = String(sourceSnapshot.model_id ?? '').trim().length > 0
  const oaValue = sourceSnapshot.open_access_only
  const isPubMed = String(sourceSnapshot.source_type ?? '') === 'pubmed'
  const oaReady = !isPubMed || oaValue === true
  const warningRows = filterWarningRows(eventRows)
  const showErrorsAndWarnings =
    Boolean(selectedRunId) || warnings.length > 0 || warningRows.length > 0

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Setup summary</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <SummaryRow label="Source status" value={displayValue(sourceSnapshot.status)} />
          <SummaryRow label="Schedule enabled" value={displayValue(schedule.enabled)} />
          <SummaryRow label="Schedule frequency" value={displayValue(schedule.frequency)} />
          <SummaryRow label="Query" value={displayValue(sourceSnapshot.query)} mono />
          <SummaryRow label="Model" value={displayValue(sourceSnapshot.model_id)} />
          <SummaryRow label="OA only" value={displayValue(sourceSnapshot.open_access_only)} />
          <SummaryRow label="Per-run cap" value={displayValue(sourceSnapshot.max_results)} />
          {selectedRunId && (
            <div className="pt-1 text-xs text-muted-foreground">
              Filtered to run id: <span className="font-mono">{selectedRunId}</span>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Readiness checklist</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <ChecklistItem label="Query configured" isReady={hasQuery} />
          <ChecklistItem label="Runnable schedule configured" isReady={scheduleRunnable} />
          <ChecklistItem label="AI model selected" isReady={hasModel} />
          <ChecklistItem label="PubMed OA policy satisfied" isReady={oaReady} />
        </CardContent>
      </Card>

      {showErrorsAndWarnings && (
        <ErrorsAndWarningsCard eventRows={warningRows} warnings={warnings} />
      )}
    </div>
  )
}
