import Link from 'next/link'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { AuditLogListResponse, AuditLogQueryParams } from '@/types/audit'

interface AuditEventsCardProps {
  filters: AuditLogQueryParams
  logs: AuditLogListResponse | null
  logsError?: string | null
}

function buildPageHref(
  filters: AuditLogQueryParams,
  page: number,
  perPage: number,
): string {
  const params = new URLSearchParams()
  if (filters.action) {
    params.set('action', filters.action)
  }
  if (filters.entity_type) {
    params.set('entity_type', filters.entity_type)
  }
  if (filters.entity_id) {
    params.set('entity_id', filters.entity_id)
  }
  if (filters.actor_id) {
    params.set('actor_id', filters.actor_id)
  }
  if (filters.request_id) {
    params.set('request_id', filters.request_id)
  }
  if (filters.ip_address) {
    params.set('ip_address', filters.ip_address)
  }
  if (typeof filters.success === 'boolean') {
    params.set('success', String(filters.success))
  }
  if (filters.created_after) {
    params.set('created_after', filters.created_after)
  }
  if (filters.created_before) {
    params.set('created_before', filters.created_before)
  }
  params.set('page', String(page))
  params.set('per_page', String(perPage))
  return `?${params.toString()}`
}

export function AuditEventsCard({
  filters,
  logs,
  logsError,
}: AuditEventsCardProps) {
  const rows = logs?.logs ?? []
  const total = logs?.total ?? 0
  const currentPage = logs?.page ?? filters.page ?? 1
  const pageSize = logs?.per_page ?? filters.per_page ?? 50
  const hasPreviousPage = currentPage > 1
  const hasNextPage = currentPage * pageSize < total

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Events</CardTitle>
        <CardDescription>
          {logsError ? (
            <span className="text-destructive">{logsError}</span>
          ) : (
            <span>{total.toLocaleString()} total events</span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {logsError ? null : rows.length === 0 ? (
          <div className="py-12 text-center text-muted-foreground">
            No audit logs found for the selected filters.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Created</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Entity</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Request</TableHead>
                <TableHead>IP</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="text-xs">
                    {row.created_at ? new Date(row.created_at).toLocaleString() : '—'}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{row.action}</TableCell>
                  <TableCell className="text-xs">
                    <div>{row.entity_type}</div>
                    <div className="font-mono text-muted-foreground">{row.entity_id}</div>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{row.user ?? '—'}</TableCell>
                  <TableCell className="font-mono text-xs">{row.request_id ?? '—'}</TableCell>
                  <TableCell className="font-mono text-xs">{row.ip_address ?? '—'}</TableCell>
                  <TableCell>
                    {row.success === null ? (
                      <Badge variant="secondary">N/A</Badge>
                    ) : row.success ? (
                      <Badge>Success</Badge>
                    ) : (
                      <Badge variant="destructive">Failure</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {!logsError && total > 0 ? (
          <div className="mt-4 flex items-center justify-between">
            <div className="text-sm text-muted-foreground">
              Page {currentPage} • Showing up to {pageSize} rows
            </div>
            <div className="flex gap-2">
              <Button asChild variant="outline" size="sm" disabled={!hasPreviousPage}>
                <Link href={buildPageHref(filters, currentPage - 1, pageSize)}>
                  Previous
                </Link>
              </Button>
              <Button asChild variant="outline" size="sm" disabled={!hasNextPage}>
                <Link href={buildPageHref(filters, currentPage + 1, pageSize)}>
                  Next
                </Link>
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
