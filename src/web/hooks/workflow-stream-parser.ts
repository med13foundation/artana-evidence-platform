import type {
  SourceWorkflowCardStatusPayload,
  SourceWorkflowEvent,
  SourceWorkflowMonitorResponse,
  SourceWorkflowStreamBootstrapPayload,
  SourceWorkflowStreamEventsPayload,
  SourceWorkflowStreamSnapshotPayload,
  SpaceWorkflowBootstrapPayload,
  SpaceWorkflowSourceCardPayload,
  WorkflowEventCardItem,
} from '@/types/kernel'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function asNullableString(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const normalized = value.trim()
  return normalized.length > 0 ? normalized : null
}

function asNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return 0
}

function parseJsonObject(rawData: string): JsonRecord | null {
  try {
    const parsed: unknown = JSON.parse(rawData)
    return isRecord(parsed) ? parsed : null
  } catch {
    return null
  }
}

function asSourceWorkflowEventArray(value: unknown): SourceWorkflowEvent[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is SourceWorkflowEvent => isRecord(item)) as SourceWorkflowEvent[]
}

function asWorkflowEventCardArray(value: unknown): WorkflowEventCardItem[] {
  if (!Array.isArray(value)) {
    return []
  }
  const parsed: WorkflowEventCardItem[] = []
  for (const item of value) {
    if (!isRecord(item)) {
      continue
    }
    parsed.push({
      event_id: asString(item.event_id) ?? 'workflow-event',
      occurred_at: asNullableString(item.occurred_at),
      category: asNullableString(item.category),
      stage: asNullableString(item.stage),
      status: asNullableString(item.status),
      message: asString(item.message) ?? 'Workflow event updated.',
    })
  }
  return parsed
}

function asWorkflowCardStatus(value: unknown): SourceWorkflowCardStatusPayload | null {
  if (!isRecord(value)) {
    return null
  }
  const artanaProgress = isRecord(value.artana_progress)
    ? (value.artana_progress as SourceWorkflowCardStatusPayload['artana_progress'])
    : undefined
  return {
    active_pipeline_run_id: asNullableString(value.active_pipeline_run_id),
    last_pipeline_status: asNullableString(value.last_pipeline_status),
    last_failed_stage:
      asNullableString(value.last_failed_stage) as SourceWorkflowCardStatusPayload['last_failed_stage'],
    pending_paper_count: asNumber(value.pending_paper_count),
    pending_relation_review_count: asNumber(value.pending_relation_review_count),
    extraction_extracted_count: asNumber(value.extraction_extracted_count),
    extraction_failed_count: asNumber(value.extraction_failed_count),
    extraction_skipped_count: asNumber(value.extraction_skipped_count),
    extraction_timeout_failed_count: asNumber(value.extraction_timeout_failed_count),
    graph_edges_delta_last_run: asNumber(value.graph_edges_delta_last_run),
    graph_edges_total: asNumber(value.graph_edges_total),
    artana_progress: artanaProgress,
  }
}

function asMonitorPayload(value: unknown): SourceWorkflowMonitorResponse | null {
  if (!isRecord(value)) {
    return null
  }
  const requiredKeys: Array<keyof SourceWorkflowMonitorResponse> = [
    'source_snapshot',
    'last_run',
    'pipeline_runs',
    'documents',
    'document_status_counts',
    'extraction_queue',
    'extraction_queue_status_counts',
    'publication_extractions',
    'publication_extraction_status_counts',
    'relation_review',
    'graph_summary',
    'operational_counters',
    'warnings',
  ]
  if (requiredKeys.some((key) => !(key in value))) {
    return null
  }
  return value as unknown as SourceWorkflowMonitorResponse
}

export function parseSourceWorkflowBootstrapEvent(
  rawData: string,
): SourceWorkflowStreamBootstrapPayload | null {
  const parsed = parseJsonObject(rawData)
  if (parsed === null) {
    return null
  }
  const monitor = asMonitorPayload(parsed.monitor)
  if (monitor === null) {
    return null
  }
  return {
    monitor,
    events: asSourceWorkflowEventArray(parsed.events),
    generated_at: asString(parsed.generated_at) ?? new Date().toISOString(),
    run_id: asNullableString(parsed.run_id),
  }
}

export function parseSourceWorkflowSnapshotEvent(
  rawData: string,
): SourceWorkflowStreamSnapshotPayload | null {
  const parsed = parseJsonObject(rawData)
  if (parsed === null) {
    return null
  }
  const monitor = asMonitorPayload(parsed.monitor)
  if (monitor === null) {
    return null
  }
  return {
    monitor,
    generated_at: asString(parsed.generated_at) ?? new Date().toISOString(),
    run_id: asNullableString(parsed.run_id),
  }
}

export function parseSourceWorkflowEventsEvent(
  rawData: string,
): SourceWorkflowStreamEventsPayload | null {
  const parsed = parseJsonObject(rawData)
  if (parsed === null) {
    return null
  }
  return {
    events: asSourceWorkflowEventArray(parsed.events),
    generated_at: asString(parsed.generated_at) ?? new Date().toISOString(),
    run_id: asNullableString(parsed.run_id),
  }
}

export function parseSpaceWorkflowBootstrapEvent(
  rawData: string,
): SpaceWorkflowBootstrapPayload | null {
  const parsed = parseJsonObject(rawData)
  if (parsed === null) {
    return null
  }
  const sourcesRaw = parsed.sources
  if (!Array.isArray(sourcesRaw)) {
    return null
  }
  const sources: SpaceWorkflowSourceCardPayload[] = []
  for (const item of sourcesRaw) {
    if (!isRecord(item)) {
      continue
    }
    const workflowStatus = asWorkflowCardStatus(item.workflow_status)
    if (workflowStatus === null) {
      continue
    }
    const sourceId = asString(item.source_id)
    if (sourceId === null) {
      continue
    }
    sources.push({
      source_id: sourceId,
      workflow_status: workflowStatus,
      events: asWorkflowEventCardArray(item.events),
      generated_at: asString(item.generated_at) ?? new Date().toISOString(),
    })
  }
  return {
    sources,
    generated_at: asString(parsed.generated_at) ?? new Date().toISOString(),
  }
}

export function parseSpaceWorkflowSourceCardEvent(
  rawData: string,
): SpaceWorkflowSourceCardPayload | null {
  const parsed = parseJsonObject(rawData)
  if (parsed === null) {
    return null
  }
  const workflowStatus = asWorkflowCardStatus(parsed.workflow_status)
  const sourceId = asString(parsed.source_id)
  if (workflowStatus === null || sourceId === null) {
    return null
  }
  return {
    source_id: sourceId,
    workflow_status: workflowStatus,
    events: asWorkflowEventCardArray(parsed.events),
    generated_at: asString(parsed.generated_at) ?? new Date().toISOString(),
  }
}

export function parseWorkflowStreamErrorEvent(rawData: string): string | null {
  const parsed = parseJsonObject(rawData)
  if (parsed === null) {
    return null
  }
  return asNullableString(parsed.message)
}
