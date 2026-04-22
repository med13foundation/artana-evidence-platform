import type { ClaimParticipantCoverageResponse } from '@/types/kernel'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const REVIEW_STATUS_FILTERS = ['ALL', 'PROPOSED', 'ACCEPTED', 'REJECTED'] as const

export type ReviewStatusFilter = (typeof REVIEW_STATUS_FILTERS)[number]

interface ClaimOverlayToolbarProps {
  canCurate: boolean
  isLoading: boolean
  isBackfillRunning: boolean
  coverage: ClaimParticipantCoverageResponse | null
  reviewFilter: ReviewStatusFilter
  refreshOverlay: () => void
  runDryBackfill: () => void
  runBackfill: () => void
  openClaimsTab: () => void
  changeReviewFilter: (value: ReviewStatusFilter) => void
}

export function ClaimOverlayToolbar({
  canCurate,
  isLoading,
  isBackfillRunning,
  coverage,
  reviewFilter,
  refreshOverlay,
  runDryBackfill,
  runBackfill,
  openClaimsTab,
  changeReviewFilter,
}: ClaimOverlayToolbarProps) {
  return (
    <Card className="border-border/80 bg-card">
      <CardContent className="space-y-3 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            Claim overlay mode renders hypothesis nodes (`relation_claims`) and claim-to-claim
            edges (`claim_relations`) without mutating canonical relations.
          </p>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={refreshOverlay} disabled={isLoading}>
              Refresh overlay
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={isBackfillRunning || !canCurate}
              onClick={runDryBackfill}
            >
              Dry-run backfill
            </Button>
            <Button
              type="button"
              disabled={isBackfillRunning || !canCurate}
              onClick={runBackfill}
            >
              Backfill participants
            </Button>
            <Button type="button" onClick={openClaimsTab}>
              Go To Extraction Claims
            </Button>
          </div>
        </div>

        {coverage ? (
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">Claims {coverage.total_claims}</Badge>
            <Badge variant="outline">
              Subject coverage {coverage.claims_with_subject}/{coverage.total_claims}
            </Badge>
            <Badge variant="outline">
              Object coverage {coverage.claims_with_object}/{coverage.total_claims}
            </Badge>
            <Badge variant="outline">
              Unresolved {Math.round(coverage.unresolved_endpoint_rate * 100)}%
            </Badge>
          </div>
        ) : null}

        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase text-muted-foreground">Review</span>
          <Select
            value={reviewFilter}
            onValueChange={(value) => changeReviewFilter(value as ReviewStatusFilter)}
          >
            <SelectTrigger className="w-52">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {REVIEW_STATUS_FILTERS.map((status) => (
                <SelectItem key={status} value={status}>
                  {status}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  )
}
