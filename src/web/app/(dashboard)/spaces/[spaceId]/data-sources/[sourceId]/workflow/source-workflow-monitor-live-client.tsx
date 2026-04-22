"use client"

import { startTransition, useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

import { useSourceWorkflowStream } from '@/hooks/use-source-workflow-stream'
import type { ArtanaRunTraceResponse } from '@/types/artana'
import type {
  SourcePipelineRunsResponse,
  SourceWorkflowEventsResponse,
  SourceWorkflowMonitorResponse,
  SourceWorkflowStreamBootstrapPayload,
  SourceWorkflowStreamSnapshotPayload,
} from '@/types/kernel'

import { SourceWorkflowMonitorView } from './source-workflow-monitor-view'
import type { WorkflowTabKey } from './source-workflow-monitor-tab-sections'

const WORKFLOW_SSE_ENABLED = process.env.NEXT_PUBLIC_WORKFLOW_SSE_ENABLED !== 'false'

interface SourceWorkflowMonitorLiveClientProps {
  spaceId: string
  sourceId: string
  selectedRunId?: string
  traceRunId?: string
  initialTab: WorkflowTabKey
  initialState: {
    monitor: SourceWorkflowMonitorResponse | null
    pipelineRuns: SourcePipelineRunsResponse | null
    workflowEvents: SourceWorkflowEventsResponse | null
    trace: ArtanaRunTraceResponse | null
  }
  initialErrors: {
    monitor: string | null
    trace: string | null
  }
}

function resolveSourceIdFromMonitor(
  fallbackSourceId: string,
  monitor: SourceWorkflowMonitorResponse,
): string {
  const sourceSnapshot = monitor.source_snapshot
  if (
    typeof sourceSnapshot === 'object' &&
    sourceSnapshot !== null &&
    !Array.isArray(sourceSnapshot)
  ) {
    const rawSourceId = sourceSnapshot.source_id
    if (typeof rawSourceId === 'string' && rawSourceId.trim().length > 0) {
      return rawSourceId
    }
  }
  return fallbackSourceId
}

function mapMonitorToPipelineRuns(
  sourceId: string,
  monitor: SourceWorkflowMonitorResponse,
): SourcePipelineRunsResponse {
  const runs = Array.isArray(monitor.pipeline_runs) ? monitor.pipeline_runs : []
  return {
    source_id: sourceId,
    runs,
    total: runs.length,
  }
}

function applyMonitorSnapshot(
  sourceId: string,
  payload: SourceWorkflowStreamBootstrapPayload | SourceWorkflowStreamSnapshotPayload,
): {
  monitor: SourceWorkflowMonitorResponse
  pipelineRuns: SourcePipelineRunsResponse
} {
  const resolvedSourceId = resolveSourceIdFromMonitor(sourceId, payload.monitor)
  return {
    monitor: payload.monitor,
    pipelineRuns: mapMonitorToPipelineRuns(resolvedSourceId, payload.monitor),
  }
}

function asIsoTimestamp(value: string | null | undefined): number {
  if (typeof value !== 'string' || value.trim().length === 0) {
    return 0
  }
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function extractEventSequence(eventId: string): number {
  const separatorIndex = eventId.lastIndexOf(':')
  if (separatorIndex < 0) {
    return -1
  }
  const parsed = Number(eventId.slice(separatorIndex + 1))
  return Number.isFinite(parsed) ? parsed : -1
}

export function mergeWorkflowEvents(
  previous: SourceWorkflowEventsResponse | null,
  incoming: SourceWorkflowEventsResponse,
): SourceWorkflowEventsResponse {
  const mergedById = new Map<string, SourceWorkflowEventsResponse['events'][number]>()

  for (const event of previous?.events ?? []) {
    mergedById.set(event.event_id, event)
  }
  for (const event of incoming.events) {
    mergedById.set(event.event_id, event)
  }

  const mergedEvents = Array.from(mergedById.values()).sort((left, right) => {
    const timestampDelta = asIsoTimestamp(right.occurred_at) - asIsoTimestamp(left.occurred_at)
    if (timestampDelta !== 0) {
      return timestampDelta
    }
    return extractEventSequence(right.event_id) - extractEventSequence(left.event_id)
  })

  return {
    source_id: incoming.source_id,
    run_id: incoming.run_id,
    generated_at: incoming.generated_at,
    events: mergedEvents,
    total: mergedEvents.length,
    has_more: incoming.has_more,
  }
}

export function SourceWorkflowMonitorLiveClient({
  spaceId,
  sourceId,
  selectedRunId,
  traceRunId,
  initialTab,
  initialState,
  initialErrors,
}: SourceWorkflowMonitorLiveClientProps) {
  const router = useRouter()
  const [monitor, setMonitor] = useState<SourceWorkflowMonitorResponse | null>(
    initialState.monitor,
  )
  const [monitorError, setMonitorError] = useState<string | null>(initialErrors.monitor)
  const [pipelineRuns, setPipelineRuns] = useState<SourcePipelineRunsResponse | null>(
    initialState.pipelineRuns,
  )
  const [workflowEvents, setWorkflowEvents] = useState<SourceWorkflowEventsResponse | null>(
    initialState.workflowEvents,
  )
  const [trace, setTrace] = useState<ArtanaRunTraceResponse | null>(initialState.trace)
  const [traceError, setTraceError] = useState<string | null>(initialErrors.trace)
  const streamEnabled = useMemo(() => WORKFLOW_SSE_ENABLED, [])

  const refreshTrace = useCallback(async (runId: string) => {
    const response = await fetch(
      `/api/research-spaces/${spaceId}/artana-runs/${encodeURIComponent(runId)}`,
      {
        cache: 'no-store',
      },
    )
    const responseText = await response.text()
    if (!response.ok) {
      let detail = 'Unable to load Artana trace.'
      if (responseText) {
        try {
          const parsed = JSON.parse(responseText) as { detail?: string }
          if (typeof parsed.detail === 'string' && parsed.detail.trim().length > 0) {
            detail = parsed.detail
          }
        } catch {
          detail = responseText
        }
      }
      throw new Error(detail)
    }
    const parsed = JSON.parse(responseText) as ArtanaRunTraceResponse
    startTransition(() => {
      setTrace(parsed)
      setTraceError(null)
    })
  }, [spaceId])

  const {
    isFallbackActive: isSseFallbackActive,
    lastError: streamError,
  } = useSourceWorkflowStream({
    spaceId,
    sourceId,
    runId: selectedRunId,
    enabled: streamEnabled,
    onBootstrap: (payload) => {
      const nextState = applyMonitorSnapshot(sourceId, payload)
      setMonitor(nextState.monitor)
      setPipelineRuns(nextState.pipelineRuns)
      setWorkflowEvents((previous) =>
        mergeWorkflowEvents(previous, {
          source_id: nextState.pipelineRuns.source_id,
          run_id: payload.run_id ?? null,
          generated_at: payload.generated_at,
          events: payload.events,
          total: payload.events.length,
          has_more: false,
        }),
      )
      setMonitorError(null)
      if (traceRunId) {
        void refreshTrace(traceRunId).catch((error: unknown) => {
          setTraceError(error instanceof Error ? error.message : 'Unable to load Artana trace.')
        })
      }
    },
    onSnapshot: (payload) => {
      const nextState = applyMonitorSnapshot(sourceId, payload)
      setMonitor(nextState.monitor)
      setPipelineRuns(nextState.pipelineRuns)
      setMonitorError(null)
      if (traceRunId) {
        void refreshTrace(traceRunId).catch((error: unknown) => {
          setTraceError(error instanceof Error ? error.message : 'Unable to load Artana trace.')
        })
      }
    },
    onEvents: (payload) => {
      setWorkflowEvents((previous) => ({
        ...mergeWorkflowEvents(previous, {
          source_id: previous?.source_id ?? sourceId,
          run_id: payload.run_id ?? null,
          generated_at: payload.generated_at,
          events: payload.events,
          total: payload.events.length,
          has_more: false,
        }),
      }))
    },
  })

  useEffect(() => {
    if (streamError !== null) {
      setMonitorError((previous) => previous ?? streamError)
    }
  }, [streamError])

  useEffect(() => {
    if (!streamEnabled || !isSseFallbackActive) {
      return
    }
    const intervalId = window.setInterval(() => {
      router.refresh()
    }, 4000)
    return () => {
      window.clearInterval(intervalId)
    }
  }, [isSseFallbackActive, router, streamEnabled])

  useEffect(() => {
    if (!traceRunId) {
      setTrace(null)
      setTraceError(null)
      return
    }
    void refreshTrace(traceRunId).catch((error: unknown) => {
      setTrace(null)
      setTraceError(error instanceof Error ? error.message : 'Unable to load Artana trace.')
    })
  }, [refreshTrace, traceRunId])

  return (
    <SourceWorkflowMonitorView
      spaceId={spaceId}
      selectedRunId={selectedRunId}
      traceRunId={traceRunId}
      monitor={monitor}
      monitorError={monitorError}
      pipelineRuns={pipelineRuns}
      workflowEvents={workflowEvents}
      trace={trace}
      traceError={traceError}
      initialTab={initialTab}
    />
  )
}
