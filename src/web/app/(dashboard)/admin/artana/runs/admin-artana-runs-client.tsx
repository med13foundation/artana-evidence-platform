import Link from 'next/link'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type {
  ArtanaRunListParams,
  ArtanaRunListResponse,
  ArtanaRunTraceResponse,
} from '@/types/artana'

interface AdminArtanaRunsClientProps {
  filters: ArtanaRunListParams
  selectedRunId?: string
  runs: ArtanaRunListResponse | null
  runsError?: string | null
  trace: ArtanaRunTraceResponse | null
  traceError?: string | null
}

function buildHref(
  filters: ArtanaRunListParams,
  selectedRunId?: string,
): string {
  const searchParams = new URLSearchParams()
  if (filters.q) {
    searchParams.set('q', filters.q)
  }
  if (filters.status) {
    searchParams.set('status', filters.status)
  }
  if (filters.space_id) {
    searchParams.set('space_id', filters.space_id)
  }
  if (filters.source_type) {
    searchParams.set('source_type', filters.source_type)
  }
  if (filters.alert_code) {
    searchParams.set('alert_code', filters.alert_code)
  }
  if (typeof filters.since_hours === 'number') {
    searchParams.set('since_hours', String(filters.since_hours))
  }
  searchParams.set('page', String(filters.page ?? 1))
  searchParams.set('per_page', String(filters.per_page ?? 25))
  if (selectedRunId) {
    searchParams.set('run_id', selectedRunId)
  }
  return `/admin/artana/runs?${searchParams.toString()}`
}

function SummaryCard({ title, value }: { title: string; value: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  )
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return JSON.stringify(value)
}

export default function AdminArtanaRunsClient({
  filters,
  selectedRunId,
  runs,
  runsError,
  trace,
  traceError,
}: AdminArtanaRunsClientProps) {
  const counters = runs?.counters
  const runRows = runs?.runs ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Artana Runs</h1>
        <p className="text-sm text-muted-foreground">
          Inspect run health, alerts, summaries, and linked MED13 records.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <SummaryCard title="Running" value={String(counters?.running ?? 0)} />
        <SummaryCard title="Failed" value={String(counters?.failed ?? 0)} />
        <SummaryCard title="Stuck" value={String(counters?.stuck ?? 0)} />
        <SummaryCard title="Drift" value={String(counters?.drift_detected ?? 0)} />
        <SummaryCard title="Budget" value={String(counters?.budget_warning ?? 0)} />
        <SummaryCard
          title="Unknown tool outcome"
          value={String(counters?.tool_unknown_outcome ?? 0)}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <form action="/admin/artana/runs" className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Input name="q" placeholder="Run id or source id" defaultValue={filters.q ?? ''} />
            <Input
              name="status"
              placeholder="Status"
              defaultValue={filters.status ?? ''}
            />
            <Input
              name="space_id"
              placeholder="Space id"
              defaultValue={filters.space_id ?? ''}
            />
            <Input
              name="source_type"
              placeholder="Source type"
              defaultValue={filters.source_type ?? ''}
            />
            <Input
              name="alert_code"
              placeholder="Alert code"
              defaultValue={filters.alert_code ?? ''}
            />
            <Input
              name="since_hours"
              placeholder="Since hours"
              defaultValue={
                typeof filters.since_hours === 'number'
                  ? String(filters.since_hours)
                  : ''
              }
            />
            <input type="hidden" name="page" value="1" />
            <input
              type="hidden"
              name="per_page"
              value={String(filters.per_page ?? 25)}
            />
            <div className="flex items-center gap-2">
              <Button type="submit" size="sm">Apply</Button>
              <Button asChild type="button" variant="outline" size="sm">
                <Link href="/admin/artana/runs">Clear</Link>
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>Runs</CardTitle>
          </CardHeader>
          <CardContent>
            {runsError ? (
              <p className="text-sm text-destructive">{runsError}</p>
            ) : runRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No Artana runs matched the current filters.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Run ID</TableHead>
                    <TableHead>Space</TableHead>
                    <TableHead>Source type</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Current stage</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead>Alerts</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runRows.map((run) => (
                    <TableRow key={run.run_id}>
                      <TableCell className="font-mono text-xs">
                        <Link
                          href={buildHref(filters, run.run_id)}
                          className={selectedRunId === run.run_id ? 'font-semibold underline' : 'underline'}
                        >
                          {run.run_id}
                        </Link>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{displayValue(run.space_id)}</TableCell>
                      <TableCell>{displayValue(run.source_type)}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{displayValue(run.status)}</Badge>
                      </TableCell>
                      <TableCell>{displayValue(run.current_stage)}</TableCell>
                      <TableCell>{displayValue(run.updated_at)}</TableCell>
                      <TableCell>{displayValue(run.alert_count)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Run detail</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!selectedRunId ? (
              <p className="text-sm text-muted-foreground">Select a run from the table to inspect trace detail.</p>
            ) : traceError ? (
              <p className="text-sm text-destructive">{traceError}</p>
            ) : !trace ? (
              <p className="text-sm text-muted-foreground">Run detail is unavailable.</p>
            ) : (
              <>
                <div className="space-y-2 text-sm">
                  <div className="grid grid-cols-[120px_1fr] gap-2">
                    <span className="text-muted-foreground">Run</span>
                    <span className="font-mono text-xs">{displayValue(trace.run_id)}</span>
                  </div>
                  <div className="grid grid-cols-[120px_1fr] gap-2">
                    <span className="text-muted-foreground">Status</span>
                    <span>{displayValue(trace.status)}</span>
                  </div>
                  <div className="grid grid-cols-[120px_1fr] gap-2">
                    <span className="text-muted-foreground">Stage</span>
                    <span>{displayValue(trace.current_stage)}</span>
                  </div>
                  <div className="grid grid-cols-[120px_1fr] gap-2">
                    <span className="text-muted-foreground">Updated</span>
                    <span>{displayValue(trace.updated_at)}</span>
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="text-sm font-medium">Alerts</div>
                  {trace.alerts.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No alerts.</p>
                  ) : (
                    trace.alerts.map((alert) => (
                      <div key={alert.code} className="rounded border px-3 py-2 text-sm">
                        <div className="flex items-center gap-2">
                          <Badge variant={alert.severity === 'error' ? 'destructive' : 'outline'}>
                            {alert.code}
                          </Badge>
                          <span>{alert.title}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>

                <div className="space-y-2">
                  <div className="text-sm font-medium">Legacy Artana tables</div>
                  {trace.raw_tables && trace.raw_tables.length > 0 ? (
                    trace.raw_tables.map((table) => (
                      <div key={table.table_name} className="rounded border px-3 py-2 text-sm">
                        <div className="font-medium">{table.table_name}</div>
                        <div className="text-muted-foreground">
                          Rows: {table.row_count} | Latest: {displayValue(table.latest_created_at)}
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-muted-foreground">No legacy Artana table samples were found.</p>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
