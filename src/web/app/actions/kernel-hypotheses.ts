'use server'

import { revalidatePath } from 'next/cache'

import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'
import { generateHypotheses } from '@/lib/api/artana-evidence-api'
import {
  createManualHypothesis,
  fetchHypotheses,
} from '@/lib/api/kernel'
import type {
  GenerateHypothesesRequest,
  GenerateHypothesesResponse,
  HypothesisResponse,
} from '@/types/kernel'

import { type ActionResult, revalidateHybridPaths } from './kernel-hybrid-shared'

function revalidateHypothesisViews(spaceId: string): void {
  revalidateHybridPaths(spaceId)
  revalidatePath(`/spaces/${spaceId}/curation`)
}

export async function listHypothesesAction(
  spaceId: string,
): Promise<ActionResult<HypothesisResponse[]>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchHypotheses(spaceId, { limit: 200, offset: 0 }, token)
    return { success: true, data: response.hypotheses }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] listHypothesesAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load hypotheses'),
    }
  }
}

export interface ManualHypothesisInput {
  statement: string
  rationale: string
  seedEntityIds?: string[]
  sourceType?: string
}

export async function createManualHypothesisAction(
  spaceId: string,
  payload: ManualHypothesisInput,
): Promise<ActionResult<HypothesisResponse>> {
  const statement = payload.statement.trim()
  const rationale = payload.rationale.trim()
  if (statement.length === 0 || rationale.length === 0) {
    return {
      success: false,
      error: 'Hypothesis statement and rationale are required.',
    }
  }

  try {
    const token = await requireAccessToken()
    const response = await createManualHypothesis(
      spaceId,
      {
        statement,
        rationale,
        seed_entity_ids: payload.seedEntityIds ?? [],
        source_type: payload.sourceType ?? 'manual',
      },
      token,
    )
    revalidateHypothesisViews(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createManualHypothesisAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to log hypothesis'),
    }
  }
}

export async function generateHypothesesAction(
  spaceId: string,
  payload: GenerateHypothesesRequest,
): Promise<ActionResult<GenerateHypothesesResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await generateHypotheses(
      spaceId,
      payload,
      token,
    )
    revalidateHypothesisViews(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] generateHypothesesAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to auto-generate hypotheses'),
    }
  }
}
