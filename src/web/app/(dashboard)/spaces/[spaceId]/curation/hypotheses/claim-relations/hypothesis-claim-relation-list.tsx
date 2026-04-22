import type {
  ClaimRelationResponse,
  ClaimRelationReviewStatus,
  HypothesisResponse,
} from '@/types/kernel'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

import {
  CLAIM_RELATION_REVIEW_STATUSES,
  type ClaimRelationReviewFilter,
  shortId,
  summarizeHypothesis,
} from './hypothesis-claim-relation-utils'

interface HypothesisClaimRelationListProps {
  relations: ClaimRelationResponse[]
  reviewFilter: ClaimRelationReviewFilter
  pendingRelationId: string | null
  canEdit: boolean
  claimIndex: Map<string, HypothesisResponse>
  changeReviewFilter: (value: ClaimRelationReviewFilter) => void
  updateReviewStatus: (
    relation: ClaimRelationResponse,
    reviewStatus: ClaimRelationReviewStatus,
  ) => void
}

export function HypothesisClaimRelationList({
  relations,
  reviewFilter,
  pendingRelationId,
  canEdit,
  claimIndex,
  changeReviewFilter,
  updateReviewStatus,
}: HypothesisClaimRelationListProps) {
  return (
    <>
      <div className="flex items-center gap-2">
        <Label htmlFor="claim-link-review-filter">Filter</Label>
        <Select
          value={reviewFilter}
          onValueChange={(value) => changeReviewFilter(value as ClaimRelationReviewFilter)}
        >
          <SelectTrigger id="claim-link-review-filter" className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All</SelectItem>
            {CLAIM_RELATION_REVIEW_STATUSES.map((status) => (
              <SelectItem key={status} value={status}>
                {status}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {relations.length === 0 ? (
        <p className="text-sm text-muted-foreground">No claim links have been created yet.</p>
      ) : (
        <div className="space-y-3">
          {relations.map((relation) => {
            const isPending = pendingRelationId === relation.id
            const sourceSummary = claimIndex.get(relation.source_claim_id)
            const targetSummary = claimIndex.get(relation.target_claim_id)
            return (
              <Card key={relation.id} className="border-border/70">
                <CardContent className="space-y-2 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">{relation.relation_type}</Badge>
                    <Badge variant="outline">{relation.review_status}</Badge>
                    <Badge variant="outline">{Math.round(relation.confidence * 100)}%</Badge>
                  </div>
                  <p className="text-sm">
                    {shortId(relation.source_claim_id)} {relation.relation_type}{' '}
                    {shortId(relation.target_claim_id)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {sourceSummary ? summarizeHypothesis(sourceSummary) : relation.source_claim_id}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {targetSummary ? summarizeHypothesis(targetSummary) : relation.target_claim_id}
                  </p>
                  {canEdit ? (
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={isPending || relation.review_status === 'PROPOSED'}
                        onClick={() => updateReviewStatus(relation, 'PROPOSED')}
                      >
                        Proposed
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        disabled={isPending || relation.review_status === 'ACCEPTED'}
                        onClick={() => updateReviewStatus(relation, 'ACCEPTED')}
                      >
                        Accept
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="destructive"
                        disabled={isPending || relation.review_status === 'REJECTED'}
                        onClick={() => updateReviewStatus(relation, 'REJECTED')}
                      >
                        Reject
                      </Button>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </>
  )
}
