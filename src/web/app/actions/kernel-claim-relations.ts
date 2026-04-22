'use server'

import { revalidatePath } from 'next/cache'

import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'
import {
  createClaimRelation,
  fetchClaimsByEntity,
  fetchClaimParticipants,
  fetchClaimParticipantCoverage,
  fetchClaimRelations,
  runClaimParticipantBackfill,
  updateClaimRelationReview,
  type ClaimRelationListParams,
} from '@/lib/api/kernel'
import type {
  ClaimParticipantBackfillResponse,
  ClaimParticipantCoverageResponse,
  ClaimParticipantResponse,
  ClaimRelationCreateRequest,
  ClaimRelationResponse,
  ClaimRelationReviewStatus,
  RelationClaimListResponse,
} from '@/types/kernel'

import { type ActionResult, revalidateHybridPaths } from './kernel-hybrid-shared'

function revalidateClaimRelationViews(spaceId: string): void {
  revalidateHybridPaths(spaceId)
  revalidatePath(`/spaces/${spaceId}/curation`)
}

export async function listClaimRelationsAction(
  spaceId: string,
  params: ClaimRelationListParams = { offset: 0, limit: 100 },
): Promise<ActionResult<ClaimRelationResponse[]>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchClaimRelations(spaceId, params, token)
    return { success: true, data: response.claim_relations }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] listClaimRelationsAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load claim relations'),
    }
  }
}

export async function createClaimRelationAction(
  spaceId: string,
  payload: ClaimRelationCreateRequest,
): Promise<ActionResult<ClaimRelationResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await createClaimRelation(spaceId, payload, token)
    revalidateClaimRelationViews(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createClaimRelationAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create claim relation'),
    }
  }
}

export async function updateClaimRelationReviewAction(
  spaceId: string,
  relationId: string,
  reviewStatus: ClaimRelationReviewStatus,
): Promise<ActionResult<ClaimRelationResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await updateClaimRelationReview(
      spaceId,
      relationId,
      { review_status: reviewStatus },
      token,
    )
    revalidateClaimRelationViews(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateClaimRelationReviewAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update claim relation status'),
    }
  }
}

export async function listClaimParticipantsAction(
  spaceId: string,
  claimId: string,
): Promise<ActionResult<ClaimParticipantResponse[]>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchClaimParticipants(spaceId, claimId, token)
    return { success: true, data: response.participants }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] listClaimParticipantsAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load claim participants'),
    }
  }
}

export async function listClaimsByEntityAction(
  spaceId: string,
  entityId: string,
  params: { offset?: number; limit?: number } = {},
): Promise<ActionResult<RelationClaimListResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchClaimsByEntity(spaceId, entityId, params, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] listClaimsByEntityAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load claims for entity'),
    }
  }
}

export async function getClaimParticipantCoverageAction(
  spaceId: string,
): Promise<ActionResult<ClaimParticipantCoverageResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchClaimParticipantCoverage(spaceId, { limit: 500, offset: 0 }, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] getClaimParticipantCoverageAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load participant coverage'),
    }
  }
}

export async function runClaimParticipantBackfillAction(
  spaceId: string,
  dryRun: boolean,
): Promise<ActionResult<ClaimParticipantBackfillResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await runClaimParticipantBackfill(
      spaceId,
      { dry_run: dryRun, limit: 1000, offset: 0 },
      token,
    )
    revalidateClaimRelationViews(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] runClaimParticipantBackfillAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to run participant backfill'),
    }
  }
}
