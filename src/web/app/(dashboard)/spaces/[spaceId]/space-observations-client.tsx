"use client"

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { DashboardSection } from '@/components/ui/composition-patterns'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { KernelObservationListResponse, KernelObservationResponse } from '@/types/kernel'

interface SpaceObservationsClientProps {
  spaceId: string
  observations: KernelObservationListResponse | null
  observationsError?: string | null
  filters: {
    subjectId: string
    variableId: string
    offset: number
    limit: number
  }
}

function formatObservationValue(obs: KernelObservationResponse): string {
  if (obs.value_numeric !== null) {
    return String(obs.value_numeric)
  }
  if (obs.value_text !== null) {
    return obs.value_text
  }
  if (obs.value_coded !== null) {
    return obs.value_coded
  }
  if (obs.value_boolean !== null) {
    return obs.value_boolean ? 'true' : 'false'
  }
  if (obs.value_date !== null) {
    return obs.value_date
  }
  if (obs.value_json !== null) {
    try {
      return JSON.stringify(obs.value_json)
    } catch {
      return '[json]'
    }
  }
  return '—'
}

export default function SpaceObservationsClient({
  spaceId,
  observations,
  observationsError,
  filters,
}: SpaceObservationsClientProps) {
  const router = useRouter()
  const [subjectId, setSubjectId] = useState(filters.subjectId)
  const [variableId, setVariableId] = useState(filters.variableId)

  const rows = useMemo(() => observations?.observations ?? [], [observations?.observations])

  return (
    <div className="space-y-6">
      <DashboardSection
        title="Observations"
        description="Browse kernel observations (typed facts) for this research space."
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setSubjectId('')
                setVariableId('')
                router.push(`/spaces/${spaceId}/observations`)
              }}
            >
              Clear
            </Button>
            <Button
              onClick={() => {
                const params = new URLSearchParams()
                const subjectTrim = subjectId.trim()
                const variableTrim = variableId.trim()
                if (subjectTrim) params.set('subject_id', subjectTrim)
                if (variableTrim) params.set('variable_id', variableTrim)
                router.push(
                  params.toString().length > 0
                    ? `/spaces/${spaceId}/observations?${params.toString()}`
                    : `/spaces/${spaceId}/observations`,
                )
              }}
            >
              Apply
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Card>
            <CardContent className="grid gap-4 py-6 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="subject_id">Subject Entity ID (optional)</Label>
                <Input
                  id="subject_id"
                  value={subjectId}
                  onChange={(e) => setSubjectId(e.target.value)}
                  placeholder="e.g. 3fa85f64-5717-4562-b3fc-2c963f66afa6"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="variable_id">Variable ID (optional)</Label>
                <Input
                  id="variable_id"
                  value={variableId}
                  onChange={(e) => setVariableId(e.target.value)}
                  placeholder="e.g. VAR_GENE_SYMBOL"
                />
              </div>
            </CardContent>
          </Card>

          {observationsError ? (
            <Card>
              <CardContent className="py-10 text-center text-destructive">
                {observationsError}
              </CardContent>
            </Card>
          ) : rows.length === 0 ? (
            <Card>
              <CardContent className="py-10 text-center text-muted-foreground">
                No observations found.
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-2">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Created</TableHead>
                      <TableHead>Subject</TableHead>
                      <TableHead>Variable</TableHead>
                      <TableHead>Value</TableHead>
                      <TableHead>Unit</TableHead>
                      <TableHead>Observed At</TableHead>
                      <TableHead>Confidence</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((obs) => (
                      <TableRow key={obs.id}>
                        <TableCell className="text-xs">{obs.created_at}</TableCell>
                        <TableCell className="font-mono text-xs">{obs.subject_id}</TableCell>
                        <TableCell className="font-mono text-xs">{obs.variable_id}</TableCell>
                        <TableCell className="text-xs">{formatObservationValue(obs)}</TableCell>
                        <TableCell className="text-xs">{obs.unit ?? '—'}</TableCell>
                        <TableCell className="text-xs">{obs.observed_at ?? '—'}</TableCell>
                        <TableCell className="text-xs">{obs.confidence}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </div>
      </DashboardSection>
    </div>
  )
}
