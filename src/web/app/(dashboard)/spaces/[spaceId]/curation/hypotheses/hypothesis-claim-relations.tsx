'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  createClaimRelationAction,
  listClaimRelationsAction,
  updateClaimRelationReviewAction,
} from '@/app/actions/kernel-claim-relations'
import type {
  ClaimRelationResponse,
  ClaimRelationReviewStatus,
  ClaimRelationType,
  FactAssessment,
  HypothesisResponse,
} from '@/types/kernel'

import { Card, CardContent } from '@/components/ui/card'

import { type ClaimRelationOption, HypothesisClaimRelationForm } from './claim-relations/hypothesis-claim-relation-form'
import { HypothesisClaimRelationList } from './claim-relations/hypothesis-claim-relation-list'
import { type ClaimRelationReviewFilter, summarizeHypothesis } from './claim-relations/hypothesis-claim-relation-utils'

interface HypothesisClaimRelationsProps {
  spaceId: string
  canEdit: boolean
  hypotheses: HypothesisResponse[]
}

interface HypothesisClaimRelationsState {
  relations: ClaimRelationResponse[]
  isLoading: boolean
  isCreating: boolean
  pendingRelationId: string | null
  error: string | null
  sourceClaimId: string
  targetClaimId: string
  relationType: ClaimRelationType
  supportBand: FactAssessment['support_band']
  reviewFilter: ClaimRelationReviewFilter
}

const INITIAL_STATE: HypothesisClaimRelationsState = {
  relations: [],
  isLoading: false,
  isCreating: false,
  pendingRelationId: null,
  error: null,
  sourceClaimId: '',
  targetClaimId: '',
  relationType: 'SUPPORTS',
  supportBand: 'SUPPORTED',
  reviewFilter: 'ALL',
}

function buildManualClaimLinkAssessment(supportBand: FactAssessment['support_band']): FactAssessment {
  return {
    support_band: supportBand,
    grounding_level: 'GRAPH_INFERENCE',
    mapping_status: 'RESOLVED',
    speculation_level: 'DIRECT',
    confidence_rationale: `Manual claim-link curation selected support_band=${supportBand}.`,
  }
}

export function HypothesisClaimRelations({ spaceId, canEdit, hypotheses }: HypothesisClaimRelationsProps) {
  const [state, setState] = useState<HypothesisClaimRelationsState>(INITIAL_STATE)

  const claimIndex = useMemo(() => {
    const index = new Map<string, HypothesisResponse>()
    for (const hypothesis of hypotheses) {
      index.set(hypothesis.claim_id, hypothesis)
    }
    return index
  }, [hypotheses])

  const claimOptions = useMemo<ClaimRelationOption[]>(
    () =>
      hypotheses.map((hypothesis) => ({
        id: hypothesis.claim_id,
        label: summarizeHypothesis(hypothesis),
      })),
    [hypotheses],
  )

  useEffect(() => {
    if (claimOptions.length === 0) {
      setState((previous) => ({
        ...previous,
        sourceClaimId: '',
        targetClaimId: '',
      }))
      return
    }

    const defaultSource = claimOptions[0].id
    const defaultTarget = claimOptions[1]?.id ?? defaultSource
    setState((previous) => ({
      ...previous,
      sourceClaimId: previous.sourceClaimId || defaultSource,
      targetClaimId: previous.targetClaimId || defaultTarget,
    }))
  }, [claimOptions])

  const refreshRelations = useCallback(async (): Promise<void> => {
    setState((previous) => ({ ...previous, isLoading: true }))
    const result = await listClaimRelationsAction(spaceId, {
      offset: 0,
      limit: 200,
    })
    if (!result.success) {
      setState((previous) => ({
        ...previous,
        isLoading: false,
        error: result.error,
      }))
      return
    }

    setState((previous) => ({
      ...previous,
      isLoading: false,
      error: null,
      relations: result.data,
    }))
  }, [spaceId])

  useEffect(() => {
    void refreshRelations()
  }, [refreshRelations])

  const filteredRelations = useMemo(() => {
    if (state.reviewFilter === 'ALL') {
      return state.relations
    }
    return state.relations.filter((relation) => relation.review_status === state.reviewFilter)
  }, [state.relations, state.reviewFilter])

  async function createRelation(): Promise<void> {
    if (!canEdit) {
      const message = 'You do not have permission to create claim relations.'
      toast.error(message)
      setState((previous) => ({ ...previous, error: message }))
      return
    }
    if (!state.sourceClaimId || !state.targetClaimId) {
      setState((previous) => ({
        ...previous,
        error: 'Select both source and target claims.',
      }))
      return
    }
    if (state.sourceClaimId === state.targetClaimId) {
      setState((previous) => ({
        ...previous,
        error: 'Source and target claim IDs must be different.',
      }))
      return
    }

    setState((previous) => ({ ...previous, isCreating: true }))
    const result = await createClaimRelationAction(spaceId, {
      source_claim_id: state.sourceClaimId,
      target_claim_id: state.targetClaimId,
      relation_type: state.relationType,
      assessment: buildManualClaimLinkAssessment(state.supportBand),
      review_status: 'PROPOSED',
      metadata: { origin: 'manual_hypothesis_overlay' },
    })
    if (!result.success) {
      setState((previous) => ({
        ...previous,
        isCreating: false,
        error: result.error,
      }))
      toast.error(result.error)
      return
    }

    setState((previous) => ({
      ...previous,
      isCreating: false,
      error: null,
      relations: [result.data, ...previous.relations],
    }))
    toast.success('Claim relation created.')
  }

  async function updateReviewStatus(
    relation: ClaimRelationResponse,
    reviewStatus: ClaimRelationReviewStatus,
  ): Promise<void> {
    if (!canEdit) {
      const message = 'You do not have permission to review claim relations.'
      toast.error(message)
      setState((previous) => ({ ...previous, error: message }))
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
      relations: previous.relations.map((candidate) => (candidate.id === relation.id ? result.data : candidate)),
    }))
    toast.success(`Claim relation moved to ${reviewStatus.toLowerCase()}.`)
  }

  return (
    <Card className="border-border/70">
      <CardContent className="space-y-4 p-4">
        <div className="space-y-1">
          <h4 className="text-sm font-semibold text-foreground">Hypothesis Graph Links</h4>
          <p className="text-xs text-muted-foreground">
            Curate claim-to-claim links to capture mechanistic chains without writing canonical graph edges.
          </p>
        </div>

        <HypothesisClaimRelationForm
          model={{
            claimOptions,
            sourceClaimId: state.sourceClaimId,
            targetClaimId: state.targetClaimId,
            relationType: state.relationType,
            supportBand: state.supportBand,
            isCreating: state.isCreating,
            canEdit,
            isLoading: state.isLoading,
          }}
          actions={{
            setSourceClaimId: (value) => setState((previous) => ({ ...previous, sourceClaimId: value })),
            setTargetClaimId: (value) => setState((previous) => ({ ...previous, targetClaimId: value })),
            setRelationType: (value) => setState((previous) => ({ ...previous, relationType: value })),
            setSupportBand: (value) => setState((previous) => ({ ...previous, supportBand: value })),
            createRelation: () => void createRelation(),
            refreshRelations: () => void refreshRelations(),
          }}
        />

        {state.error ? <p className="text-sm text-destructive">{state.error}</p> : null}

        <HypothesisClaimRelationList
          relations={filteredRelations}
          reviewFilter={state.reviewFilter}
          pendingRelationId={state.pendingRelationId}
          canEdit={canEdit}
          claimIndex={claimIndex}
          changeReviewFilter={(value) => setState((previous) => ({ ...previous, reviewFilter: value }))}
          updateReviewStatus={(relation, reviewStatus) => void updateReviewStatus(relation, reviewStatus)}
        />
      </CardContent>
    </Card>
  )
}
