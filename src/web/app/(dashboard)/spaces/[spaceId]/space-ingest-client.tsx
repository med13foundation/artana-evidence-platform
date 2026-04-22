"use client"

import Link from 'next/link'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Loader2, Play, PlayCircle } from 'lucide-react'

import {
  runAllActiveSpaceSourcesIngestionAction,
  runSingleSpaceSourceIngestionAction,
} from '@/app/actions/kernel-ingest'
import { DashboardSection } from '@/components/ui/composition-patterns'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { DataSource } from '@/types/data-source'
import type {
  SpaceRunActiveSourcesResponse,
  SpaceSourceIngestionRunResponse,
} from '@/types/kernel'

interface SpaceIngestClientProps {
  spaceId: string
  dataSources: DataSource[]
}

function formatTimestamp(value?: string | null): string {
  if (!value) {
    return 'Never'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Unknown'
  }
  return date.toLocaleString()
}

function requiresRunnableSchedule(source: DataSource): boolean {
  const schedule = source.ingestion_schedule
  return Boolean(schedule?.enabled && schedule.frequency !== 'manual')
}

function formatSchedule(source: DataSource): string {
  const schedule = source.ingestion_schedule
  if (!schedule || !schedule.enabled) {
    return 'Disabled'
  }
  if (schedule.frequency === 'cron') {
    return schedule.cron_expression ? `Cron (${schedule.cron_expression})` : 'Cron'
  }
  return schedule.frequency.charAt(0).toUpperCase() + schedule.frequency.slice(1)
}

function resultTone(status: SpaceSourceIngestionRunResponse['status']): string {
  if (status === 'completed') {
    return 'bg-emerald-100 text-emerald-800'
  }
  if (status === 'failed') {
    return 'bg-red-100 text-red-800'
  }
  return 'bg-amber-100 text-amber-800'
}

export default function SpaceIngestClient({ spaceId, dataSources }: SpaceIngestClientProps) {
  const [runningSourceId, setRunningSourceId] = useState<string | null>(null)
  const [isRunningAll, setIsRunningAll] = useState(false)
  const [lastBatchResult, setLastBatchResult] = useState<SpaceRunActiveSourcesResponse | null>(null)
  const [lastSingleRuns, setLastSingleRuns] = useState<Record<string, SpaceSourceIngestionRunResponse>>({})

  const activeSources = useMemo(
    () => dataSources.filter((source) => source.status === 'active'),
    [dataSources],
  )

  const runnableActiveSources = useMemo(
    () => activeSources.filter((source) => requiresRunnableSchedule(source)),
    [activeSources],
  )

  const handleRunAll = async () => {
    setIsRunningAll(true)
    const result = await runAllActiveSpaceSourcesIngestionAction(spaceId)
    setIsRunningAll(false)

    if (!result.success) {
      toast.error(result.error)
      return
    }

    setLastBatchResult(result.data)
    const completed = result.data.completed_sources
    const skipped = result.data.skipped_sources
    const failed = result.data.failed_sources
    toast.success(`Ingestion finished: ${completed} completed, ${skipped} skipped, ${failed} failed.`)
  }

  const handleRunSource = async (sourceId: string) => {
    setRunningSourceId(sourceId)
    const result = await runSingleSpaceSourceIngestionAction(spaceId, sourceId)
    setRunningSourceId(null)

    if (!result.success) {
      toast.error(result.error)
      return
    }

    setLastSingleRuns((current) => ({
      ...current,
      [sourceId]: result.data,
    }))

    toast.success(
      `Ingestion completed for ${result.data.source_name}: ${result.data.created_publications} new, ${result.data.updated_publications} updated publications.`,
    )
  }

  const sortedSources = [...dataSources].sort((left, right) => left.name.localeCompare(right.name))

  return (
    <div className="space-y-6">
      <DashboardSection
        title="Ingest"
        description="Run ingestion for configured data sources. Data must be configured first in Data Sources."
      >
        <div className="space-y-4">
          <Card>
            <CardHeader className="space-y-1">
              <CardTitle className="text-lg">Run Active Sources</CardTitle>
              <CardDescription>
                Executes only sources that are active in this space. Each active source must also have an enabled non-manual schedule.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-sm text-muted-foreground">
                {dataSources.length} configured source{dataSources.length === 1 ? '' : 's'} in this space, {activeSources.length} active, {runnableActiveSources.length} runnable.
              </div>
              <Button onClick={handleRunAll} disabled={isRunningAll || activeSources.length === 0}>
                {isRunningAll ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : (
                  <PlayCircle className="mr-2 size-4" />
                )}
                Run all active sources
              </Button>
            </CardContent>
          </Card>

          {sortedSources.length === 0 ? (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                No configured data sources in this space yet.
                <div className="mt-4">
                  <Button asChild>
                    <Link href={`/spaces/${spaceId}/data-sources`}>Configure Data Sources</Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {sortedSources.map((source) => {
                const isRunnable = source.status === 'active' && requiresRunnableSchedule(source)
                const lastSingleRun = lastSingleRuns[source.id]

                return (
                  <Card key={source.id}>
                    <CardHeader className="space-y-1">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <CardTitle className="text-base">{source.name}</CardTitle>
                          <CardDescription>
                            {source.description || 'No description'}
                          </CardDescription>
                        </div>
                        <Badge variant="outline" className="capitalize">
                          {source.status}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Schedule</span>
                        <span className="font-medium">{formatSchedule(source)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Next run</span>
                        <span className="font-medium">
                          {formatTimestamp(source.ingestion_schedule?.next_run_at)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Last ingested</span>
                        <span className="font-medium">{formatTimestamp(source.last_ingested_at)}</span>
                      </div>
                      <div className="pt-2">
                        <Button
                          onClick={() => handleRunSource(source.id)}
                          disabled={runningSourceId === source.id || !isRunnable}
                          className="w-full"
                        >
                          {runningSourceId === source.id ? (
                            <Loader2 className="mr-2 size-4 animate-spin" />
                          ) : (
                            <Play className="mr-2 size-4" />
                          )}
                          Run source
                        </Button>
                        {!isRunnable && (
                          <p className="mt-2 text-xs text-muted-foreground">
                            Source must be active with an enabled non-manual schedule to run.
                          </p>
                        )}
                      </div>

                      {lastSingleRun && (
                        <div className="rounded-md border p-3 text-xs">
                          <div className="mb-2 flex items-center justify-between">
                            <span className="font-medium">Last run</span>
                            <span className={`rounded px-2 py-0.5 font-medium capitalize ${resultTone(lastSingleRun.status)}`}>
                              {lastSingleRun.status}
                            </span>
                          </div>
                          <div>
                            {lastSingleRun.created_publications} new, {lastSingleRun.updated_publications} updated publications.
                          </div>
                          {lastSingleRun.message && (
                            <div className="mt-1 text-muted-foreground">{lastSingleRun.message}</div>
                          )}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}

          {lastBatchResult && (
            <Card>
              <CardHeader className="space-y-1">
                <CardTitle className="text-lg">Last Run Summary</CardTitle>
                <CardDescription>
                  {lastBatchResult.completed_sources} completed, {lastBatchResult.skipped_sources} skipped, {lastBatchResult.failed_sources} failed.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {lastBatchResult.runs.map((run) => (
                  <div key={run.source_id} className="flex items-center justify-between rounded border px-3 py-2 text-sm">
                    <div>
                      <div className="font-medium">{run.source_name}</div>
                      <div className="text-xs text-muted-foreground">
                        {run.created_publications} new, {run.updated_publications} updated
                        {run.message ? ` • ${run.message}` : ''}
                      </div>
                    </div>
                    <span className={`rounded px-2 py-0.5 text-xs font-medium capitalize ${resultTone(run.status)}`}>
                      {run.status}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent className="flex flex-col gap-2 py-6 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-sm text-muted-foreground">
                Manage source configuration and schedules in Data Sources.
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Button asChild variant="outline">
                  <Link href={`/spaces/${spaceId}/data-sources`}>Manage Data Sources</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link href={`/spaces/${spaceId}/observations`}>View Observations</Link>
                </Button>
                <Button asChild>
                  <Link href={`/spaces/${spaceId}/knowledge-graph`}>View Graph</Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </DashboardSection>
    </div>
  )
}
