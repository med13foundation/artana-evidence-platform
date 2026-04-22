import Link from 'next/link'

import { Download, RefreshCcw, Search } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { AuditLogQueryParams } from '@/types/audit'

interface AuditFiltersCardProps {
  filters: AuditLogQueryParams
  exportCsvHref: string
  exportJsonHref: string
  pageSize: number
}

function normalizeSuccessFilter(
  value: boolean | undefined,
): 'all' | 'true' | 'false' {
  if (value === true) {
    return 'true'
  }
  if (value === false) {
    return 'false'
  }
  return 'all'
}

export function AuditFiltersCard({
  filters,
  exportCsvHref,
  exportJsonHref,
  pageSize,
}: AuditFiltersCardProps) {
  return (
    <>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold">Audit Logs</h1>
          <p className="text-sm text-muted-foreground">
            Query and export compliance-grade audit events across the platform.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={exportCsvHref}>
              <Download className="mr-2 size-4" />
              Export CSV
            </a>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href={exportJsonHref}>
              <Download className="mr-2 size-4" />
              Export JSON
            </a>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/admin/audit">
              <RefreshCcw className="mr-2 size-4" />
              Reset
            </Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Filters</CardTitle>
          <CardDescription>
            Narrow events by actor, entity, request, or execution outcome.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form method="get" className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-1">
                <Label htmlFor="audit-action">Action</Label>
                <Input
                  id="audit-action"
                  name="action"
                  defaultValue={filters.action ?? ''}
                  placeholder="e.g. phi.read"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="audit-entity-type">Entity Type</Label>
                <Input
                  id="audit-entity-type"
                  name="entity_type"
                  defaultValue={filters.entity_type ?? ''}
                  placeholder="entity_identifiers"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="audit-entity-id">Entity ID</Label>
                <Input
                  id="audit-entity-id"
                  name="entity_id"
                  defaultValue={filters.entity_id ?? ''}
                  placeholder="UUID or ID"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="audit-actor-id">Actor ID</Label>
                <Input
                  id="audit-actor-id"
                  name="actor_id"
                  defaultValue={filters.actor_id ?? ''}
                  placeholder="User ID"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="audit-request-id">Request ID</Label>
                <Input
                  id="audit-request-id"
                  name="request_id"
                  defaultValue={filters.request_id ?? ''}
                  placeholder="X-Request-ID"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="audit-ip-address">IP Address</Label>
                <Input
                  id="audit-ip-address"
                  name="ip_address"
                  defaultValue={filters.ip_address ?? ''}
                  placeholder="203.0.113.42"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="audit-success">Result</Label>
                <select
                  id="audit-success"
                  name="success"
                  defaultValue={normalizeSuccessFilter(filters.success)}
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                >
                  <option value="all">All</option>
                  <option value="true">Success</option>
                  <option value="false">Failure</option>
                </select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="audit-per-page">Rows per page</Label>
                <select
                  id="audit-per-page"
                  name="per_page"
                  defaultValue={String(pageSize)}
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                >
                  <option value="25">25</option>
                  <option value="50">50</option>
                  <option value="100">100</option>
                  <option value="250">250</option>
                </select>
              </div>
            </div>
            <input type="hidden" name="page" value="1" />
            <div className="flex gap-2">
              <Button type="submit">
                <Search className="mr-2 size-4" />
                Apply Filters
              </Button>
              <Button asChild variant="outline">
                <Link href="/admin/audit">Clear</Link>
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </>
  )
}
