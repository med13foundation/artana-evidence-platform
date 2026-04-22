import type { MonitorRow } from './source-workflow-monitor-utils'

export interface RunMonitorTabSectionProps {
  lastRun: MonitorRow
  counters: MonitorRow
  runRows: MonitorRow[]
  documentRows: MonitorRow[]
  paperCandidateRows: MonitorRow[]
  queueRows: MonitorRow[]
  extractionRows: MonitorRow[]
  eventRows: MonitorRow[]
  warnings: string[]
}

export interface StageTimingRow extends MonitorRow {
  stage_key: string
  stage_label: string
  status: string
  started_at: unknown
  completed_at: unknown
  duration_ms: number | null
  gap_since_previous_ms: number | null
  queue_wait_ms: number | null
  timeout_budget_ms: number | null
}
