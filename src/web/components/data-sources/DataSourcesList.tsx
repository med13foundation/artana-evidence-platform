"use client"

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  deleteDataSourceAction,
  updateDataSourceAction,
} from '@/app/actions/data-sources'
import {
  cancelSpaceSourcePipelineRunAction,
  fetchSourceWorkflowEventsAction,
  fetchSourceWorkflowCardStatusAction,
  runSpaceSourcePipelineAction,
} from '@/app/actions/kernel-ingest'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Database,
  Loader2,
  Play,
  Square,
  ChevronDown,
  ChevronsUpDown,
  Info,
  Search,
  MoreVertical,
  Trash2,
  ShieldCheck,
  Settings2,
} from 'lucide-react'
import { DataSourceConfigurationDialog } from './DataSourceConfigurationDialog'
import { DataSourceIngestionDetailsDialog } from './DataSourceIngestionDetailsDialog'
import { DiscoverSourcesDialog } from './DiscoverSourcesDialog'
import { getSourceAgentConfigSnapshot } from './sourceAgentConfig'
import type { OrchestratedSessionState, SourceCatalogEntry } from '@/types/generated'
import type { DataSource } from '@/types/data-source'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import type {
  SpaceWorkflowBootstrapPayload,
  SpaceWorkflowSourceCardPayload,
} from '@/types/kernel'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { cn } from '@/lib/utils'
import { useSpaceWorkflowStream } from '@/hooks/use-space-workflow-stream'
import { mergeSpaceDataSource, removeSpaceDataSource } from '@/lib/query/admin-cache'
import { queryKeys } from '@/lib/query/query-keys'
import { spaceDataSourcesQueryOptions } from '@/lib/query/query-options'

interface DataSourcesListProps {
  spaceId: string
  dataSources: DataSourceListResponse | null
  dataSourcesError?: string | null
  discoveryState: OrchestratedSessionState | null
  discoveryCatalog: SourceCatalogEntry[]
  discoveryError?: string | null
  workflowStatusBySource?: Record<string, SourceWorkflowCardStatus>
  initialNowMs?: number
}

export interface SourceWorkflowCardStatus {
  active_pipeline_run_id?: string | null
  last_pipeline_status: string | null
  last_failed_stage?: 'ingestion' | 'enrichment' | 'extraction' | 'graph' | null
  pending_paper_count: number
  pending_relation_review_count: number
  extraction_extracted_count: number
  extraction_failed_count: number
  extraction_skipped_count: number
  extraction_timeout_failed_count: number
  graph_edges_delta_last_run: number
  graph_edges_total: number
  artana_progress?: Record<string, SourceWorkflowArtanaStage>
}

interface SourceWorkflowArtanaStage {
  run_id: string | null
  status: string | null
  percent: number | null
  current_stage: string | null
}

interface WorkflowSignal {
  pipelineStatus: string | null
  pendingPapers: number
  pendingReview: number
  timeoutFailures: number
  newEdges: number
}

interface WorkflowEventSignal {
  event_id: string
  occurred_at: string | null
  category: string | null
  stage: string | null
  status: string | null
  message: string
}

const WORKFLOW_SSE_ENABLED = process.env.NEXT_PUBLIC_WORKFLOW_SSE_ENABLED !== 'false'

function isActivePipelineStatus(status: string | null | undefined): boolean {
  return status === 'queued' || status === 'retrying' || status === 'running'
}

function buildWorkflowSignal(status: SourceWorkflowCardStatus): WorkflowSignal {
  return {
    pipelineStatus: status.last_pipeline_status,
    pendingPapers: status.pending_paper_count,
    pendingReview: status.pending_relation_review_count,
    timeoutFailures: status.extraction_timeout_failed_count ?? 0,
    newEdges: status.graph_edges_delta_last_run,
  }
}

function resolvePipelineCurrentStage(
  status: SourceWorkflowCardStatus | undefined,
): string | null {
  if (!status?.artana_progress) {
    return null
  }
  const pipelineStage = status.artana_progress.pipeline
  if (!pipelineStage || typeof pipelineStage.current_stage !== 'string') {
    return null
  }
  const normalized = pipelineStage.current_stage.trim().toLowerCase()
  return normalized.length > 0 ? normalized : null
}

function formatPipelineCurrentStageLabel(stage: string): string {
  if (stage === 'ingestion') {
    return 'Starting ingestion'
  }
  if (stage === 'enrichment') {
    return 'Content enrichment'
  }
  if (stage === 'extraction') {
    return 'Knowledge extraction'
  }
  if (stage === 'graph') {
    return 'Graph persistence'
  }
  return `Running ${stage}`
}

function describePipelineStage(status: SourceWorkflowCardStatus | undefined): string {
  if (!status) return 'Connecting to monitor'
  if (status.last_pipeline_status === 'queued') {
    return 'Queued for worker execution'
  }
  if (status.last_pipeline_status === 'retrying') {
    return 'Retrying after system capacity pressure'
  }
  if (status.last_pipeline_status === 'failed') {
    return 'Pipeline failed'
  }
  if (status.last_pipeline_status === 'running') {
    const currentStage = resolvePipelineCurrentStage(status)
    if (currentStage !== null) {
      return formatPipelineCurrentStageLabel(currentStage)
    }
    if (status.pending_paper_count > 0) {
      return 'Document ingestion and extraction'
    }
    if (status.pending_relation_review_count > 0) {
      return 'Relation review queue'
    }
    if (status.graph_edges_delta_last_run > 0) {
      return 'Graph persistence'
    }
    return 'Pipeline startup'
  }
  if (
    status.last_pipeline_status === 'completed' &&
    (status.extraction_timeout_failed_count ?? 0) > 0
  ) {
    return 'Completed with timeout failures'
  }
  if (
    status.last_pipeline_status === 'completed' &&
    (status.extraction_failed_count ?? 0) > 0
  ) {
    return 'Completed with extraction failures'
  }
  if (status.pending_paper_count > 0) {
    return 'Document ingestion and extraction'
  }
  if (status.pending_relation_review_count > 0) {
    return 'Relation review queue'
  }
  if (status.graph_edges_delta_last_run > 0) {
    return 'Graph persistence'
  }
  if (status.last_pipeline_status === 'completed') {
    return 'Completed'
  }
  return 'Waiting for pipeline signal'
}

function describeArtanaStage(status: SourceWorkflowCardStatus | undefined): string | null {
  if (!status?.artana_progress) {
    return null
  }
  const stageOrder = ['extraction', 'enrichment', 'graph', 'pipeline'] as const
  for (const stageName of stageOrder) {
    const stage = status.artana_progress[stageName]
    if (!stage) {
      continue
    }
    if (
      stage.status === 'running' ||
      stage.status === 'queued' ||
      stage.status === 'retrying'
    ) {
      const percentLabel = typeof stage.percent === 'number' ? `${stage.percent}%` : '...'
      if (
        stageName === 'pipeline' &&
        typeof stage.current_stage === 'string' &&
        stage.current_stage.trim().length > 0
      ) {
        return `${stage.current_stage.trim().toLowerCase()} ${percentLabel}`
      }
      return `${stageName} ${percentLabel}`
    }
  }
  for (const stageName of stageOrder) {
    const stage = status.artana_progress[stageName]
    if (!stage) {
      continue
    }
    if (typeof stage.status === 'string' && stage.status.trim().length > 0) {
      const percentLabel = typeof stage.percent === 'number' ? `${stage.percent}%` : 'n/a'
      return `${stageName} ${stage.status} (${percentLabel})`
    }
  }
  return null
}

function describeRecentWorkflowEventPlaceholder(
  status: SourceWorkflowCardStatus | undefined,
): string {
  if (!status) {
    return 'waiting for monitor connection.'
  }
  if (status.last_pipeline_status === 'queued') {
    return 'queued; waiting for worker claim.'
  }
  if (status.last_pipeline_status === 'retrying') {
    return 'retry scheduled; waiting for worker claim.'
  }
  if (status.last_pipeline_status === 'running') {
    const currentStage = resolvePipelineCurrentStage(status)
    if (currentStage !== null) {
      return `${currentStage} is starting; waiting for the first persisted event.`
    }
    return 'run is active; waiting for the first persisted event.'
  }
  return 'waiting for first event.'
}

function describeWorkflowChange(
  previousSignal: WorkflowSignal | undefined,
  nextSignal: WorkflowSignal,
): string | null {
  if (!previousSignal) {
    return 'Connected to monitor.'
  }
  const updates: string[] = []
  if (previousSignal.pipelineStatus !== nextSignal.pipelineStatus) {
    updates.push(
      `status ${previousSignal.pipelineStatus ?? 'unknown'} -> ${nextSignal.pipelineStatus ?? 'unknown'}`,
    )
  }
  if (previousSignal.pendingPapers !== nextSignal.pendingPapers) {
    updates.push(
      `papers ${previousSignal.pendingPapers} -> ${nextSignal.pendingPapers}`,
    )
  }
  if (previousSignal.pendingReview !== nextSignal.pendingReview) {
    updates.push(
      `review ${previousSignal.pendingReview} -> ${nextSignal.pendingReview}`,
    )
  }
  if (previousSignal.timeoutFailures !== nextSignal.timeoutFailures) {
    updates.push(
      `timeouts ${previousSignal.timeoutFailures} -> ${nextSignal.timeoutFailures}`,
    )
  }
  if (previousSignal.newEdges !== nextSignal.newEdges) {
    updates.push(
      `edges ${previousSignal.newEdges} -> ${nextSignal.newEdges}`,
    )
  }
  if (updates.length === 0) {
    return null
  }
  return updates.join(' | ')
}

function shouldPollWorkflowCard(
  status: SourceWorkflowCardStatus | undefined,
  isRunActive: boolean,
): boolean {
  if (isRunActive) {
    return true
  }
  if (!status) {
    return false
  }
  if (isActivePipelineStatus(status.last_pipeline_status)) {
    return true
  }

  // The list page should only live-poll while ingestion/extraction work is still moving.
  // Review backlog can remain nonzero for long periods and would otherwise trigger
  // endless polling on an idle page.
  return (status.pending_paper_count ?? 0) > 0
}

function formatElapsedSeconds(nowMs: number, timestampMs: number | undefined, fallback: string): string {
  if (typeof timestampMs !== 'number') {
    return fallback
  }
  const elapsedSeconds = Math.max(0, Math.floor((nowMs - timestampMs) / 1000))
  return `${elapsedSeconds}s ago`
}

function toTimestampMs(value: string | null | undefined): number | undefined {
  if (typeof value !== 'string' || value.trim().length === 0) {
    return undefined
  }
  const timestamp = Date.parse(value)
  if (Number.isNaN(timestamp)) {
    return undefined
  }
  return timestamp
}

export function DataSourcesList({
  spaceId,
  dataSources,
  dataSourcesError,
  discoveryState,
  discoveryCatalog,
  discoveryError,
  workflowStatusBySource,
  initialNowMs,
}: DataSourcesListProps) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [detailSourceId, setDetailSourceId] = useState<string | null>(null)
  const [isDiscoverDialogOpen, setIsDiscoverDialogOpen] = useState(false)
  const [configurationDialogSource, setConfigurationDialogSource] = useState<DataSource | null>(null)
  const [configurationDialogTab, setConfigurationDialogTab] = useState<'schedule' | 'ai'>('schedule')
  const [configurationDialogActivationIntent, setConfigurationDialogActivationIntent] = useState(false)
  const [togglingSourceId, setTogglingSourceId] = useState<string | null>(null)
  const [deleteSourceId, setDeleteSourceId] = useState<string | null>(null)
  const [isDeletingSource, setIsDeletingSource] = useState(false)
  const [runningPipelineSourceId, setRunningPipelineSourceId] = useState<string | null>(null)
  const [liveWorkflowStatusBySource, setLiveWorkflowStatusBySource] = useState<
    Record<string, SourceWorkflowCardStatus>
  >(workflowStatusBySource ?? {})
  const [liveWorkflowEventsBySource, setLiveWorkflowEventsBySource] = useState<
    Record<string, WorkflowEventSignal[]>
  >({})
  const [expandedSourceIds, setExpandedSourceIds] = useState<Set<string>>(new Set())
  const initialExpandDoneRef = useRef(false)
  const runGenerationBySourceRef = useRef<Record<string, number>>({})
  const detachedRunGenerationBySourceRef = useRef<Record<string, number>>({})
  const activeRunIdBySourceRef = useRef<Record<string, string>>({})
  const lastWorkflowSignalBySourceRef = useRef<Record<string, WorkflowSignal>>({})
  const lastWorkflowRefreshAtBySourceRef = useRef<Record<string, number>>({})
  const lastWorkflowChangeAtBySourceRef = useRef<Record<string, number>>({})
  const lastWorkflowChangeSummaryBySourceRef = useRef<Record<string, string>>({})
  const [liveStatusNowMs, setLiveStatusNowMs] = useState<number>(() => initialNowMs ?? Date.now())
  const dataSourcesQuery = useQuery(
    spaceDataSourcesQueryOptions(spaceId, {}, dataSources ?? undefined),
  )
  const resolvedDataSourceResponse = dataSourcesQuery.data ?? dataSources

  const resolvedDataSources = useMemo(
    () => resolvedDataSourceResponse?.items ?? [],
    [resolvedDataSourceResponse],
  )

  useEffect(() => {
    if (dataSources !== null) {
      queryClient.setQueryData(queryKeys.spaceDataSources(spaceId, {}), dataSources)
    }
  }, [dataSources, queryClient, spaceId])

  const applyStreamCardPayload = useCallback((payload: SpaceWorkflowSourceCardPayload) => {
    const sourceId = payload.source_id
    const status = payload.workflow_status
    const events: WorkflowEventSignal[] = payload.events.map((event) => ({
      event_id: event.event_id,
      occurred_at: event.occurred_at,
      category: event.category,
      stage: event.stage,
      status: event.status,
      message: event.message,
    }))
    const updateAtMs = Date.now()
    const signal = buildWorkflowSignal(status)
    const previousSignal = lastWorkflowSignalBySourceRef.current[sourceId]
    const changeSummary = describeWorkflowChange(previousSignal, signal)
    lastWorkflowRefreshAtBySourceRef.current[sourceId] = updateAtMs
    if (changeSummary !== null) {
      lastWorkflowChangeAtBySourceRef.current[sourceId] = updateAtMs
      lastWorkflowChangeSummaryBySourceRef.current[sourceId] = changeSummary
    } else if (!(sourceId in lastWorkflowChangeAtBySourceRef.current)) {
      lastWorkflowChangeAtBySourceRef.current[sourceId] = updateAtMs
      lastWorkflowChangeSummaryBySourceRef.current[sourceId] =
        'Awaiting first persisted backend event.'
    }
    lastWorkflowSignalBySourceRef.current[sourceId] = signal
    setLiveWorkflowStatusBySource((previous) => ({
      ...previous,
      [sourceId]: status,
    }))
    setLiveWorkflowEventsBySource((previous) => ({
      ...previous,
      [sourceId]: events,
    }))
    if (!isActivePipelineStatus(status.last_pipeline_status)) {
      delete activeRunIdBySourceRef.current[sourceId]
      setRunningPipelineSourceId((current) => (current === sourceId ? null : current))
    }
  }, [])

  const handleStreamBootstrap = useCallback(
    (payload: SpaceWorkflowBootstrapPayload) => {
      for (const row of payload.sources) {
        applyStreamCardPayload(row)
      }
    },
    [applyStreamCardPayload],
  )

  const {
    isFallbackActive: isSseFallbackActive,
  } = useSpaceWorkflowStream({
    spaceId,
    sourceIds: resolvedDataSources.map((source) => source.id),
    enabled: WORKFLOW_SSE_ENABLED,
    onBootstrap: handleStreamBootstrap,
    onSourceCardStatus: applyStreamCardPayload,
  })

  const isPollingFallbackActive = !WORKFLOW_SSE_ENABLED || isSseFallbackActive

  useEffect(() => {
    if (initialExpandDoneRef.current || resolvedDataSources.length === 0) return
    initialExpandDoneRef.current = true
    setExpandedSourceIds(new Set(resolvedDataSources.map((s) => s.id)))
  }, [resolvedDataSources])

  useEffect(() => {
    setLiveWorkflowStatusBySource(workflowStatusBySource ?? {})
  }, [workflowStatusBySource])

  useEffect(() => {
    for (const [sourceId, status] of Object.entries(liveWorkflowStatusBySource)) {
      if (!isActivePipelineStatus(status.last_pipeline_status)) {
        delete activeRunIdBySourceRef.current[sourceId]
        continue
      }
      const activeRunId = status.active_pipeline_run_id
      if (typeof activeRunId === 'string' && activeRunId.trim().length > 0) {
        activeRunIdBySourceRef.current[sourceId] = activeRunId
      }
    }
  }, [liveWorkflowStatusBySource])

  const pollingSourceIds = useMemo(() => {
    const ids: string[] = []
    for (const source of resolvedDataSources) {
      if (source.status !== 'active') {
        continue
      }
      const status = liveWorkflowStatusBySource[source.id]
      const isRunActive =
        runningPipelineSourceId === source.id ||
        isActivePipelineStatus(status?.last_pipeline_status)
      if (shouldPollWorkflowCard(status, isRunActive)) {
        ids.push(source.id)
      }
    }
    return ids
  }, [liveWorkflowStatusBySource, resolvedDataSources, runningPipelineSourceId])
  const pollingSourceIdsKey = useMemo(() => pollingSourceIds.join(','), [pollingSourceIds])

  useEffect(() => {
    if (pollingSourceIds.length === 0 && runningPipelineSourceId === null) {
      return
    }
    const intervalId = window.setInterval(() => {
      setLiveStatusNowMs(Date.now())
    }, 1000)
    return () => {
      window.clearInterval(intervalId)
    }
  }, [pollingSourceIds.length, runningPipelineSourceId])

  useEffect(() => {
    if (!isPollingFallbackActive || pollingSourceIdsKey.length === 0) return
    let isMounted = true
    let isPolling = false
    const sourceIdsToPoll = pollingSourceIdsKey.split(',').filter((value) => value.length > 0)
    const poll = async () => {
      if (isPolling || !isMounted) return
      isPolling = true
      try {
        const results = await Promise.all(
          sourceIdsToPoll.map(async (sourceId) => {
            const [statusResult, eventsResult] = await Promise.all([
              fetchSourceWorkflowCardStatusAction(spaceId, sourceId),
              fetchSourceWorkflowEventsAction(spaceId, sourceId, {
                limit: 6,
              }),
            ])
            return {
              sourceId,
              statusResult,
              eventsResult,
            }
          }),
        )
        if (!isMounted) return

        const polledAtMs = Date.now()
        setLiveWorkflowStatusBySource((previous) => {
          const next = { ...previous }
          for (const item of results) {
            if (item.statusResult.success) {
              const signal = buildWorkflowSignal(item.statusResult.data)
              const previousSignal = lastWorkflowSignalBySourceRef.current[item.sourceId]
              const changeSummary = describeWorkflowChange(previousSignal, signal)
              lastWorkflowRefreshAtBySourceRef.current[item.sourceId] = polledAtMs
              if (changeSummary !== null) {
                lastWorkflowChangeAtBySourceRef.current[item.sourceId] = polledAtMs
                lastWorkflowChangeSummaryBySourceRef.current[item.sourceId] = changeSummary
              } else if (!(item.sourceId in lastWorkflowChangeAtBySourceRef.current)) {
                lastWorkflowChangeAtBySourceRef.current[item.sourceId] = polledAtMs
                lastWorkflowChangeSummaryBySourceRef.current[item.sourceId] =
                  'Awaiting first persisted backend event.'
              }
              lastWorkflowSignalBySourceRef.current[item.sourceId] = signal
              next[item.sourceId] = item.statusResult.data
            }
          }
          return next
        })
        setLiveWorkflowEventsBySource((previous) => {
          const next = { ...previous }
          for (const item of results) {
            if (item.eventsResult.success) {
              next[item.sourceId] = item.eventsResult.data.events
            }
          }
          return next
        })

        const hasBackendRunning = results.some(
          (item) =>
            item.statusResult.success &&
            isActivePipelineStatus(item.statusResult.data.last_pipeline_status),
        )
        if (!hasBackendRunning) {
          setRunningPipelineSourceId((current) => (current === null ? current : null))
        }
      } finally {
        isPolling = false
      }
    }
    void poll()
    const intervalId = window.setInterval(() => {
      void poll()
    }, 4000)
    return () => {
      isMounted = false
      window.clearInterval(intervalId)
    }
  }, [isPollingFallbackActive, pollingSourceIdsKey, spaceId])

  if (dataSourcesError || dataSourcesQuery.isError) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-destructive">
            Failed to load data sources: {dataSourcesError ?? 'Unable to refresh the list.'}
          </p>
        </CardContent>
      </Card>
    )
  }

  const detailSource =
    resolvedDataSources.find((source) => source.id === detailSourceId) ?? null
  const configurationSourceWorkflowStatus =
    configurationDialogSource !== null
      ? liveWorkflowStatusBySource[configurationDialogSource.id]
      : undefined

  const handleToggleSourceStatus = async (source: DataSource) => {
    const shouldActivate = source.status !== 'active'
    if (shouldActivate) {
      toast('Review Schedule and AI config before activation.')
      setConfigurationDialogActivationIntent(true)
      setConfigurationDialogTab('schedule')
      setConfigurationDialogSource(source)
      return
    }
    try {
      setTogglingSourceId(source.id)
      const result = await updateDataSourceAction(
        source.id,
        {
          status: shouldActivate ? 'active' : 'inactive',
        },
        spaceId,
      )
      if (!result.success) {
        toast.error(result.error)
        return
      }
      queryClient.setQueryData(
        queryKeys.spaceDataSources(spaceId, {}),
        (current: DataSourceListResponse | undefined) =>
          current === undefined ? current : mergeSpaceDataSource(current, result.data),
      )
      toast.success(
        shouldActivate
          ? `${source.name} is now active`
          : `${source.name} is now paused`,
      )
      void queryClient.invalidateQueries({ queryKey: queryKeys.spaceDataSources(spaceId, {}) })
    } catch (error) {
      // Error toast is handled by the mutation
    } finally {
      setTogglingSourceId(null)
    }
  }

  const handleDelete = async () => {
    if (!deleteSourceId) return
    try {
      setIsDeletingSource(true)
      const result = await deleteDataSourceAction(deleteSourceId, spaceId)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      queryClient.setQueryData(
        queryKeys.spaceDataSources(spaceId, {}),
        (current: DataSourceListResponse | undefined) =>
          current === undefined ? current : removeSpaceDataSource(current, deleteSourceId),
      )
      setDeleteSourceId(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.spaceDataSources(spaceId, {}) })
    } catch (error) {
      // Error toast is handled by the mutation
    } finally {
      setIsDeletingSource(false)
    }
  }

  const toggleSourceExpansion = (sourceId: string) => {
    setExpandedSourceIds((current) => {
      const next = new Set(current)
      if (next.has(sourceId)) {
        next.delete(sourceId)
      } else {
        next.add(sourceId)
      }
      return next
    })
  }

  const handleStopPipelineRun = async (source: DataSource) => {
    const activeRunId =
      activeRunIdBySourceRef.current[source.id] ??
      liveWorkflowStatusBySource[source.id]?.active_pipeline_run_id ??
      null
    if (!activeRunId) {
      toast.error('No active run id available for cancellation.')
      return
    }
    const currentGeneration = runGenerationBySourceRef.current[source.id] ?? 0
    const cancelResult = await cancelSpaceSourcePipelineRunAction(
      spaceId,
      source.id,
      activeRunId,
    )
    if (!cancelResult.success) {
      toast.error(cancelResult.error)
      return
    }
    if (cancelResult.data.cancelled) {
      toast.success('Pipeline run cancelled.')
    } else {
      toast.message(`Pipeline run status: ${cancelResult.data.status}`)
    }
    if (currentGeneration > 0) {
      detachedRunGenerationBySourceRef.current[source.id] = currentGeneration
    }
    delete activeRunIdBySourceRef.current[source.id]
    setRunningPipelineSourceId((current) => (current === source.id ? null : current))
    router.refresh()
  }

  const formatScheduleLabel = (source: DataSource): string => {
    const schedule = source.ingestion_schedule
    if (!schedule || !schedule.enabled || schedule.frequency === 'manual') {
      return 'Manual'
    }
    if (schedule.frequency === 'cron') {
      return 'Custom'
    }
    return schedule.frequency.charAt(0).toUpperCase() + schedule.frequency.slice(1)
  }

  const formatTimestamp = (value?: string | null) => {
    if (!value) {
      return 'Never'
    }
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString()
  }

  const formatRelativeTime = (value?: string | null, nowMs?: number) => {
    if (!value) {
      return 'Never'
    }
    const target = new Date(value)
    if (Number.isNaN(target.getTime())) {
      return 'Unknown'
    }
    const diffMs = target.getTime() - (nowMs ?? Date.now())
    const absMs = Math.abs(diffMs)
    const units: [number, Intl.RelativeTimeFormatUnit][] = [
      [1000, 'second'],
      [60 * 1000, 'minute'],
      [60 * 60 * 1000, 'hour'],
      [24 * 60 * 60 * 1000, 'day'],
    ]
    const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
    for (let i = units.length - 1; i >= 0; i -= 1) {
      const [unitMs, unit] = units[i]
      if (absMs >= unitMs) {
        const valueInUnit = Math.round(diffMs / unitMs)
        return rtf.format(valueInUnit, unit)
      }
    }
    return 'moments away'
  }

  const normalizeSourceTitle = (name: string): string =>
    name.replace(/\s*\(from data discovery\)\s*$/i, '').trim()

  const readSourceMetadata = (source: DataSource): Record<string, unknown> => {
    const config = source.config
    if (!config || typeof config !== 'object' || Array.isArray(config)) {
      return {}
    }
    const metadata = (config as Record<string, unknown>).metadata
    if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) {
      return {}
    }
    return metadata as Record<string, unknown>
  }

  const readSourceAgentConfig = (source: DataSource): Record<string, unknown> => {
    const metadata = readSourceMetadata(source)
    const agentConfig = metadata.agent_config
    if (!agentConfig || typeof agentConfig !== 'object' || Array.isArray(agentConfig)) {
      return {}
    }
    return agentConfig as Record<string, unknown>
  }

  const parsePubMedSnapshot = (source: DataSource) => {
    const metadata = readSourceMetadata(source)
    const queryValue = metadata.query
    const maxResultsValue = metadata.max_results
    const openAccessOnlyValue = metadata.open_access_only

    return {
      query: typeof queryValue === 'string' ? queryValue : null,
      maxResults:
        typeof maxResultsValue === 'number' && Number.isFinite(maxResultsValue)
          ? Math.max(1, Math.floor(maxResultsValue))
          : null,
      openAccessOnly: openAccessOnlyValue !== false,
    }
  }

  const handleRunFullPipeline = async (source: DataSource, smokeMode: boolean) => {
    const nextGeneration = (runGenerationBySourceRef.current[source.id] ?? 0) + 1
    runGenerationBySourceRef.current[source.id] = nextGeneration
    delete detachedRunGenerationBySourceRef.current[source.id]
    let queuedAccepted = false
    const runId =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    activeRunIdBySourceRef.current[source.id] = runId
    try {
      if (smokeMode && source.source_type === 'pubmed') {
        const metadata = readSourceMetadata(source)
        const query = typeof metadata.query === 'string' ? metadata.query.toLowerCase() : ''
        const requiredTerms = Array.isArray(metadata.required_query_terms)
          ? metadata.required_query_terms.filter(
              (item): item is string => typeof item === 'string' && item.trim().length > 0,
            )
          : []
        const missingRequiredTerm =
          requiredTerms.length > 0 &&
          requiredTerms.some((term) => !query.includes(term.trim().toLowerCase()))
        if (missingRequiredTerm) {
          toast.error(
            'Smoke-mode guard: query is missing one or more required target terms for this source.',
          )
          return
        }
      }
      const runStartMs = Date.now()
      lastWorkflowRefreshAtBySourceRef.current[source.id] = runStartMs
      lastWorkflowChangeAtBySourceRef.current[source.id] = runStartMs
      lastWorkflowChangeSummaryBySourceRef.current[source.id] =
        'Run queued locally. Waiting for worker claim.'
      setLiveWorkflowEventsBySource((previous) => ({
        ...previous,
        [source.id]: [
          {
            event_id: `run-start:${runId}`,
            occurred_at: new Date(runStartMs).toISOString(),
            category: 'run',
            stage: 'ingestion',
            status: 'queued',
            message: 'Run queued. Waiting for worker claim.',
          },
        ],
      }))
      setRunningPipelineSourceId(source.id)
      setLiveWorkflowStatusBySource((previous) => {
        const current = previous[source.id]
        const nextStatus: SourceWorkflowCardStatus = {
          last_pipeline_status: 'queued',
          last_failed_stage: null,
          pending_paper_count: current?.pending_paper_count ?? 0,
          pending_relation_review_count:
            current?.pending_relation_review_count ?? 0,
          extraction_extracted_count: current?.extraction_extracted_count ?? 0,
          extraction_failed_count: current?.extraction_failed_count ?? 0,
          extraction_skipped_count: current?.extraction_skipped_count ?? 0,
          extraction_timeout_failed_count:
            current?.extraction_timeout_failed_count ?? 0,
          graph_edges_delta_last_run:
            current?.graph_edges_delta_last_run ?? 0,
          graph_edges_total: current?.graph_edges_total ?? 0,
        }
        return {
          ...previous,
          [source.id]: nextStatus,
        }
      })
      const agentConfig = readSourceAgentConfig(source)
      const modelId = typeof agentConfig.model_id === 'string' ? agentConfig.model_id : null
      const result = await runSpaceSourcePipelineAction(spaceId, source.id, {
        run_id: runId,
        source_type: source.source_type,
        model_id: modelId,
        smoke_mode: smokeMode,
      })
      if (runGenerationBySourceRef.current[source.id] !== nextGeneration) {
        return
      }
      if (detachedRunGenerationBySourceRef.current[source.id] === nextGeneration) {
        return
      }
      if (!result.success) {
        toast.error(result.error)
        return
      }
      const acceptedRun = result.data
      queuedAccepted = true
      activeRunIdBySourceRef.current[source.id] = acceptedRun.run_id
      toast.success(
        `${smokeMode ? 'Smoke' : 'Full'} pipeline queued for ${source.name}. Run id: ${acceptedRun.run_id}.`,
      )
      router.refresh()
    } catch (error) {
      if (detachedRunGenerationBySourceRef.current[source.id] === nextGeneration) {
        return
      }
      toast.error('Failed to run full pipeline')
    } finally {
      if (runGenerationBySourceRef.current[source.id] === nextGeneration) {
        if (!queuedAccepted) {
          setRunningPipelineSourceId((current) => (current === source.id ? null : current))
          delete activeRunIdBySourceRef.current[source.id]
        }
        router.refresh()
      }
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            {resolvedDataSourceResponse?.total || 0} data source{resolvedDataSourceResponse?.total !== 1 ? 's' : ''} in this space
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setIsDiscoverDialogOpen(true)}>
            <Search className="mr-2 size-4" />
            Add from Library
          </Button>
        </div>
      </div>

      {resolvedDataSources.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="py-12 text-center">
              <Database className="mx-auto mb-4 size-12 text-muted-foreground" />
              <h3 className="mb-2 text-lg font-semibold">No data sources added to this space yet</h3>
              <p className="mb-4 text-muted-foreground">
                Use the library to add PubMed or create a custom source from the same menu.
              </p>
              <div className="flex justify-center gap-3">
                <Button onClick={() => setIsDiscoverDialogOpen(true)}>
                  <Search className="mr-2 size-4" />
                  Add from Library
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {resolvedDataSources.map((source: DataSource) => {
            const agentConfig = getSourceAgentConfigSnapshot(source)
            const showsAiControls = agentConfig.supportsAiControls
            const isPubMedSource = source.source_type === 'pubmed'
            const pubMedSnapshot = isPubMedSource ? parsePubMedSnapshot(source) : null
            const workflowStatus = liveWorkflowStatusBySource[source.id]
            const artanaStageLabel = describeArtanaStage(workflowStatus)
            const displayTitle = normalizeSourceTitle(source.name)
            const description = isPubMedSource
              ? 'Biomedical literature database (NLM)'
              : source.description || 'No description'
            const lastExecutionAt =
              source.ingestion_schedule?.last_run_at ?? source.last_ingested_at ?? null
            const executionStatusLine = lastExecutionAt
              ? `Last execution: ${formatTimestamp(lastExecutionAt)}`
              : null
            const schedule = source.ingestion_schedule
            const hasRunnableSchedule =
              schedule?.enabled === true && String(schedule.frequency) !== 'manual'
            const nextRunRelative =
              hasRunnableSchedule && schedule?.next_run_at
                ? formatRelativeTime(schedule.next_run_at, liveStatusNowMs)
                : null
            const countTelemetryMetrics: Array<{
              label: string
              value: string
              tooltip?: string
            }> = [
              {
                label: 'Pending papers',
                value: String(workflowStatus?.pending_paper_count ?? 0),
              },
              {
                label: 'Pending review',
                value: String(workflowStatus?.pending_relation_review_count ?? 0),
              },
              {
                label: 'Failed papers',
                value: String(workflowStatus?.extraction_failed_count ?? 0),
              },
              {
                label: 'Timeouts',
                value: String(workflowStatus?.extraction_timeout_failed_count ?? 0),
              },
              {
                label: 'New edges',
                value: String(workflowStatus?.graph_edges_delta_last_run ?? 0),
                tooltip: 'Edges added in the latest pipeline run.',
              },
            ]
            const liveStageLabel = describePipelineStage(workflowStatus)
            const lastSignalLabel = formatElapsedSeconds(
              liveStatusNowMs,
              lastWorkflowChangeAtBySourceRef.current[source.id],
              'waiting',
            )
            const lastPollLabel = formatElapsedSeconds(
              liveStatusNowMs,
              lastWorkflowRefreshAtBySourceRef.current[source.id],
              'connecting',
            )
            const lastSignalSummary =
              lastWorkflowChangeSummaryBySourceRef.current[source.id] ??
              'Awaiting first persisted backend event.'
            const workflowEventSignals = liveWorkflowEventsBySource[source.id] ?? []
            const recentWorkflowEventSignals = workflowEventSignals.slice(0, 3)
            const lastRunMetric = formatRelativeTime(lastExecutionAt, liveStatusNowMs)
            const isActive = source.status === 'active'
            const isArchived = source.status === 'archived'
            const backendRunning = isActivePipelineStatus(
              workflowStatus?.last_pipeline_status,
            )
            const isRunning = runningPipelineSourceId === source.id || backendRunning
            const showNextRunBadge = isActive && Boolean(nextRunRelative)
            const isExpanded = expandedSourceIds.has(source.id)
            const showLifecycleToggle = !isActive && !isArchived
            const lifecycleLabel = 'Activate'
            const lifecycleBadge = isArchived
              ? 'retired'
              : source.status === 'draft'
                ? 'draft'
                : isActive
                  ? 'active'
                  : 'disabled'
            const showOverflowMenu = true
            const inactiveMessage = isArchived
              ? 'Source is retired. Read-only mode.'
              : 'Source is inactive. Activate and complete configuration before execution.'
            const compactNextRunValue = showNextRunBadge
              ? `Next ${nextRunRelative}`
              : isActive
                ? 'Manual'
                : 'Paused'

            return (
              <Card
                key={source.id}
                className={cn('transition-opacity', !isActive && !isArchived && 'opacity-80')}
              >
                <CardHeader className="space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <TooltipProvider delayDuration={120}>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                type="button"
                                size="icon"
                                variant="ghost"
                                className="size-7 shrink-0 text-muted-foreground"
                                aria-label={isExpanded ? `Collapse ${source.name}` : `Expand ${source.name}`}
                                title={isExpanded ? 'Collapse details' : 'Expand details'}
                                disabled={isRunning}
                                onClick={() => toggleSourceExpansion(source.id)}
                              >
                                <ChevronsUpDown className="size-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>
                              {isExpanded ? 'Collapse details' : 'Expand details'}
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                        <CardTitle className="truncate text-lg">{displayTitle}</CardTitle>
                        <Badge variant="outline" className="h-5 px-2 text-xs">
                          {lifecycleBadge}
                        </Badge>
                        {!isRunning && workflowStatus?.last_pipeline_status === 'failed' && (
                          <Badge variant="destructive" className="h-5 px-2 text-xs">
                            Pipeline failed
                          </Badge>
                        )}
                        {isRunning && (
                          <Badge variant="secondary" className="h-5 px-2 text-xs">
                            <Loader2 className="mr-1 size-3 animate-spin" />
                            Running
                          </Badge>
                        )}
                        {artanaStageLabel && (
                          <Badge variant="outline" className="h-5 px-2 text-xs">
                            Artana {artanaStageLabel}
                          </Badge>
                        )}
                      </div>
                      <CardDescription className="mt-1 text-sm text-muted-foreground">
                        {description}
                      </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                      {!isExpanded && (
                        <div className="hidden items-center gap-3 whitespace-nowrap pr-1 text-xs md:flex">
                          {isRunning && (
                            <span className="inline-flex items-center gap-1 text-primary">
                              <Loader2 className="size-3 animate-spin" />
                              Live
                            </span>
                          )}
                          <span className="text-muted-foreground">
                            Last run
                            <span className="ml-1 font-medium text-foreground">{lastRunMetric}</span>
                          </span>
                          <span className="text-muted-foreground">
                            Next run
                            <span className="ml-1 font-medium text-foreground">{compactNextRunValue}</span>
                          </span>
                        </div>
                      )}
                      {isActive &&
                        (isRunning ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="destructive"
                            className="h-7 gap-1 px-2 text-xs"
                            aria-label={`Stop run for ${source.name}`}
                            title="Stop run"
                            onClick={() => handleStopPipelineRun(source)}
                          >
                            <Square className="size-3" />
                            Stop run
                          </Button>
                        ) : (
                          <div className="flex items-center">
                            <Button
                              type="button"
                              size="icon"
                              variant="default"
                              className="size-7 rounded-r-none"
                              aria-label={`Run pipeline for ${source.name}`}
                              title="Run pipeline"
                              onClick={() => handleRunFullPipeline(source, false)}
                              disabled={runningPipelineSourceId === source.id}
                            >
                              <Play className="size-3.5" />
                            </Button>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button
                                  type="button"
                                  size="icon"
                                  variant="default"
                                  className="size-7 rounded-l-none border-l border-primary-foreground/20"
                                  aria-label={`Run options for ${source.name}`}
                                  title="More run options: full pipeline or quick test"
                                  disabled={runningPipelineSourceId === source.id}
                                >
                                  <ChevronDown className="size-3.5" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem
                                  disabled={runningPipelineSourceId === source.id}
                                  onClick={() => handleRunFullPipeline(source, false)}
                                >
                                  Run full pipeline
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  disabled={runningPipelineSourceId === source.id}
                                  onClick={() => handleRunFullPipeline(source, true)}
                                >
                                  Run quick test (stage cap 5)
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                        ))}
                      {showsAiControls && (
                        <TooltipProvider delayDuration={120}>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                type="button"
                                size="icon"
                                variant="outline"
                              className="size-7"
                              aria-label={`Configure ${source.name}`}
                              title="Configure source"
                              disabled={isRunning}
                              onClick={() => {
                                setConfigurationDialogActivationIntent(false)
                                setConfigurationDialogTab('schedule')
                                  setConfigurationDialogSource(source)
                                }}
                              >
                                <Settings2 className="size-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Configure source</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                      {showLifecycleToggle && (
                        <Button
                          type="button"
                          size="sm"
                          variant="default"
                          className="h-7 px-3 text-xs"
                          disabled={togglingSourceId === source.id || isRunning}
                          onClick={() => handleToggleSourceStatus(source)}
                        >
                          {togglingSourceId === source.id ? (
                            <Loader2 className="size-3 animate-spin" />
                          ) : (
                            lifecycleLabel
                          )}
                        </Button>
                      )}
                      {showOverflowMenu && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              className="text-muted-foreground opacity-50 transition-opacity hover:opacity-100"
                              disabled={isRunning}
                            >
                              <MoreVertical className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem asChild>
                              <Link href={`/spaces/${spaceId}/data-sources/${source.id}/workflow?tab=setup`}>
                                Open pipeline workspace
                              </Link>
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => setDetailSourceId(source.id)}>
                              View details
                            </DropdownMenuItem>
                            {isActive && (
                              <>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  disabled={togglingSourceId === source.id}
                                  onClick={() => handleToggleSourceStatus(source)}
                                >
                                  Disable source
                                </DropdownMenuItem>
                              </>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => setDeleteSourceId(source.id)}
                            >
                              <Trash2 className="mr-2 size-4" />
                              Remove source
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </div>
                  </div>
                  {executionStatusLine && isExpanded && (
                    <p className="text-sm text-muted-foreground">{executionStatusLine}</p>
                  )}
                  {isExpanded &&
                    !isRunning &&
                    isActive &&
                    (workflowStatus?.pending_paper_count ?? 0) > 0 && (
                      <p className="text-sm text-amber-700">
                        Queue backlog: {workflowStatus?.pending_paper_count ?? 0} pending paper
                        {(workflowStatus?.pending_paper_count ?? 0) === 1 ? '' : 's'}.
                      </p>
                    )}
                  {isExpanded &&
                    !isRunning &&
                    isActive &&
                    (workflowStatus?.extraction_timeout_failed_count ?? 0) > 0 && (
                      <p className="text-sm text-destructive">
                        Timeout failures: {workflowStatus?.extraction_timeout_failed_count ?? 0}{' '}
                        paper{(workflowStatus?.extraction_timeout_failed_count ?? 0) === 1 ? '' : 's'} hit
                        timeout in the latest run.
                      </p>
                    )}
                  {isExpanded &&
                    !isRunning &&
                    isActive &&
                    (workflowStatus?.extraction_failed_count ?? 0) > 0 && (
                      <p className="text-sm text-destructive">
                        Extraction failures: {workflowStatus?.extraction_failed_count ?? 0} paper
                        {(workflowStatus?.extraction_failed_count ?? 0) === 1 ? '' : 's'} failed in the
                        latest run.
                      </p>
                    )}
                </CardHeader>
                {isExpanded && (
                  <CardContent className="space-y-4">
                    {isRunning && (
                      <div className="rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-foreground">
                        <div className="flex items-center gap-2">
                          <Loader2 className="size-4 animate-spin text-primary" />
                          <span>Live run in progress. Processing pipeline stages.</span>
                        </div>
                        <p className="mt-1 pl-6 text-xs text-muted-foreground">
                          Stage: {liveStageLabel} · Last signal: {lastSignalLabel} · Last poll: {lastPollLabel}
                          {artanaStageLabel ? ` · Artana: ${artanaStageLabel}` : ''}
                          {' · '}
                          {lastSignalSummary}
                        </p>
                        <div className="mt-1 space-y-1 pl-6 text-xs text-muted-foreground">
                          {recentWorkflowEventSignals.length === 0 ? (
                            <p>
                              Recent backend events:{' '}
                              {describeRecentWorkflowEventPlaceholder(workflowStatus)}
                            </p>
                          ) : (
                            recentWorkflowEventSignals.map((eventSignal) => {
                              const eventAge = formatElapsedSeconds(
                                liveStatusNowMs,
                                toTimestampMs(eventSignal.occurred_at),
                                'unknown',
                              )
                              const eventScope = eventSignal.stage ?? eventSignal.category ?? 'event'
                              const eventStatus = eventSignal.status ? `/${eventSignal.status}` : ''
                              return (
                                <p key={eventSignal.event_id}>
                                  {eventAge} · {eventScope}
                                  {eventStatus} · {eventSignal.message}
                                </p>
                              )
                            })
                          )}
                        </div>
                      </div>
                    )}
                    <div className="grid gap-6 xl:grid-cols-12 xl:items-start xl:divide-x xl:divide-border">
                    <div className="grid w-full grid-cols-[120px_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm xl:col-span-4 xl:pr-6 2xl:col-span-3">
                      <div className="text-muted-foreground/80">Type</div>
                      <div className="font-semibold capitalize text-foreground">{source.source_type}</div>

                      <div className="text-muted-foreground/80">{isPubMedSource ? 'Access' : 'Status'}</div>
                      <div className="font-semibold text-foreground">
                        {isPubMedSource ? (
                          <span className="inline-flex items-center gap-2 whitespace-nowrap">
                            Open Access
                            <TooltipProvider delayDuration={120}>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span
                                    role="img"
                                    aria-label={
                                      pubMedSnapshot?.openAccessOnly
                                        ? 'Open access enforced'
                                        : 'Open access not enforced'
                                    }
                                    className="inline-flex cursor-help items-center text-muted-foreground"
                                  >
                                    <ShieldCheck className="size-4" />
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>
                                  {pubMedSnapshot?.openAccessOnly ? 'Enforced' : 'Not enforced'}
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </span>
                        ) : (
                          source.status
                        )}
                      </div>

                      <div className="inline-flex items-center gap-1 text-muted-foreground/80">
                        {isPubMedSource ? 'Cap / run' : 'Schedule'}
                        {isPubMedSource && (
                          <TooltipProvider delayDuration={120}>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="inline-flex cursor-help items-center">
                                  <Info className="size-3.5" />
                                </span>
                              </TooltipTrigger>
                              <TooltipContent>Maximum papers ingested per run.</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                      </div>
                      <div className="font-semibold text-foreground">
                        {isPubMedSource
                          ? (pubMedSnapshot?.maxResults ?? 'Not set')
                          : formatScheduleLabel(source)}
                      </div>

                      <div className="text-muted-foreground/80">Ingestion</div>
                      <div className="font-semibold text-foreground">{formatTimestamp(source.last_ingested_at)}</div>

                      <div className="text-muted-foreground/80">Persistence</div>
                      <div className="font-semibold text-foreground">Deterministic</div>
                    </div>

                    <div className="w-full space-y-3 xl:col-span-8 xl:pl-6 2xl:col-span-9">
                      <div className="space-y-3 rounded-md bg-muted/20 p-4">
                        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-0 md:divide-x md:divide-border">
                          {countTelemetryMetrics.map((metric) => (
                            <div key={metric.label} className="space-y-1 md:px-3">
                              <div className="text-xl font-semibold leading-none">{metric.value}</div>
                              <div className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                                {metric.label}
                                {metric.tooltip && (
                                  <TooltipProvider delayDuration={120}>
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <span className="inline-flex cursor-help items-center">
                                          <Info className="size-3.5" />
                                        </span>
                                      </TooltipTrigger>
                                      <TooltipContent>{metric.tooltip}</TooltipContent>
                                    </Tooltip>
                                  </TooltipProvider>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                        {lastExecutionAt && (
                          <div className="flex items-center justify-between rounded-md border bg-background/60 px-3 py-2 text-sm">
                            <div className="text-muted-foreground">Last run</div>
                            <div className="font-medium">{lastRunMetric}</div>
                          </div>
                        )}
                        {!lastExecutionAt && (
                          <div className="space-y-2 rounded-md bg-background/70 px-3 py-2">
                            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                              {isRunning ? (
                                <Loader2 className="size-4 animate-spin" />
                              ) : (
                                <Play className="size-4" />
                              )}
                              <span>
                                {isRunning
                                  ? 'Run in progress · awaiting completion status.'
                                  : 'Never run · No execution history available.'}
                              </span>
                            </div>
                          </div>
                        )}
                      </div>

                      {!isActive && (
                        <div className="rounded-md border border-amber-300/60 bg-amber-50/60 px-3 py-2 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200">
                          {inactiveMessage}
                        </div>
                      )}
                    </div>
                  </div>
                  </CardContent>
                )}
              </Card>
            )
          })}
        </div>
      )}

      <DataSourceConfigurationDialog
        spaceId={spaceId}
        source={configurationDialogSource}
        workflowStatus={configurationSourceWorkflowStatus}
        open={Boolean(configurationDialogSource)}
        initialTab={configurationDialogTab}
        activationIntent={configurationDialogActivationIntent}
        onOpenChange={(open) => {
          if (!open) {
            setConfigurationDialogSource(null)
            setConfigurationDialogActivationIntent(false)
          }
        }}
      />
      <DataSourceIngestionDetailsDialog
        source={detailSource}
        open={Boolean(detailSourceId)}
        onOpenChange={(open) => {
          if (!open) {
            setDetailSourceId(null)
          }
        }}
      />
      <DiscoverSourcesDialog
        spaceId={spaceId}
        open={isDiscoverDialogOpen}
        onOpenChange={setIsDiscoverDialogOpen}
        discoveryState={discoveryState}
        discoveryCatalog={discoveryCatalog}
        discoveryError={discoveryError}
        onSourceAdded={() => {
          void queryClient.invalidateQueries({ queryKey: queryKeys.spaceDataSources(spaceId, {}) })
        }}
      />
      <Dialog open={Boolean(deleteSourceId)} onOpenChange={(open) => !open && setDeleteSourceId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove data source</DialogTitle>
            <DialogDescription>
              Are you sure you want to remove this data source? This action cannot be undone and will
              permanently delete the source from this research space.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeleteSourceId(null)}
              disabled={isDeletingSource}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={handleDelete}
              disabled={isDeletingSource}
            >
              {isDeletingSource && <Loader2 className="mr-2 size-4 animate-spin" />}
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
