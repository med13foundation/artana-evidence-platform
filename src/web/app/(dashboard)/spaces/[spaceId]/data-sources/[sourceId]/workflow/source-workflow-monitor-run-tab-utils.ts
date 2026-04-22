import { asRecord, displayValue, type MonitorRow } from './source-workflow-monitor-utils'
import type { StageTimingRow } from './source-workflow-monitor-run-tab-types'

const PIPELINE_STAGE_ORDER = ['ingestion', 'enrichment', 'extraction', 'graph'] as const

export function toNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return 0
}

export function formatDuration(value: unknown): string {
  const durationMs = toNumber(value)
  if (durationMs <= 0) {
    return '—'
  }
  if (durationMs < 1000) {
    return `${durationMs} ms`
  }
  const seconds = durationMs / 1000
  if (seconds < 60) {
    return `${seconds.toFixed(1)} s`
  }
  const minutes = Math.floor(seconds / 60)
  const remainderSeconds = Math.round(seconds % 60)
  return `${minutes}m ${remainderSeconds}s`
}

export function formatCurrency(value: unknown): string {
  const numericValue = toNumber(value)
  return `$${numericValue.toFixed(4)}`
}

export function formatMeasuredDuration(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  if (typeof value === 'string' && value.trim().length === 0) {
    return '—'
  }
  const durationMs = toNumber(value)
  if (durationMs < 0) {
    return '—'
  }
  if (durationMs === 0) {
    return '0 ms'
  }
  return formatDuration(durationMs)
}

function parseTimestampMs(value: unknown): number | null {
  if (typeof value !== 'string' || value.trim().length === 0) {
    return null
  }
  const timestampMs = Date.parse(value)
  return Number.isNaN(timestampMs) ? null : timestampMs
}

function formatStageName(stageName: string): string {
  if (stageName.length === 0) {
    return 'Unknown'
  }
  return stageName.charAt(0).toUpperCase() + stageName.slice(1)
}

export function resolveQueueWaitMs(lastRun: MonitorRow, eventRows: MonitorRow[]): number | null {
  const claimEvent = eventRows.find((row) => String(row.event_type ?? '') === 'run_claimed')
  const explicitQueueWaitMs =
    claimEvent !== undefined && claimEvent.queue_wait_ms !== undefined
      ? toNumber(claimEvent.queue_wait_ms)
      : null
  if (explicitQueueWaitMs !== null && explicitQueueWaitMs >= 0) {
    return explicitQueueWaitMs
  }

  const startedAtMs = parseTimestampMs(lastRun.started_at)
  const triggeredAtMs = parseTimestampMs(lastRun.triggered_at)
  const acceptedAtMs = parseTimestampMs(lastRun.accepted_at)
  const baselineMs = triggeredAtMs ?? acceptedAtMs
  if (startedAtMs === null || baselineMs === null) {
    return null
  }
  return Math.max(startedAtMs - baselineMs, 0)
}

export function buildStageTimingRows(lastRun: MonitorRow): StageTimingRow[] {
  const timingSummary = asRecord(lastRun.timing_summary)
  const stageTimings = asRecord(timingSummary.stage_timings)
  const stageStatuses = asRecord(lastRun.stage_statuses)
  const extraStageNames = Object.keys(stageTimings).filter(
    (stageName) =>
      !PIPELINE_STAGE_ORDER.includes(stageName as (typeof PIPELINE_STAGE_ORDER)[number]),
  )
  const orderedStageNames = [...PIPELINE_STAGE_ORDER, ...extraStageNames]

  let previousCompletedAtMs: number | null = null
  return orderedStageNames
    .map((stageName) => {
      const timingPayload = asRecord(stageTimings[stageName])
      const hasTiming = Object.keys(timingPayload).length > 0
      const status = displayValue(timingPayload.status ?? stageStatuses[stageName] ?? null)
      if (!hasTiming && status === '—') {
        return null
      }
      const startedAt = timingPayload.started_at
      const completedAt = timingPayload.completed_at
      const startedAtMs = parseTimestampMs(startedAt)
      const completedAtMs = parseTimestampMs(completedAt)
      const gapSincePreviousMs =
        previousCompletedAtMs !== null && startedAtMs !== null
          ? Math.max(startedAtMs - previousCompletedAtMs, 0)
          : null
      if (completedAtMs !== null) {
        previousCompletedAtMs = completedAtMs
      }
      return {
        stage_key: stageName,
        stage_label: formatStageName(stageName),
        status,
        started_at: startedAt,
        completed_at: completedAt,
        duration_ms:
          timingPayload.duration_ms !== undefined ? toNumber(timingPayload.duration_ms) : null,
        gap_since_previous_ms: gapSincePreviousMs,
        queue_wait_ms:
          timingPayload.queue_wait_ms !== undefined ? toNumber(timingPayload.queue_wait_ms) : null,
        timeout_budget_ms:
          timingPayload.timeout_budget_ms !== undefined
            ? toNumber(timingPayload.timeout_budget_ms)
            : null,
      } satisfies StageTimingRow
    })
    .filter((row): row is StageTimingRow => row !== null)
}

export function formatPhaseSummaryValue(row: StageTimingRow | null): string {
  if (row === null) {
    return '—'
  }
  return `${displayValue(row.stage_label)} · ${formatMeasuredDuration(row.duration_ms)}`
}
