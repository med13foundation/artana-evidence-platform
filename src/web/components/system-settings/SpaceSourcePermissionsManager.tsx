"use client"

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Loader2 } from 'lucide-react'
import {
  clearProjectAvailabilityAction,
  updateProjectAvailabilityAction,
} from '@/app/actions/data-source-availability'
import type { PermissionLevel, DataSourceAvailability } from '@/lib/api/data-source-activation'
import type { SourceCatalogEntry } from '@/lib/types/data-discovery'
import type { ResearchSpace } from '@/types/research-space'
import { toast } from 'sonner'
import { mergeAvailabilitySummaries } from '@/lib/query/admin-cache'
import { queryKeys } from '@/lib/query/query-keys'
import { availabilitySummariesQueryOptions } from '@/lib/query/query-options'

const PERMISSION_LABELS: Record<PermissionLevel, string> = {
  available: 'Available',
  visible: 'Visible',
  blocked: 'Blocked',
}

const PERMISSION_VARIANTS: Record<PermissionLevel, 'default' | 'secondary' | 'destructive'> = {
  available: 'default',
  visible: 'secondary',
  blocked: 'destructive',
}

const PERMISSION_DESCRIPTIONS: Record<PermissionLevel, string> = {
  available: 'Catalog + testing enabled',
  visible: 'Catalog only',
  blocked: 'Hidden and disabled',
}

const PERMISSION_ORDER: PermissionLevel[] = ['available', 'visible', 'blocked']

function getEffectivePermission(
  summary: DataSourceAvailability | undefined,
  spaceId: string,
): PermissionLevel {
  if (!summary) {
    return 'available'
  }
  const override = summary.project_rules.find((rule) => rule.research_space_id === spaceId)
  if (override) {
    return override.permission_level
  }
  return summary.global_rule?.permission_level ?? summary.effective_permission_level ?? 'available'
}

interface SpaceSourcePermissionsManagerProps {
  catalogEntries: SourceCatalogEntry[]
  availabilitySummaries: DataSourceAvailability[]
  spaces: ResearchSpace[]
}

export function SpaceSourcePermissionsManager({
  catalogEntries,
  availabilitySummaries,
  spaces,
}: SpaceSourcePermissionsManagerProps) {
  const queryClient = useQueryClient()
  const [isApplying, setIsApplying] = useState(false)
  const availabilityQuery = useQuery(
    availabilitySummariesQueryOptions(availabilitySummaries),
  )
  const resolvedAvailabilitySummaries = availabilityQuery.data ?? availabilitySummaries

  const summaryMap = useMemo(() => {
    const data = resolvedAvailabilitySummaries ?? []
    return new Map(data.map((summary) => [summary.catalog_entry_id, summary]))
  }, [resolvedAvailabilitySummaries])

  const handlePermissionChange = async (
    sourceId: string,
    spaceId: string,
    value: PermissionLevel | 'inherit',
  ) => {
    try {
      setIsApplying(true)
      if (value === 'inherit') {
        const result = await clearProjectAvailabilityAction(sourceId, spaceId)
        if (!result.success) {
          toast.error(result.error)
          return
        }
        queryClient.setQueryData<DataSourceAvailability[]>(
          queryKeys.availabilitySummaries(),
          (current) => mergeAvailabilitySummaries(current ?? [], [result.data]),
        )
      } else {
        const result = await updateProjectAvailabilityAction(sourceId, spaceId, value)
        if (!result.success) {
          toast.error(result.error)
          return
        }
        queryClient.setQueryData<DataSourceAvailability[]>(
          queryKeys.availabilitySummaries(),
          (current) => mergeAvailabilitySummaries(current ?? [], [result.data]),
        )
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.availabilitySummaries() })
    } finally {
      setIsApplying(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Space-Source Permission Matrix</CardTitle>
        <CardDescription>
          Review and adjust the permission level each research space receives for catalog sources.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {catalogEntries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No catalog entries available.</p>
        ) : spaces.length === 0 ? (
          <p className="text-sm text-muted-foreground">No research spaces available.</p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-[220px]">Source</TableHead>
                  {spaces.map((space) => (
                    <TableHead key={space.id} className="min-w-[160px] text-center">
                      {space.name}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {catalogEntries.map((source) => {
                  const summary = summaryMap.get(source.id)
                  return (
                    <TableRow key={source.id}>
                      <TableCell>
                        <div className="font-medium">{source.name}</div>
                        <div className="text-xs text-muted-foreground">{source.category}</div>
                      </TableCell>
                      {spaces.map((space) => {
                        const override = summary?.project_rules.find(
                          (rule) => rule.research_space_id === space.id,
                        )
                        const effective = getEffectivePermission(summary, space.id)
                        const inherited =
                          summary?.global_rule?.permission_level ??
                          summary?.effective_permission_level ??
                          'available'
                        const selectValue = override ? override.permission_level : 'inherit'
                        return (
                          <TableCell key={`${source.id}-${space.id}`} className="text-center">
                            <div className="flex flex-col gap-2">
                              <Badge variant={PERMISSION_VARIANTS[effective]}>
                                {PERMISSION_LABELS[effective]}
                                {override ? ' • Override' : ''}
                              </Badge>
                              <Select
                                value={selectValue}
                                onValueChange={(value) =>
                                  handlePermissionChange(
                                    source.id,
                                    space.id,
                                    value as PermissionLevel | 'inherit',
                                  )
                                }
                                disabled={isApplying}
                              >
                                <SelectTrigger className="w-full">
                                  <SelectValue placeholder="Select permission" />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="inherit">
                                    Inherit ({PERMISSION_LABELS[inherited]})
                                  </SelectItem>
                                  {PERMISSION_ORDER.map((permission) => (
                                    <SelectItem key={permission} value={permission}>
                                      {PERMISSION_LABELS[permission]} — {PERMISSION_DESCRIPTIONS[permission]}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                          </TableCell>
                        )
                      })}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
        {isApplying && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Applying permission change…
          </div>
        )}
      </CardContent>
    </Card>
  )
}
