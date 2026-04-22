'use client'

import { useMemo } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

import {
  ClaimOverlayToolbar,
} from './claim-overlay/claim-overlay-toolbar'
import { ClaimOverlayRelationList } from './claim-overlay/claim-overlay-relation-list'
import { ClaimOverlayParticipantPanel } from './claim-overlay/claim-overlay-participant-panel'
import { ClaimOverlayFocusPathCard } from './claim-overlay/claim-overlay-focus-path-card'
import { useClaimOverlayData } from './claim-overlay/use-claim-overlay-data'
import { useClaimOverlayFocusPath } from './claim-overlay/use-claim-overlay-focus-path'

interface ClaimOverlayGraphPanelProps {
  spaceId: string
  canCurate: boolean
  openClaimsTab: () => void
  openCanonicalGraphRelation: (relationId: string) => void
}

export default function ClaimOverlayGraphPanel({
  spaceId,
  canCurate,
  openClaimsTab,
  openCanonicalGraphRelation,
}: ClaimOverlayGraphPanelProps) {
  const {
    state,
    filteredRelations,
    setReviewFilter,
    refreshOverlay,
    selectClaimParticipants,
    updateReviewStatus,
    runBackfill,
  } = useClaimOverlayData({
    spaceId,
    canCurate,
  })

  const {
    focusSourceEntityId,
    focusTargetEntityId,
    focusedClaimIds,
    focusedRelationIds,
    focusSummary,
    isPathFinding,
    setFocusSourceEntityId,
    setFocusTargetEntityId,
    findFocusPath,
    clearFocusPath,
  } = useClaimOverlayFocusPath({
    spaceId,
    relations: state.relations,
    reviewFilter: state.reviewFilter,
  })

  const highlightedClaimIds = useMemo(() => new Set(focusedClaimIds), [focusedClaimIds])
  const highlightedRelationIds = useMemo(() => new Set(focusedRelationIds), [focusedRelationIds])

  return (
    <div className="space-y-4">
      <ClaimOverlayToolbar
        canCurate={canCurate}
        isLoading={state.isLoading}
        isBackfillRunning={state.isBackfillRunning}
        coverage={state.coverage}
        reviewFilter={state.reviewFilter}
        refreshOverlay={() => void refreshOverlay()}
        runDryBackfill={() => void runBackfill(true)}
        runBackfill={() => void runBackfill(false)}
        openClaimsTab={openClaimsTab}
        changeReviewFilter={setReviewFilter}
      />

      <ClaimOverlayFocusPathCard
        focusSourceEntityId={focusSourceEntityId}
        focusTargetEntityId={focusTargetEntityId}
        isPathFinding={isPathFinding}
        focusSummary={focusSummary}
        focusedClaimIds={focusedClaimIds}
        setFocusSourceEntityId={setFocusSourceEntityId}
        setFocusTargetEntityId={setFocusTargetEntityId}
        findFocusPath={() => void findFocusPath()}
        clearFocusPath={clearFocusPath}
      />

      {state.error ? (
        <Card>
          <CardContent className="py-6 text-sm text-destructive">{state.error}</CardContent>
        </Card>
      ) : null}

      {filteredRelations.length === 0 ? (
        <Card>
          <CardContent className="space-y-3 py-8 text-center">
            <p className="text-sm text-muted-foreground">
              No claim overlay edges exist yet. Create/review links from the hypotheses workflow.
            </p>
            <Button type="button" onClick={openClaimsTab}>
              Create Or Review Claim Links
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
          <ClaimOverlayRelationList
            relations={filteredRelations}
            claimsById={state.claimsById}
            canCurate={canCurate}
            pendingRelationId={state.pendingRelationId}
            highlightedRelationIds={highlightedRelationIds}
            highlightedClaimIds={highlightedClaimIds}
            openClaimsTab={openClaimsTab}
            openCanonicalGraphRelation={openCanonicalGraphRelation}
            selectClaimParticipants={(claimId) => void selectClaimParticipants(claimId)}
            updateReviewStatus={({ relation, reviewStatus }) =>
              void updateReviewStatus(relation, reviewStatus)
            }
          />
          <ClaimOverlayParticipantPanel
            spaceId={spaceId}
            openClaimsTab={openClaimsTab}
            selectedClaimId={state.selectedClaimId}
            isLoading={state.isParticipantLoading}
            participants={state.selectedParticipants}
          />
        </div>
      )}
    </div>
  )
}
