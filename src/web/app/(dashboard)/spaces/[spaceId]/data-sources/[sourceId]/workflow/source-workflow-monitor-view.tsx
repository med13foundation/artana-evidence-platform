"use client"

import Link from 'next/link'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { ArtanaRunTraceResponse } from '@/types/artana'
import type {
  SourcePipelineRunsResponse,
  SourceWorkflowEventsResponse,
  SourceWorkflowMonitorResponse,
} from '@/types/kernel'

import {
  GraphTabSection,
  ReviewTabSection,
  RunMonitorTabSection,
  SetupTabSection,
  TraceTabSection,
  type WorkflowTabKey,
} from './source-workflow-monitor-tab-sections'
import { asList, asRecord, displayValue } from './source-workflow-monitor-utils'

interface SourceWorkflowMonitorViewProps {
  spaceId: string
  selectedRunId?: string
  traceRunId?: string
  monitor: SourceWorkflowMonitorResponse | null
  monitorError: string | null
  pipelineRuns: SourcePipelineRunsResponse | null
  workflowEvents: SourceWorkflowEventsResponse | null
  trace: ArtanaRunTraceResponse | null
  traceError: string | null
  initialTab?: WorkflowTabKey
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

function resolveArtanaStageLabel(stageName: string, currentStage: unknown): string {
  if (stageName !== 'pipeline' || typeof currentStage !== 'string') {
    return stageName
  }
  const normalized = currentStage.trim().toLowerCase()
  return normalized.length > 0 ? normalized : stageName
}

export function SourceWorkflowMonitorView({
  spaceId,
  selectedRunId,
  traceRunId,
  monitor,
  monitorError,
  pipelineRuns,
  workflowEvents,
  trace,
  traceError,
  initialTab = 'setup',
}: SourceWorkflowMonitorViewProps) {
  const sourceSnapshot = asRecord(monitor?.source_snapshot)
  const schedule = asRecord(sourceSnapshot.schedule)
  const counters = asRecord(monitor?.operational_counters)
  const runRows = asList(pipelineRuns?.runs ?? monitor?.pipeline_runs ?? [])
  const documentRows = asList(monitor?.documents)
  const paperCandidateRows = asList(monitor?.paper_candidates)
  const queueRows = asList(monitor?.extraction_queue)
  const extractionRows = asList(monitor?.publication_extractions)
  const relationReview = asRecord(monitor?.relation_review)
  const relationRows = asList(relationReview.persisted_relation_rows)
  const pendingRelationRows = asList(relationReview.pending_review_relation_rows)
  const reviewQueueRows = asList(relationReview.review_queue_rows)
  const rejectedRows = asList(relationReview.rejected_relation_rows)
  const lastRun = asRecord(monitor?.last_run)
  const workflowEventRows = asList(workflowEvents?.events)
  const graphSummary = asRecord(monitor?.graph_summary)
  const artanaProgress = asRecord(monitor?.artana_progress)
  const artanaProgressRows = Object.entries(artanaProgress).map(([stageName, rawValue]) => {
    const payload = asRecord(rawValue)
    return {
      stage: stageName,
      run_id: payload.run_id,
      status: payload.status,
      percent: payload.percent,
      current_stage: payload.current_stage,
    }
  })
  const warnings = Array.isArray(monitor?.warnings)
    ? monitor?.warnings.filter((item): item is string => typeof item === 'string')
    : []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Pipeline workspace</h1>
          <p className="text-sm text-muted-foreground">
            Source: {displayValue(sourceSnapshot.name)} ({displayValue(sourceSnapshot.source_type)})
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link href={`/spaces/${spaceId}/data-sources`}>Back to data sources</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href={`/spaces/${spaceId}/knowledge-graph`}>Open graph</Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="flex flex-wrap items-center gap-2 py-4 text-xs">
          <Badge variant="outline">
            Last pipeline: {displayValue(counters.last_pipeline_status)}
          </Badge>
          <Badge variant="outline">
            Pending papers: {toNumber(counters.pending_paper_count)}
          </Badge>
          <Badge variant="outline">
            Pending review: {toNumber(counters.pending_relation_review_count)}
          </Badge>
          <Badge variant="outline">
            Graph Δ edges: {toNumber(counters.graph_edges_delta_last_run)}
          </Badge>
          <Badge variant="outline">
            Graph total edges: {toNumber(counters.graph_edges_total)}
          </Badge>
          {artanaProgressRows.length > 0 && (
            <Badge variant="outline">
              Artana stages: {artanaProgressRows.length}
            </Badge>
          )}
        </CardContent>
      </Card>

      {artanaProgressRows.length > 0 && (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-2 py-4 text-xs">
            {artanaProgressRows.map((row) => {
              const percentLabel =
                typeof row.percent === 'number' ? `${row.percent}%` : 'n/a'
              const stageLabel = resolveArtanaStageLabel(
                displayValue(row.stage),
                row.current_stage,
              )
              return (
                <Badge key={`${displayValue(row.stage)}-${displayValue(row.run_id)}`} variant="outline">
                  {stageLabel}: {displayValue(row.status)} ({percentLabel})
                </Badge>
              )
            })}
          </CardContent>
        </Card>
      )}

      {monitorError ? (
        <Card>
          <CardContent className="py-8 text-sm text-destructive">{monitorError}</CardContent>
        </Card>
      ) : (
        <Tabs defaultValue={initialTab} className="space-y-4">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="setup">Setup</TabsTrigger>
            <TabsTrigger value="run">Run Monitor</TabsTrigger>
            <TabsTrigger value="review">Review</TabsTrigger>
            <TabsTrigger value="graph">Graph</TabsTrigger>
            <TabsTrigger value="trace">Trace</TabsTrigger>
          </TabsList>

          <TabsContent value="setup">
            <SetupTabSection
              sourceSnapshot={sourceSnapshot}
              schedule={schedule}
              selectedRunId={selectedRunId}
              warnings={warnings}
              eventRows={workflowEventRows}
            />
          </TabsContent>

          <TabsContent value="run">
            <RunMonitorTabSection
              lastRun={lastRun}
              counters={counters}
              runRows={runRows}
              documentRows={documentRows}
              paperCandidateRows={paperCandidateRows}
              queueRows={queueRows}
              extractionRows={extractionRows}
              eventRows={workflowEventRows}
              warnings={warnings}
            />
          </TabsContent>

          <TabsContent value="review">
            <ReviewTabSection
              relationRows={relationRows}
              pendingRelationRows={pendingRelationRows}
              reviewQueueRows={reviewQueueRows}
              rejectedRows={rejectedRows}
            />
          </TabsContent>

          <TabsContent value="graph">
            <GraphTabSection spaceId={spaceId} graphSummary={graphSummary} />
          </TabsContent>

          <TabsContent value="trace">
            <TraceTabSection
              selectedRunId={traceRunId}
              trace={trace}
              traceError={traceError}
            />
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}
