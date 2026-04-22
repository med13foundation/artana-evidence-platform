'use client'

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import { setConceptDecisionStatusAction } from '@/app/actions/concepts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type {
  ConceptDecisionResponse,
  ConceptDecisionStatus,
  ConceptMemberResponse,
  ConceptSetResponse,
} from '@/types/concepts'

interface ConceptDecisionsLedgerCardProps {
  spaceId: string
  canReview: boolean
  conceptSets: ConceptSetResponse[]
  conceptMembers: ConceptMemberResponse[]
  conceptDecisions: ConceptDecisionResponse[]
  error?: string | null
}

const DECISION_STATUSES: ConceptDecisionStatus[] = [
  'PROPOSED',
  'NEEDS_REVIEW',
  'APPROVED',
  'REJECTED',
  'APPLIED',
]

function decisionBadgeVariant(status: ConceptDecisionStatus): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'APPLIED' || status === 'APPROVED') {
    return 'default'
  }
  if (status === 'REJECTED') {
    return 'destructive'
  }
  if (status === 'NEEDS_REVIEW') {
    return 'secondary'
  }
  return 'outline'
}

export function ConceptDecisionsLedgerCard({
  spaceId,
  canReview,
  conceptSets,
  conceptMembers,
  conceptDecisions,
  error,
}: ConceptDecisionsLedgerCardProps) {
  const router = useRouter()
  const [pendingDecisionId, setPendingDecisionId] = useState<string | null>(null)
  const [statusDrafts, setStatusDrafts] = useState<Record<string, ConceptDecisionStatus>>({})

  const setNameById = useMemo(() => {
    const map: Record<string, string> = {}
    for (const conceptSet of conceptSets) {
      map[conceptSet.id] = conceptSet.name
    }
    return map
  }, [conceptSets])

  const memberLabelById = useMemo(() => {
    const map: Record<string, string> = {}
    for (const member of conceptMembers) {
      map[member.id] = member.canonical_label
    }
    return map
  }, [conceptMembers])

  const handleUpdateStatus = async (decisionId: string) => {
    if (!canReview) {
      toast.error('You do not have permission to set decision status.')
      return
    }

    const status = statusDrafts[decisionId]
    if (!status) {
      toast.error('Select a target status first.')
      return
    }

    setPendingDecisionId(decisionId)
    const result = await setConceptDecisionStatusAction(spaceId, decisionId, {
      decision_status: status,
    })
    setPendingDecisionId(null)

    if (!result.success) {
      toast.error(result.error)
      return
    }

    toast.success('Decision status updated')
    router.refresh()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Decision Ledger</CardTitle>
        <CardDescription>
          {error ? <span className="text-destructive">{error}</span> : `${conceptDecisions.length} total`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? null : conceptDecisions.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">No concept decisions recorded.</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Decision</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Harness</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {conceptDecisions.map((decision) => {
                const targetLabel =
                  (decision.concept_member_id ? memberLabelById[decision.concept_member_id] : null) ||
                  (decision.concept_set_id ? setNameById[decision.concept_set_id] : null) ||
                  decision.concept_link_id ||
                  '—'

                return (
                  <TableRow key={decision.id}>
                    <TableCell>
                      <p className="font-medium">{decision.decision_type}</p>
                      <p className="text-xs text-muted-foreground">
                        {decision.proposed_by} • {new Date(decision.created_at).toLocaleString()}
                      </p>
                    </TableCell>
                    <TableCell>
                      <Badge variant={decisionBadgeVariant(decision.decision_status)}>
                        {decision.decision_status}
                      </Badge>
                    </TableCell>
                    <TableCell>{decision.harness_outcome ?? '—'}</TableCell>
                    <TableCell>{targetLabel}</TableCell>
                    <TableCell>
                      {canReview ? (
                        <div className="flex items-center gap-2">
                          <Select
                            value={statusDrafts[decision.id] ?? ''}
                            onValueChange={(value: ConceptDecisionStatus) =>
                              setStatusDrafts((current) => ({ ...current, [decision.id]: value }))
                            }
                          >
                            <SelectTrigger className="h-8 w-[170px]">
                              <SelectValue placeholder="Set status" />
                            </SelectTrigger>
                            <SelectContent>
                              {DECISION_STATUSES.map((status) => (
                                <SelectItem key={status} value={status}>
                                  {status}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={pendingDecisionId === decision.id}
                            onClick={() => void handleUpdateStatus(decision.id)}
                          >
                            Apply
                          </Button>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">Curator role required</span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
