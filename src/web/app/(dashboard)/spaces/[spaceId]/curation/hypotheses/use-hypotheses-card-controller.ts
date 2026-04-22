'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  createManualHypothesisAction,
  generateHypothesesAction,
  listHypothesesAction,
} from '@/app/actions/kernel-hypotheses'
import { updateRelationClaimStatusAction } from '@/app/actions/kernel-relations'
import type { HypothesisResponse } from '@/types/kernel'

import {
  type HypothesisClaimStatus,
  filterHypotheses,
  humanizeToken,
  normalizeSeedIds,
} from './hypothesis-utils'
import { buildHypothesisGenerationFeedback } from './hypothesis-generation-feedback'
import type {
  HypothesesCardController,
  HypothesesCardState,
  UseHypothesesCardControllerParams,
} from './hypotheses-controller-types'
import { INITIAL_STATE } from './hypotheses-controller-types'

export function useHypothesesCardController({
  spaceId,
  canEdit,
  autoGenerationEnabled,
}: UseHypothesesCardControllerParams): HypothesesCardController {
  const [state, setState] = useState<HypothesesCardState>(INITIAL_STATE)

  const refreshHypotheses = useCallback(async (): Promise<void> => {
    setState((previous) => ({ ...previous, isLoading: true }))
    const result = await listHypothesesAction(spaceId)
    if (!result.success) {
      setState((previous) => ({
        ...previous,
        isLoading: false,
        error: result.error,
        hypotheses: [],
        feedbackMessage: result.error,
        feedbackTone: 'error',
      }))
      return
    }
    setState((previous) => ({
      ...previous,
      isLoading: false,
      error: null,
      hypotheses: result.data,
    }))
  }, [spaceId])

  useEffect(() => {
    void refreshHypotheses()
  }, [refreshHypotheses])

  const availableOrigins = useMemo(() => {
    const values = new Set<string>()
    for (const hypothesis of state.hypotheses) {
      values.add(hypothesis.origin)
    }
    return Array.from(values).sort((left, right) => left.localeCompare(right))
  }, [state.hypotheses])

  const filteredHypotheses = useMemo(
    () =>
      filterHypotheses(
        state.hypotheses,
        state.originFilter,
        state.statusFilter,
        state.certaintyFilter,
      ),
    [state.certaintyFilter, state.hypotheses, state.originFilter, state.statusFilter],
  )

  function changeStatement(value: string): void {
    setState((previous) => ({ ...previous, statement: value }))
  }

  function changeRationale(value: string): void {
    setState((previous) => ({ ...previous, rationale: value }))
  }

  function changeSeedInput(value: string): void {
    setState((previous) => ({ ...previous, seedInput: value }))
  }

  function changeOriginFilter(value: string): void {
    setState((previous) => ({ ...previous, originFilter: value }))
  }

  function changeStatusFilter(value: string): void {
    setState((previous) => ({ ...previous, statusFilter: value }))
  }

  function changeCertaintyFilter(value: string): void {
    setState((previous) => ({ ...previous, certaintyFilter: value }))
  }

  async function submitManualHypothesis(): Promise<void> {
    if (!canEdit) {
      toast.error('You do not have permission to create hypotheses.')
      setState((previous) => ({
        ...previous,
        feedbackMessage: 'You do not have permission to create hypotheses.',
        feedbackTone: 'error',
      }))
      return
    }
    setState((previous) => ({ ...previous, isSubmitting: true }))
    const result = await createManualHypothesisAction(spaceId, {
      statement: state.statement,
      rationale: state.rationale,
      seedEntityIds: normalizeSeedIds(state.seedInput),
      sourceType: 'manual',
    })
    setState((previous) => ({ ...previous, isSubmitting: false }))

    if (!result.success) {
      toast.error(result.error)
      setState((previous) => ({
        ...previous,
        feedbackMessage: result.error,
        feedbackTone: 'error',
      }))
      return
    }

    toast.success(`Hypothesis logged (${result.data.claim_id.slice(0, 8)}...).`)
    setState((previous) => ({
      ...previous,
      statement: '',
      rationale: '',
      feedbackMessage: `Hypothesis logged (${result.data.claim_id.slice(0, 8)}...).`,
      feedbackTone: 'success',
    }))
    await refreshHypotheses()
  }

  async function runAutoGeneration(): Promise<void> {
    if (!canEdit) {
      toast.error('You do not have permission to auto-generate hypotheses.')
      setState((previous) => ({
        ...previous,
        feedbackMessage: 'You do not have permission to auto-generate hypotheses.',
        feedbackTone: 'error',
      }))
      return
    }
    if (!autoGenerationEnabled) {
      toast.error('Auto-generation is disabled for this environment.')
      setState((previous) => ({
        ...previous,
        feedbackMessage: 'Auto-generation is disabled for this environment.',
        feedbackTone: 'error',
      }))
      return
    }

    const seedEntityIds = normalizeSeedIds(state.seedInput)
    setState((previous) => ({ ...previous, isGenerating: true }))
    const result = await generateHypothesesAction(spaceId, {
      seed_entity_ids: seedEntityIds.length > 0 ? seedEntityIds : null,
      source_type: 'pubmed',
      max_depth: 2,
      max_hypotheses: 20,
    })
    setState((previous) => ({ ...previous, isGenerating: false }))

    if (!result.success) {
      toast.error(result.error)
      setState((previous) => ({
        ...previous,
        feedbackMessage: result.error,
        feedbackTone: 'error',
      }))
      return
    }

    const feedback = buildHypothesisGenerationFeedback(result.data)
    const message =
      feedback.details.length > 0
        ? `${feedback.summary}\n${feedback.details.map((detail) => `- ${detail}`).join('\n')}`
        : feedback.summary

    setState((previous) => ({
      ...previous,
      lastGeneration: result.data,
      feedbackMessage: message,
      feedbackTone: feedback.tone,
    }))

    if (feedback.tone === 'error') {
      toast.error(feedback.summary)
    } else {
      toast.success(feedback.summary)
    }
    await refreshHypotheses()
  }

  async function triageHypothesis(
    hypothesis: HypothesisResponse,
    nextStatus: HypothesisClaimStatus,
  ): Promise<void> {
    if (!canEdit) {
      toast.error('You do not have permission to triage hypotheses.')
      setState((previous) => ({
        ...previous,
        feedbackMessage: 'You do not have permission to triage hypotheses.',
        feedbackTone: 'error',
      }))
      return
    }

    setState((previous) => ({ ...previous, pendingClaimId: hypothesis.claim_id }))
    const result = await updateRelationClaimStatusAction(
      spaceId,
      hypothesis.claim_id,
      nextStatus,
    )
    setState((previous) => ({ ...previous, pendingClaimId: null }))

    if (!result.success) {
      toast.error(result.error)
      setState((previous) => ({
        ...previous,
        feedbackMessage: result.error,
        feedbackTone: 'error',
      }))
      return
    }

    toast.success(`Hypothesis moved to ${humanizeToken(nextStatus)}.`)
    setState((previous) => ({
      ...previous,
      feedbackMessage: `Hypothesis moved to ${humanizeToken(nextStatus)}.`,
      feedbackTone: 'success',
    }))
    await refreshHypotheses()
  }

  return {
    hypotheses: state.hypotheses,
    filteredHypotheses,
    availableOrigins,
    statement: state.statement,
    rationale: state.rationale,
    seedInput: state.seedInput,
    originFilter: state.originFilter,
    statusFilter: state.statusFilter,
    certaintyFilter: state.certaintyFilter,
    isLoading: state.isLoading,
    isSubmitting: state.isSubmitting,
    isGenerating: state.isGenerating,
    pendingClaimId: state.pendingClaimId,
    lastGeneration: state.lastGeneration,
    error: state.error,
    feedbackMessage: state.feedbackMessage,
    feedbackTone: state.feedbackTone,
    changeStatement,
    changeRationale,
    changeSeedInput,
    changeOriginFilter,
    changeStatusFilter,
    changeCertaintyFilter,
    refreshHypotheses,
    submitManualHypothesis,
    runAutoGeneration,
    triageHypothesis,
  }
}
