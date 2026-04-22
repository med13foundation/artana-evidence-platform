import type {
  ClaimRelationResponse,
  ClaimRelationReviewStatus,
  HypothesisResponse,
} from '@/types/kernel'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

function compactId(value: string): string {
  if (value.length <= 18) {
    return value
  }
  return `${value.slice(0, 8)}...${value.slice(-6)}`
}

function summarizeClaim(claim: HypothesisResponse | undefined, claimId: string): string {
  if (!claim) {
    return `Claim ${claimId.slice(0, 8)}...`
  }
  const source = claim.source_label?.trim() || 'Unknown source'
  const target = claim.target_label?.trim() || 'Unknown target'
  return `${source} -> ${claim.relation_type} -> ${target}`
}

function summarizeSnippet(claim: HypothesisResponse | undefined): string | null {
  if (!claim?.claim_text) {
    return null
  }
  const trimmed = claim.claim_text.trim()
  if (trimmed.length === 0) {
    return null
  }
  if (trimmed.length <= 150) {
    return trimmed
  }
  return `${trimmed.slice(0, 147)}...`
}

function statusBadgeVariant(
  status: HypothesisResponse['claim_status'],
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'RESOLVED') return 'default'
  if (status === 'NEEDS_MAPPING') return 'secondary'
  if (status === 'REJECTED') return 'destructive'
  return 'outline'
}

function polarityBadgeVariant(
  polarity: HypothesisResponse['polarity'],
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (polarity === 'SUPPORT') return 'default'
  if (polarity === 'REFUTE') return 'destructive'
  if (polarity === 'HYPOTHESIS') return 'secondary'
  return 'outline'
}

interface ClaimOverlayRelationListProps {
  relations: ClaimRelationResponse[]
  claimsById: Record<string, HypothesisResponse>
  canCurate: boolean
  pendingRelationId: string | null
  highlightedRelationIds: ReadonlySet<string>
  highlightedClaimIds: ReadonlySet<string>
  openClaimsTab: () => void
  openCanonicalGraphRelation: (relationId: string) => void
  selectClaimParticipants: (claimId: string) => void
  updateReviewStatus: (input: ClaimOverlayReviewUpdate) => void
}

interface ClaimOverlayReviewUpdate {
  relation: ClaimRelationResponse
  reviewStatus: ClaimRelationReviewStatus
}

export function ClaimOverlayRelationList({
  relations,
  claimsById,
  canCurate,
  pendingRelationId,
  highlightedRelationIds,
  highlightedClaimIds,
  openClaimsTab,
  openCanonicalGraphRelation,
  selectClaimParticipants,
  updateReviewStatus,
}: ClaimOverlayRelationListProps) {
  return (
    <div className="space-y-3">
      {relations.map((relation) => {
        const sourceClaim = claimsById[relation.source_claim_id]
        const targetClaim = claimsById[relation.target_claim_id]
        const isPending = pendingRelationId === relation.id
        const sourceSnippet = summarizeSnippet(sourceClaim)
        const targetSnippet = summarizeSnippet(targetClaim)
        const evidenceSummary = relation.evidence_summary?.trim() ?? ''
        const isHighlightedRelation = highlightedRelationIds.has(relation.id)
        const isHighlightedSource = highlightedClaimIds.has(relation.source_claim_id)
        const isHighlightedTarget = highlightedClaimIds.has(relation.target_claim_id)
        const sourceLinkedRelationId =
          typeof sourceClaim?.linked_relation_id === 'string'
            ? sourceClaim.linked_relation_id.trim()
            : ''
        const targetLinkedRelationId =
          typeof targetClaim?.linked_relation_id === 'string'
            ? targetClaim.linked_relation_id.trim()
            : ''
        const canonicalRelationIds = Array.from(
          new Set(
            [sourceLinkedRelationId, targetLinkedRelationId].filter(
              (relationId) => relationId.length > 0,
            ),
          ),
        )
        return (
          <Card
            key={relation.id}
            className={
              isHighlightedRelation
                ? 'border-primary/60 bg-card ring-1 ring-primary/35'
                : 'border-border/70'
            }
          >
            <CardContent className="space-y-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">{relation.relation_type}</Badge>
                <Badge variant="outline">{relation.review_status}</Badge>
                <Badge variant="outline">{Math.round(relation.confidence * 100)}%</Badge>
                <Badge variant="outline">Edge {compactId(relation.id)}</Badge>
                {isHighlightedRelation ? <Badge variant="secondary">Focus path</Badge> : null}
              </div>
              <div className="grid gap-2 lg:grid-cols-2">
                <div
                  className={
                    isHighlightedSource
                      ? 'space-y-2 rounded-md border border-primary/55 bg-primary/5 p-3'
                      : 'space-y-2 rounded-md border border-border/70 p-3'
                  }
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">Source claim</Badge>
                    {sourceClaim ? (
                      <>
                        <Badge variant={statusBadgeVariant(sourceClaim.claim_status)}>
                          {sourceClaim.claim_status}
                        </Badge>
                        <Badge variant={polarityBadgeVariant(sourceClaim.polarity)}>
                          {sourceClaim.polarity}
                        </Badge>
                      </>
                    ) : null}
                    {isHighlightedSource ? <Badge variant="secondary">Path node</Badge> : null}
                  </div>
                  <p className="text-xs text-foreground">
                    {summarizeClaim(sourceClaim, relation.source_claim_id)}
                  </p>
                  {sourceSnippet ? (
                    <p className="text-xs text-muted-foreground">{sourceSnippet}</p>
                  ) : null}
                </div>
                <div
                  className={
                    isHighlightedTarget
                      ? 'space-y-2 rounded-md border border-primary/55 bg-primary/5 p-3'
                      : 'space-y-2 rounded-md border border-border/70 p-3'
                  }
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">Target claim</Badge>
                    {targetClaim ? (
                      <>
                        <Badge variant={statusBadgeVariant(targetClaim.claim_status)}>
                          {targetClaim.claim_status}
                        </Badge>
                        <Badge variant={polarityBadgeVariant(targetClaim.polarity)}>
                          {targetClaim.polarity}
                        </Badge>
                      </>
                    ) : null}
                    {isHighlightedTarget ? <Badge variant="secondary">Path node</Badge> : null}
                  </div>
                  <p className="text-xs text-foreground">
                    {summarizeClaim(targetClaim, relation.target_claim_id)}
                  </p>
                  {targetSnippet ? (
                    <p className="text-xs text-muted-foreground">{targetSnippet}</p>
                  ) : null}
                </div>
              </div>
              {evidenceSummary.length > 0 ? (
                <p className="text-xs text-muted-foreground">{evidenceSummary}</p>
              ) : (
                <p className="text-xs text-muted-foreground">No edge rationale recorded.</p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button type="button" size="sm" variant="outline" onClick={openClaimsTab}>
                  Open claims queue
                </Button>
                {canonicalRelationIds.length === 1 ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => openCanonicalGraphRelation(canonicalRelationIds[0])}
                  >
                    Open canonical relation
                  </Button>
                ) : null}
                {canonicalRelationIds.length === 2 ? (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => openCanonicalGraphRelation(canonicalRelationIds[0])}
                    >
                      Open source canonical relation
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => openCanonicalGraphRelation(canonicalRelationIds[1])}
                    >
                      Open target canonical relation
                    </Button>
                  </>
                ) : null}
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => selectClaimParticipants(relation.source_claim_id)}
                >
                  Source participants
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => selectClaimParticipants(relation.target_claim_id)}
                >
                  Target participants
                </Button>
                {canCurate ? (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={isPending || relation.review_status === 'PROPOSED'}
                      onClick={() => updateReviewStatus({ relation, reviewStatus: 'PROPOSED' })}
                    >
                      Proposed
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      disabled={isPending || relation.review_status === 'ACCEPTED'}
                      onClick={() => updateReviewStatus({ relation, reviewStatus: 'ACCEPTED' })}
                    >
                      Accept
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="destructive"
                      disabled={isPending || relation.review_status === 'REJECTED'}
                      onClick={() => updateReviewStatus({ relation, reviewStatus: 'REJECTED' })}
                    >
                      Reject
                    </Button>
                  </>
                ) : null}
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
