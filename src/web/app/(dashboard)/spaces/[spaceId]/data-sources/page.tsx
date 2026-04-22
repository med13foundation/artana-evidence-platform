import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import SpaceDataSourcesClient from '../space-data-sources-client'
import { fetchDataSourcesBySpace } from '@/lib/api/data-sources'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import { fetchSpaceDiscoveryState } from '@/app/actions/space-discovery'
import { fetchSourceWorkflowMonitor } from '@/lib/api/kernel'
import type { SourceWorkflowCardStatus } from '@/components/data-sources/DataSourcesList'
import type { SourceCatalogEntry } from '@/types/generated'

export const dynamic = 'force-dynamic'

interface SpaceDataSourcesPageProps {
  params: Promise<{
    spaceId: string
  }>
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}

function firstParam(value: string | string[] | undefined): string | undefined {
  if (typeof value === 'string') {
    return value
  }
  return Array.isArray(value) ? value[0] : undefined
}

function isValidSpaceId(value: string): boolean {
  const normalized = value.trim()
  return normalized.length > 0 && normalized !== 'undefined' && normalized !== 'null'
}

function normalizeDiscoveryCatalog(value: unknown): SourceCatalogEntry[] {
  return Array.isArray(value) ? value : []
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
  monitor: { artana_progress?: unknown },
): SourceWorkflowCardStatus['artana_progress'] {
  const root = asObject(monitor.artana_progress)
  const entries = Object.entries(root)
  if (entries.length === 0) {
    return undefined
  }
  const parsed: NonNullable<SourceWorkflowCardStatus['artana_progress']> = {}
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

function extractLastFailedStage(monitor: { last_run: unknown }): PipelineStage | null {
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

function resolveActivePipelineRunId(monitor: { last_run: unknown }): string | null {
  const lastRun = asObject(monitor.last_run)
  const runStatus = typeof lastRun.status === 'string' ? lastRun.status : null
  if (runStatus !== 'queued' && runStatus !== 'retrying' && runStatus !== 'running') {
    return null
  }
  const runId = typeof lastRun.run_id === 'string' ? lastRun.run_id.trim() : ''
  return runId.length > 0 ? runId : null
}

export default async function SpaceDataSourcesPage({
  params,
  searchParams,
}: SpaceDataSourcesPageProps) {
  const initialNowMs = Date.now()
  const { spaceId } = await params
  if (!isValidSpaceId(spaceId)) {
    redirect('/spaces/new')
  }
  const resolvedSearchParams = searchParams ? await searchParams : undefined
  const onboardingParam = firstParam(resolvedSearchParams?.onboarding)
  if (onboardingParam === '0') {
    const cleanedParams = new URLSearchParams()
    if (resolvedSearchParams) {
      for (const [key, rawValue] of Object.entries(resolvedSearchParams)) {
        if (key === 'onboarding' || rawValue === undefined) {
          continue
        }
        if (typeof rawValue === 'string') {
          cleanedParams.append(key, rawValue)
        } else {
          for (const value of rawValue) {
            cleanedParams.append(key, value)
          }
        }
      }
    }
    const cleanedQuery = cleanedParams.toString()
    redirect(
      cleanedQuery.length > 0
        ? `/spaces/${spaceId}/data-sources?${cleanedQuery}`
        : `/spaces/${spaceId}/data-sources`,
    )
  }
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let dataSources: DataSourceListResponse | null = null
  let dataSourcesError: string | null = null

  const [dataSourcesResult, discoveryResult] = await Promise.allSettled([
    fetchDataSourcesBySpace(spaceId, {}, token),
    fetchSpaceDiscoveryState(spaceId),
  ])

  if (dataSourcesResult.status === 'fulfilled') {
    dataSources = dataSourcesResult.value
  } else {
    dataSourcesError =
      dataSourcesResult.reason instanceof Error
        ? dataSourcesResult.reason.message
        : 'Unable to load data sources for this space.'
    console.error('[SpaceDataSourcesPage] Failed to fetch data sources', dataSourcesResult.reason)
  }

  const resolvedDiscoveryResult =
    discoveryResult.status === 'fulfilled'
      ? discoveryResult.value
      : ({ success: false, error: 'Unable to load discovery state for this space.' } as const)
  const discoveryState = resolvedDiscoveryResult.success
    ? resolvedDiscoveryResult.data.orchestratedState
    : null
  const discoveryCatalog = resolvedDiscoveryResult.success
    ? normalizeDiscoveryCatalog(resolvedDiscoveryResult.data.catalog)
    : []
  const discoveryError = resolvedDiscoveryResult.success ? null : resolvedDiscoveryResult.error
  const workflowMonitorEnabled = process.env.SPACE_WORKFLOW_MONITOR_ENABLED !== 'false'
  const onboarding = onboardingParam === '1'
  let workflowStatusBySource: Record<string, SourceWorkflowCardStatus> = {}

  if (workflowMonitorEnabled && dataSources?.items && dataSources.items.length > 0) {
    const entries = await Promise.all(
      dataSources.items.map(async (source) => {
        try {
          const monitor = await fetchSourceWorkflowMonitor(
            spaceId,
            source.id,
            { limit: 5, include_graph: false },
            token,
          )
          const counters = monitor.operational_counters ?? {}
          return [
            source.id,
            {
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
            } satisfies SourceWorkflowCardStatus,
          ] as const
        } catch {
          return null
        }
      }),
    )
    const workflowEntries: Array<[string, SourceWorkflowCardStatus]> = []
    for (const entry of entries) {
      if (entry !== null) {
        workflowEntries.push([entry[0], entry[1]])
      }
    }
    workflowStatusBySource = Object.fromEntries(workflowEntries)
  }

  return (
    <SpaceDataSourcesClient
      spaceId={spaceId}
      dataSources={dataSources}
      dataSourcesError={dataSourcesError}
      discoveryState={discoveryState}
      discoveryCatalog={discoveryCatalog}
      discoveryError={discoveryError}
      workflowStatusBySource={workflowStatusBySource}
      workflowMonitorEnabled={workflowMonitorEnabled}
      onboarding={onboarding}
      initialNowMs={initialNowMs}
    />
  )
}
