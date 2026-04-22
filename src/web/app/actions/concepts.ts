'use server'

import { revalidatePath } from 'next/cache'

import {
  createSpaceConceptAlias,
  createSpaceConceptMember,
  createSpaceConceptSet,
  proposeSpaceConceptDecision,
  setSpaceConceptDecisionStatus,
  upsertSpaceConceptPolicy,
} from '@/lib/api/concepts'
import type {
  ConceptAliasCreateRequest,
  ConceptAliasResponse,
  ConceptDecisionProposeRequest,
  ConceptDecisionResponse,
  ConceptDecisionStatusRequest,
  ConceptMemberCreateRequest,
  ConceptMemberResponse,
  ConceptPolicyResponse,
  ConceptPolicyUpsertRequest,
  ConceptSetCreateRequest,
  ConceptSetResponse,
} from '@/types/concepts'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateConceptPaths(spaceId: string): void {
  revalidatePath(`/spaces/${spaceId}`)
  revalidatePath(`/spaces/${spaceId}/concepts`)
  revalidatePath(`/spaces/${spaceId}/settings`)
}

export async function createConceptSetAction(
  spaceId: string,
  payload: ConceptSetCreateRequest,
): Promise<ActionResult<ConceptSetResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await createSpaceConceptSet(spaceId, payload, token)
    revalidateConceptPaths(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createConceptSetAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create concept set'),
    }
  }
}

export async function createConceptMemberAction(
  spaceId: string,
  payload: ConceptMemberCreateRequest,
): Promise<ActionResult<ConceptMemberResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await createSpaceConceptMember(spaceId, payload, token)
    revalidateConceptPaths(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createConceptMemberAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create concept member'),
    }
  }
}

export async function createConceptAliasAction(
  spaceId: string,
  payload: ConceptAliasCreateRequest,
): Promise<ActionResult<ConceptAliasResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await createSpaceConceptAlias(spaceId, payload, token)
    revalidateConceptPaths(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createConceptAliasAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create concept alias'),
    }
  }
}

export async function upsertConceptPolicyAction(
  spaceId: string,
  payload: ConceptPolicyUpsertRequest,
): Promise<ActionResult<ConceptPolicyResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await upsertSpaceConceptPolicy(spaceId, payload, token)
    revalidateConceptPaths(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] upsertConceptPolicyAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update concept policy'),
    }
  }
}

export async function proposeConceptDecisionAction(
  spaceId: string,
  payload: ConceptDecisionProposeRequest,
): Promise<ActionResult<ConceptDecisionResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await proposeSpaceConceptDecision(spaceId, payload, token)
    revalidateConceptPaths(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] proposeConceptDecisionAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to propose concept decision'),
    }
  }
}

export async function setConceptDecisionStatusAction(
  spaceId: string,
  decisionId: string,
  payload: ConceptDecisionStatusRequest,
): Promise<ActionResult<ConceptDecisionResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await setSpaceConceptDecisionStatus(spaceId, decisionId, payload, token)
    revalidateConceptPaths(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] setConceptDecisionStatusAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update decision status'),
    }
  }
}
