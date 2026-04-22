import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  getClaimParticipantCoverageAction,
  listClaimParticipantsAction,
  listClaimRelationsAction,
  runClaimParticipantBackfillAction,
  updateClaimRelationReviewAction,
} from '@/app/actions/kernel-claim-relations'
import { listHypothesesAction } from '@/app/actions/kernel-hypotheses'
import type {
  ClaimParticipantCoverageResponse,
  ClaimParticipantResponse,
  ClaimRelationResponse,
  ClaimRelationReviewStatus,
  HypothesisResponse,
} from '@/types/kernel'

import type { ReviewStatusFilter } from './claim-overlay-toolbar'

interface ClaimOverlayPanelState {
  isLoading: boolean
  isParticipantLoading: boolean
  pendingRelationId: string | null
  reviewFilter: ReviewStatusFilter
  relations: ClaimRelationResponse[]
  claimsById: Record<string, HypothesisResponse>
  selectedClaimId: string | null
  selectedParticipants: ClaimParticipantResponse[]
  coverage: ClaimParticipantCoverageResponse | null
  isBackfillRunning: boolean
  error: string | null
}

const INITIAL_STATE: ClaimOverlayPanelState = {
  isLoading: false,
  isParticipantLoading: false,
  pendingRelationId: null,
  reviewFilter: 'ALL',
  relations: [],
  claimsById: {},
  selectedClaimId: null,
  selectedParticipants: [],
  coverage: null,
  isBackfillRunning: false,
  error: null,
}

interface UseClaimOverlayDataArgs {
  spaceId: string
  canCurate: boolean
}

interface UseClaimOverlayDataResult {
  state: ClaimOverlayPanelState
  filteredRelations: ClaimRelationResponse[]
  setReviewFilter: (value: ReviewStatusFilter) => void
  refreshOverlay: () => Promise<void>
  selectClaimParticipants: (claimId: string) => Promise<void>
  updateReviewStatus: (
    relation: ClaimRelationResponse,
    reviewStatus: ClaimRelationReviewStatus,
  ) => Promise<void>
  runBackfill: (dryRun: boolean) => Promise<void>
}

function toClaimIndex(claims: HypothesisResponse[]): Record<string, HypothesisResponse> {
  const claimIndex: Record<string, HypothesisResponse> = {}
  for (const claim of claims) {
    claimIndex[claim.claim_id] = claim
  }
  return claimIndex
}

export function useClaimOverlayData({
  spaceId,
  canCurate,
}: UseClaimOverlayDataArgs): UseClaimOverlayDataResult {
  const [state, setState] = useState<ClaimOverlayPanelState>(INITIAL_STATE)

  const refreshOverlay = useCallback(async (): Promise<void> => {
    setState((previous) => ({ ...previous, isLoading: true }))
    const [relationsResult, claimsResult, coverageResult] = await Promise.all([
      listClaimRelationsAction(spaceId, { offset: 0, limit: 200 }),
      listHypothesesAction(spaceId),
      getClaimParticipantCoverageAction(spaceId),
    ])

    if (!relationsResult.success) {
      setState((previous) => ({
        ...previous,
        isLoading: false,
        error: relationsResult.error,
      }))
      return
    }
    if (!claimsResult.success) {
      setState((previous) => ({
        ...previous,
        isLoading: false,
        error: claimsResult.error,
      }))
      return
    }
    if (!coverageResult.success) {
      setState((previous) => ({
        ...previous,
        isLoading: false,
        error: coverageResult.error,
      }))
      return
    }

    setState((previous) => ({
      ...previous,
      isLoading: false,
      error: null,
      relations: relationsResult.data,
      claimsById: toClaimIndex(claimsResult.data),
      coverage: coverageResult.data,
    }))
  }, [spaceId])

  useEffect(() => {
    void refreshOverlay()
  }, [refreshOverlay])

  const filteredRelations = useMemo(() => {
    if (state.reviewFilter === 'ALL') {
      return state.relations
    }
    return state.relations.filter((relation) => relation.review_status === state.reviewFilter)
  }, [state.relations, state.reviewFilter])

  const setReviewFilter = useCallback((value: ReviewStatusFilter): void => {
    setState((previous) => ({
      ...previous,
      reviewFilter: value,
    }))
  }, [])

  const selectClaimParticipants = useCallback(
    async (claimId: string): Promise<void> => {
      setState((previous) => ({
        ...previous,
        selectedClaimId: claimId,
        isParticipantLoading: true,
      }))

      const result = await listClaimParticipantsAction(spaceId, claimId)
      if (!result.success) {
        setState((previous) => ({
          ...previous,
          isParticipantLoading: false,
          selectedParticipants: [],
          error: result.error,
        }))
        toast.error(result.error)
        return
      }

      setState((previous) => ({
        ...previous,
        isParticipantLoading: false,
        selectedParticipants: result.data,
        error: null,
      }))
    },
    [spaceId],
  )

  const updateReviewStatus = useCallback(
    async (
      relation: ClaimRelationResponse,
      reviewStatus: ClaimRelationReviewStatus,
    ): Promise<void> => {
      if (!canCurate) {
        toast.error('You do not have permission to review claim relations.')
        return
      }
      setState((previous) => ({ ...previous, pendingRelationId: relation.id }))

      const result = await updateClaimRelationReviewAction(spaceId, relation.id, reviewStatus)
      if (!result.success) {
        setState((previous) => ({
          ...previous,
          pendingRelationId: null,
          error: result.error,
        }))
        toast.error(result.error)
        return
      }

      setState((previous) => ({
        ...previous,
        pendingRelationId: null,
        error: null,
        relations: previous.relations.map((candidate) =>
          candidate.id === relation.id ? result.data : candidate,
        ),
      }))
      toast.success(`Claim edge moved to ${reviewStatus.toLowerCase()}.`)
    },
    [canCurate, spaceId],
  )

  const runBackfill = useCallback(
    async (dryRun: boolean): Promise<void> => {
      if (!canCurate) {
        toast.error('You do not have permission to run participant backfill.')
        return
      }

      setState((previous) => ({ ...previous, isBackfillRunning: true }))
      const result = await runClaimParticipantBackfillAction(spaceId, dryRun)
      if (!result.success) {
        setState((previous) => ({
          ...previous,
          isBackfillRunning: false,
          error: result.error,
        }))
        toast.error(result.error)
        return
      }

      setState((previous) => ({ ...previous, isBackfillRunning: false, error: null }))
      toast.success(
        `Backfill ${dryRun ? 'dry run' : 'apply run'}: scanned ${result.data.scanned_claims}, created ${result.data.created_participants}.`,
      )
      await refreshOverlay()
    },
    [canCurate, refreshOverlay, spaceId],
  )

  return {
    state,
    filteredRelations,
    setReviewFilter,
    refreshOverlay,
    selectClaimParticipants,
    updateReviewStatus,
    runBackfill,
  }
}
