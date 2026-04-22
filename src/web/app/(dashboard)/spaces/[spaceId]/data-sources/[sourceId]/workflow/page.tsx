import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'

import { fetchSpaceArtanaRunTrace } from '@/lib/api/artana'
import {
  fetchSourcePipelineRuns,
  fetchSourceWorkflowEvents,
  fetchSourceWorkflowMonitor,
} from '@/lib/api/kernel'
import { authOptions } from '@/lib/auth'
import type { ArtanaRunTraceResponse } from '@/types/artana'
import type {
  SourcePipelineRunsResponse,
  SourceWorkflowEventsResponse,
  SourceWorkflowMonitorResponse,
} from '@/types/kernel'

import { SourceWorkflowMonitorLiveClient } from './source-workflow-monitor-live-client'
import { resolveInitialWorkflowRunId } from './source-workflow-monitor-run-selection'
import type { WorkflowTabKey } from './source-workflow-monitor-tab-sections'

interface SourceWorkflowMonitorPageProps {
  params: Promise<{
    spaceId: string
    sourceId: string
  }>
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}

function firstParam(value: string | string[] | undefined): string | undefined {
  if (typeof value === 'string') {
    return value
  }
  return Array.isArray(value) ? value[0] : undefined
}

function parseTab(value: string | undefined): WorkflowTabKey {
  if (value === 'run' || value === 'review' || value === 'graph' || value === 'trace') {
    return value
  }
  return 'setup'
}

export default async function SourceWorkflowMonitorPage({
  params,
  searchParams,
}: SourceWorkflowMonitorPageProps) {
  const { spaceId, sourceId } = await params
  const resolvedSearchParams = searchParams ? await searchParams : undefined
  const requestedRunId = firstParam(resolvedSearchParams?.run_id)
  const initialTab = parseTab(firstParam(resolvedSearchParams?.tab))
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let monitor: SourceWorkflowMonitorResponse | null = null
  let monitorError: string | null = null
  let pipelineRuns: SourcePipelineRunsResponse | null = null
  let workflowEvents: SourceWorkflowEventsResponse | null = null
  let trace: ArtanaRunTraceResponse | null = null
  let traceError: string | null = null

  try {
    monitor = await fetchSourceWorkflowMonitor(
      spaceId,
      sourceId,
      {
        run_id: requestedRunId,
        limit: 50,
        include_graph: true,
      },
      token,
    )
  } catch (error) {
    monitorError = error instanceof Error ? error.message : 'Unable to load workflow monitor.'
  }

  try {
    pipelineRuns = await fetchSourcePipelineRuns(spaceId, sourceId, { limit: 50 }, token)
  } catch {
    pipelineRuns = null
  }

  const effectiveRunId = resolveInitialWorkflowRunId(
    requestedRunId,
    monitor,
    pipelineRuns,
  )

  try {
    workflowEvents = await fetchSourceWorkflowEvents(
      spaceId,
      sourceId,
      {
        run_id: effectiveRunId,
        limit: 100,
      },
      token,
    )
  } catch {
    workflowEvents = null
  }

  if (requestedRunId) {
    try {
      trace = await fetchSpaceArtanaRunTrace(spaceId, requestedRunId, token)
    } catch (error) {
      traceError = error instanceof Error ? error.message : 'Unable to load Artana trace.'
    }
  }

  return (
    <SourceWorkflowMonitorLiveClient
      spaceId={spaceId}
      sourceId={sourceId}
      selectedRunId={effectiveRunId}
      traceRunId={requestedRunId}
      initialTab={initialTab}
      initialState={{
        monitor,
        pipelineRuns,
        workflowEvents,
        trace,
      }}
      initialErrors={{
        monitor: monitorError,
        trace: traceError,
      }}
    />
  )
}
