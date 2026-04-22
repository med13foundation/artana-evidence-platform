"use server"

import { revalidatePath } from 'next/cache'
import {
  cancelSpaceSourcePipelineRun,
  fetchSourceWorkflowEvents,
  fetchSourceWorkflowMonitor,
  runSpaceSourcePipeline,
  runAllActiveSpaceSourcesIngestion,
  runSingleSpaceSourceIngestion,
} from '@/lib/api/kernel'
import type {
  PipelineRunCancelResponse,
  PipelineRunResponse,
  SourceWorkflowMonitorResponse,
  SpaceRunActiveSourcesResponse,
  SpaceSourceIngestionRunResponse,
} from '@/types/kernel'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

export interface WorkflowCardStatusPayload {
  active_pipeline_run_id?: string | null
  last_pipeline_status: string | null
  last_failed_stage: 'ingestion' | 'enrichment' | 'extraction' | 'graph' | null
  pending_paper_count: number
  pending_relation_review_count: number
  extraction_extracted_count: number
  extraction_failed_count: number
  extraction_skipped_count: number
  extraction_timeout_failed_count: number
  graph_edges_delta_last_run: number
  graph_edges_total: number
  artana_progress?: Record<string, WorkflowCardArtanaStage>
}

export interface WorkflowCardArtanaStage {
  run_id: string | null
  status: string | null
  percent: number | null
  current_stage: string | null
}

export interface WorkflowEventCardItem {
  event_id: string
  occurred_at: string | null
  category: string | null
  stage: string | null
  status: string | null
  message: string
}

export interface WorkflowEventListPayload {
  generated_at: string | null
  total: number
  has_more: boolean
  events: WorkflowEventCardItem[]
}

function toNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return 0
}

function revalidateSpaceKernelViews(spaceId: string) {
  revalidatePath(`/spaces/${spaceId}/ingest`)
  revalidatePath(`/spaces/${spaceId}/observations`)
  revalidatePath(`/spaces/${spaceId}/knowledge-graph`)
  revalidatePath(`/spaces/${spaceId}/curation`)
  revalidatePath(`/spaces/${spaceId}/data-sources`)
  revalidatePath(`/spaces/${spaceId}`)
}

const PIPELINE_STAGE_ORDER = [
  'ingestion',
  'enrichment',
  'extraction',
  'graph',
] as const

type PipelineStage = (typeof PIPELINE_STAGE_ORDER)[number]

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function toNullableNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function parseArtanaProgress(
  monitor: SourceWorkflowMonitorResponse,
): Record<string, WorkflowCardArtanaStage> | undefined {
  const progressRoot = asObject(monitor.artana_progress)
  const entries = Object.entries(progressRoot)
  if (entries.length === 0) {
    return undefined
  }

  const parsed: Record<string, WorkflowCardArtanaStage> = {}
  for (const [stageName, rawStage] of entries) {
    const stage = asObject(rawStage)
    parsed[stageName] = {
      run_id: typeof stage.run_id === 'string' ? stage.run_id : null,
      status: typeof stage.status === 'string' ? stage.status : null,
      percent: toNullableNumber(stage.percent),
      current_stage:
        typeof stage.current_stage === 'string' ? stage.current_stage : null,
    }
  }
  return parsed
}

function extractLastFailedStage(monitor: SourceWorkflowMonitorResponse): PipelineStage | null {
  const lastRun = asObject(monitor.last_run)
  const runStatus = typeof lastRun.status === 'string' ? lastRun.status : null
  if (runStatus !== 'failed') {
    return null
  }
  const stageStatuses = asObject(lastRun.stage_statuses)
  for (const stage of PIPELINE_STAGE_ORDER) {
    if (stageStatuses[stage] === 'failed') {
      return stage
    }
  }
  const stageErrors = asObject(lastRun.stage_errors)
  for (const stage of PIPELINE_STAGE_ORDER) {
    if (typeof stageErrors[stage] === 'string' && stageErrors[stage].trim().length > 0) {
      return stage
    }
  }
  return 'ingestion'
}

function resolveActivePipelineRunId(
  monitor: SourceWorkflowMonitorResponse,
): string | null {
  const lastRun = asObject(monitor.last_run)
  const runStatus = typeof lastRun.status === 'string' ? lastRun.status : null
  if (runStatus !== 'queued' && runStatus !== 'retrying' && runStatus !== 'running') {
    return null
  }
  const runId = typeof lastRun.run_id === 'string' ? lastRun.run_id.trim() : ''
  return runId.length > 0 ? runId : null
}

export async function runAllActiveSpaceSourcesIngestionAction(
  spaceId: string,
): Promise<ActionResult<SpaceRunActiveSourcesResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await runAllActiveSpaceSourcesIngestion(spaceId, token)
    revalidateSpaceKernelViews(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] runAllActiveSpaceSourcesIngestion failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to run ingestion for active sources'),
    }
  }
}

export async function runSingleSpaceSourceIngestionAction(
  spaceId: string,
  sourceId: string,
): Promise<ActionResult<SpaceSourceIngestionRunResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await runSingleSpaceSourceIngestion(spaceId, sourceId, token)
    revalidateSpaceKernelViews(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] runSingleSpaceSourceIngestion failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to run ingestion for source'),
    }
  }
}

export async function runSpaceSourcePipelineAction(
  spaceId: string,
  sourceId: string,
  options: {
    resume_from_stage?: 'ingestion' | 'enrichment' | 'extraction' | 'graph' | null
    force_recover_lock?: boolean
    source_type?: string | null
    run_id?: string | null
    model_id?: string | null
    enrichment_limit?: number
    extraction_limit?: number
    graph_max_depth?: number
    smoke_mode?: boolean
  } = {},
): Promise<ActionResult<PipelineRunResponse>> {
  try {
    const token = await requireAccessToken()
    const smokeMode = options.smoke_mode === true
    const payload = {
      source_id: sourceId,
      run_id: options.run_id ?? undefined,
      resume_from_stage: options.resume_from_stage ?? undefined,
      force_recover_lock: options.force_recover_lock === true ? true : undefined,
      source_type: options.source_type ?? undefined,
      model_id: options.model_id ?? undefined,
      enrichment_limit: smokeMode ? 5 : (options.enrichment_limit ?? 25),
      extraction_limit: smokeMode ? 5 : (options.extraction_limit ?? 25),
      graph_max_depth: options.graph_max_depth ?? 2,
    }
    if (process.env.NODE_ENV !== 'test') {
      console.info('[ServerAction] runSpaceSourcePipeline payload', {
        spaceId,
        sourceIdType: typeof sourceId,
        sourceId,
        payload,
      })
    }
    const response = await runSpaceSourcePipeline(
      spaceId,
      payload,
      token,
    )
    revalidateSpaceKernelViews(spaceId)
    revalidatePath(`/spaces/${spaceId}/data-sources/${sourceId}/workflow`)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] runSpaceSourcePipeline failed:', {
        error,
        spaceId,
        sourceId,
      })
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to run full pipeline for source'),
    }
  }
}

export async function cancelSpaceSourcePipelineRunAction(
  spaceId: string,
  sourceId: string,
  runId: string,
): Promise<ActionResult<PipelineRunCancelResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await cancelSpaceSourcePipelineRun(
      spaceId,
      sourceId,
      runId,
      token,
    )
    revalidateSpaceKernelViews(spaceId)
    revalidatePath(`/spaces/${spaceId}/data-sources/${sourceId}/workflow`)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] cancelSpaceSourcePipelineRun failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to cancel pipeline run for source'),
    }
  }
}

export async function fetchSourceWorkflowCardStatusAction(
  spaceId: string,
  sourceId: string,
): Promise<ActionResult<WorkflowCardStatusPayload>> {
  try {
    const token = await requireAccessToken()
    const monitor: SourceWorkflowMonitorResponse = await fetchSourceWorkflowMonitor(
      spaceId,
      sourceId,
      { limit: 5, include_graph: true },
      token,
    )
    const counters = monitor.operational_counters ?? {}
    return {
      success: true,
      data: {
        active_pipeline_run_id: resolveActivePipelineRunId(monitor),
        last_pipeline_status:
          typeof counters.last_pipeline_status === 'string'
            ? counters.last_pipeline_status
            : null,
        last_failed_stage: extractLastFailedStage(monitor),
        pending_paper_count: toNumber(counters.pending_paper_count),
        pending_relation_review_count: toNumber(counters.pending_relation_review_count),
        extraction_extracted_count: toNumber(counters.extraction_extracted_count),
        extraction_failed_count: toNumber(counters.extraction_failed_count),
        extraction_skipped_count: toNumber(counters.extraction_skipped_count),
        extraction_timeout_failed_count: toNumber(
          counters.extraction_timeout_failed_count,
        ),
        graph_edges_delta_last_run: toNumber(counters.graph_edges_delta_last_run),
        graph_edges_total: toNumber(counters.graph_edges_total),
        artana_progress: parseArtanaProgress(monitor),
      },
    }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchSourceWorkflowCardStatus failed:', {
        error,
        spaceId,
        sourceId,
      })
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to fetch source workflow counters'),
    }
  }
}

export async function fetchSourceWorkflowEventsAction(
  spaceId: string,
  sourceId: string,
  options: {
    run_id?: string | null
    since?: string | null
    limit?: number
  } = {},
): Promise<ActionResult<WorkflowEventListPayload>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchSourceWorkflowEvents(
      spaceId,
      sourceId,
      {
        run_id: options.run_id ?? undefined,
        since: options.since ?? undefined,
        limit: options.limit ?? 8,
      },
      token,
    )
    return {
      success: true,
      data: {
        generated_at:
          typeof response.generated_at === 'string' ? response.generated_at : null,
        total: toNumber(response.total),
        has_more: response.has_more === true,
        events: Array.isArray(response.events)
          ? response.events.map((event) => ({
              event_id: event.event_id,
              occurred_at:
                typeof event.occurred_at === 'string' ? event.occurred_at : null,
              category: typeof event.category === 'string' ? event.category : null,
              stage: typeof event.stage === 'string' ? event.stage : null,
              status: typeof event.status === 'string' ? event.status : null,
              message:
                typeof event.message === 'string' && event.message.trim().length > 0
                  ? event.message
                  : 'Workflow event updated.',
            }))
          : [],
      },
    }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchSourceWorkflowEvents failed:', {
        error,
        spaceId,
        sourceId,
      })
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to fetch source workflow events'),
    }
  }
}
