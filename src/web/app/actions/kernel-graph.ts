'use server'

import { getActionErrorMessage, getActionErrorStatus, requireAccessToken } from '@/app/actions/action-utils'
import { searchKernelGraph } from '@/lib/api/artana-evidence-api'
import {
  fetchClaimParticipants,
  fetchKernelGraphDocument,
  fetchKernelGraphExport,
  fetchKernelNeighborhood,
  fetchKernelSubgraph,
  fetchRelationClaimEvidence,
  fetchRelationClaims,
  fetchRelationConflicts,
  type RelationClaimListParams,
  type RelationConflictListParams,
} from '@/lib/api/kernel'
import type {
  ClaimEvidenceListResponse,
  ClaimParticipantListResponse,
  GraphSearchRequest,
  GraphSearchResponse,
  KernelGraphDocumentRequest,
  KernelGraphDocumentResponse,
  KernelGraphExportResponse,
  KernelGraphSubgraphRequest,
  KernelGraphSubgraphResponse,
  RelationClaimListResponse,
  RelationConflictListResponse,
} from '@/types/kernel'

export type QueryActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string; status?: number }

export async function fetchKernelSubgraphAction(
  spaceId: string,
  payload: KernelGraphSubgraphRequest,
): Promise<QueryActionResult<KernelGraphSubgraphResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchKernelSubgraph(spaceId, payload, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchKernelSubgraphAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load graph subgraph'),
      status: getActionErrorStatus(error),
    }
  }
}

export async function fetchKernelGraphDocumentAction(
  spaceId: string,
  payload: KernelGraphDocumentRequest,
): Promise<QueryActionResult<KernelGraphDocumentResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchKernelGraphDocument(spaceId, payload, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchKernelGraphDocumentAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load graph document'),
      status: getActionErrorStatus(error),
    }
  }
}

export async function fetchRelationClaimsAction(
  spaceId: string,
  params: RelationClaimListParams = {},
): Promise<QueryActionResult<RelationClaimListResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchRelationClaims(spaceId, params, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchRelationClaimsAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load relation claims'),
      status: getActionErrorStatus(error),
    }
  }
}

export async function fetchClaimParticipantsAction(
  spaceId: string,
  claimId: string,
): Promise<QueryActionResult<ClaimParticipantListResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchClaimParticipants(spaceId, claimId, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchClaimParticipantsAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load claim participants'),
      status: getActionErrorStatus(error),
    }
  }
}

export async function fetchRelationConflictsAction(
  spaceId: string,
  params: RelationConflictListParams = {},
): Promise<QueryActionResult<RelationConflictListResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchRelationConflicts(spaceId, params, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchRelationConflictsAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load relation conflicts'),
      status: getActionErrorStatus(error),
    }
  }
}

export async function fetchKernelGraphExportAction(
  spaceId: string,
): Promise<QueryActionResult<KernelGraphExportResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchKernelGraphExport(spaceId, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchKernelGraphExportAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load graph export'),
      status: getActionErrorStatus(error),
    }
  }
}

export async function searchKernelGraphAction(
  spaceId: string,
  payload: GraphSearchRequest,
): Promise<QueryActionResult<GraphSearchResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await searchKernelGraph(spaceId, payload, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] searchKernelGraphAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to execute graph search'),
      status: getActionErrorStatus(error),
    }
  }
}

export async function fetchKernelNeighborhoodAction(
  spaceId: string,
  entityId: string,
  depth: number,
): Promise<QueryActionResult<KernelGraphExportResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchKernelNeighborhood(spaceId, entityId, depth, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchKernelNeighborhoodAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load graph neighborhood'),
      status: getActionErrorStatus(error),
    }
  }
}

export async function fetchRelationClaimEvidenceAction(
  spaceId: string,
  claimId: string,
): Promise<QueryActionResult<ClaimEvidenceListResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchRelationClaimEvidence(spaceId, claimId, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchRelationClaimEvidenceAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load claim evidence'),
      status: getActionErrorStatus(error),
    }
  }
}
