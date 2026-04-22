import { useMemo, useState } from 'react'

import { listClaimsByEntityAction } from '@/app/actions/kernel-claim-relations'
import type {
  ClaimParticipantResponse,
  ClaimParticipantRole,
  RelationClaimResponse,
} from '@/types/kernel'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

interface ClaimOverlayParticipantPanelProps {
  spaceId: string
  openClaimsTab: () => void
  selectedClaimId: string | null
  isLoading: boolean
  participants: ClaimParticipantResponse[]
}

const ROLE_ORDER: ClaimParticipantRole[] = [
  'SUBJECT',
  'OBJECT',
  'OUTCOME',
  'CONTEXT',
  'QUALIFIER',
  'MODIFIER',
]

const ROLE_DESCRIPTIONS: Record<ClaimParticipantRole, string> = {
  SUBJECT: 'Primary source endpoint',
  OBJECT: 'Primary target endpoint',
  OUTCOME: 'Outcome endpoint observed in the claim',
  CONTEXT: 'Contextual scope (cell type, cohort, condition)',
  QUALIFIER: 'Qualifier that narrows statement meaning',
  MODIFIER: 'Additional modifier attached to the claim',
}

function compactId(value: string): string {
  if (value.length <= 18) {
    return value
  }
  return `${value.slice(0, 8)}...${value.slice(-6)}`
}

export function ClaimOverlayParticipantPanel({
  spaceId,
  openClaimsTab,
  selectedClaimId,
  isLoading,
  participants,
}: ClaimOverlayParticipantPanelProps) {
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null)
  const [entityClaims, setEntityClaims] = useState<RelationClaimResponse[]>([])
  const [entityClaimsTotal, setEntityClaimsTotal] = useState(0)
  const [entityClaimsLoading, setEntityClaimsLoading] = useState(false)
  const [entityClaimsError, setEntityClaimsError] = useState<string | null>(null)

  async function loadEntityClaims(entityId: string): Promise<void> {
    setSelectedEntityId(entityId)
    setEntityClaimsLoading(true)
    setEntityClaimsError(null)
    const result = await listClaimsByEntityAction(spaceId, entityId, { offset: 0, limit: 20 })
    setEntityClaimsLoading(false)
    if (!result.success) {
      setEntityClaims([])
      setEntityClaimsTotal(0)
      setEntityClaimsError(result.error)
      return
    }
    setEntityClaims(result.data.claims)
    setEntityClaimsTotal(result.data.total)
    setEntityClaimsError(null)
  }

  const groupedParticipants = useMemo(() => {
    const grouped: Record<ClaimParticipantRole, ClaimParticipantResponse[]> = {
      SUBJECT: [],
      OBJECT: [],
      OUTCOME: [],
      CONTEXT: [],
      QUALIFIER: [],
      MODIFIER: [],
    }
    for (const participant of participants) {
      grouped[participant.role].push(participant)
    }
    for (const role of ROLE_ORDER) {
      grouped[role].sort((left, right) => {
        const leftPosition = left.position ?? Number.MAX_SAFE_INTEGER
        const rightPosition = right.position ?? Number.MAX_SAFE_INTEGER
        if (leftPosition !== rightPosition) {
          return leftPosition - rightPosition
        }
        const leftLabel = left.label?.trim() ?? ''
        const rightLabel = right.label?.trim() ?? ''
        return leftLabel.localeCompare(rightLabel)
      })
    }
    return grouped
  }, [participants])

  return (
    <Card className="h-fit border-border/70">
      <CardContent className="space-y-2 p-4">
        <h4 className="text-sm font-semibold">Participant Context</h4>
        {selectedClaimId ? (
          <p className="font-mono text-xs text-muted-foreground">
            Claim {selectedClaimId.slice(0, 8)}...
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">
            Select source or target participants from any edge.
          </p>
        )}

        {isLoading ? (
          <p className="text-xs text-muted-foreground">Loading participants...</p>
        ) : participants.length === 0 ? (
          <p className="text-xs text-muted-foreground">No structured participants found.</p>
        ) : (
          <div className="space-y-2">
            {ROLE_ORDER.map((role) => {
              const roleParticipants = groupedParticipants[role]
              if (roleParticipants.length === 0) {
                return null
              }
              return (
                <div key={role} className="space-y-2 rounded-md border border-border/70 p-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{role}</Badge>
                    <Badge variant="secondary">{roleParticipants.length}</Badge>
                    <span className="text-[11px] text-muted-foreground">
                      {ROLE_DESCRIPTIONS[role]}
                    </span>
                  </div>
                  {roleParticipants.map((participant) => {
                    const entityId = participant.entity_id
                    return (
                      <div key={participant.id} className="rounded-md border border-border/60 p-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={entityId ? 'outline' : 'destructive'}>
                            {entityId ? 'Mapped entity' : 'Unresolved endpoint'}
                          </Badge>
                          {entityId ? (
                            <span className="font-mono text-[11px] text-muted-foreground">
                              {compactId(entityId)}
                            </span>
                          ) : null}
                        </div>
                        <p className="text-xs text-foreground">
                          {participant.label?.trim() || 'No participant label'}
                        </p>
                        {entityId ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="mt-2"
                            onClick={() => void loadEntityClaims(entityId)}
                          >
                            Entity claims
                          </Button>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        )}

        {selectedEntityId ? (
          <div className="space-y-2 border-t border-border/70 pt-2">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                Claims for entity {compactId(selectedEntityId)}...
              </p>
              <Button type="button" size="sm" variant="outline" onClick={openClaimsTab}>
                Open Claims Queue
              </Button>
            </div>

            {entityClaimsLoading ? (
              <p className="text-xs text-muted-foreground">Loading entity claims...</p>
            ) : entityClaimsError ? (
              <p className="text-xs text-destructive">{entityClaimsError}</p>
            ) : entityClaims.length === 0 ? (
              <p className="text-xs text-muted-foreground">No claims linked to this entity.</p>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground">
                  Showing {entityClaims.length} of {entityClaimsTotal}.
                </p>
                {entityClaims.map((claim) => (
                  <div key={claim.id} className="rounded-md border border-border/70 p-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{claim.claim_status}</Badge>
                      <Badge variant="outline">{claim.polarity}</Badge>
                    </div>
                    <p className="text-xs text-foreground">
                      {claim.source_label?.trim() || 'Unknown source'} {claim.relation_type}{' '}
                      {claim.target_label?.trim() || 'Unknown target'}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
