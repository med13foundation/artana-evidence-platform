import type {
  SourcePipelineRunsResponse,
  SourceWorkflowMonitorResponse,
} from '@/types/kernel'

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function asNonEmptyString(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined
  }
  const normalized = value.trim()
  return normalized.length > 0 ? normalized : undefined
}

function resolveMonitorRunId(
  monitor: SourceWorkflowMonitorResponse | null,
): string | undefined {
  if (monitor === null) {
    return undefined
  }
  return asNonEmptyString(asRecord(monitor.last_run)?.run_id)
}

function resolvePipelineRunsRunId(
  pipelineRuns: SourcePipelineRunsResponse | null,
): string | undefined {
  if (pipelineRuns === null || pipelineRuns.runs.length === 0) {
    return undefined
  }
  return asNonEmptyString(asRecord(pipelineRuns.runs[0])?.run_id)
}

export function resolveInitialWorkflowRunId(
  requestedRunId: string | undefined,
  monitor: SourceWorkflowMonitorResponse | null,
  pipelineRuns: SourcePipelineRunsResponse | null,
): string | undefined {
  return (
    asNonEmptyString(requestedRunId) ??
    resolveMonitorRunId(monitor) ??
    resolvePipelineRunsRunId(pipelineRuns)
  )
}
