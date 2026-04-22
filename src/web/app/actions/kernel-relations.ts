"use server"

import { revalidatePath } from 'next/cache'
import {
  fetchKernelEntities,
  updateKernelRelationCurationStatus,
  updateRelationClaimStatus,
} from '@/lib/api/kernel'
import type { KernelRelationResponse, RelationClaimResponse } from '@/types/kernel'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

export interface NodeSearchOption {
  id: string
  label: string
  entityType: string
}

export interface NodeSearchResult {
  options: NodeSearchOption[]
  hasMore: boolean
  nextOffset: number
}

function revalidateCuration(spaceId: string) {
  revalidatePath(`/spaces/${spaceId}/curation`)
  revalidatePath(`/spaces/${spaceId}/knowledge-graph`)
}

export async function updateKernelRelationStatusAction(
  spaceId: string,
  relationId: string,
  curationStatus: string,
): Promise<ActionResult<KernelRelationResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await updateKernelRelationCurationStatus(
      spaceId,
      relationId,
      { curation_status: curationStatus },
      token,
    )
    revalidateCuration(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateKernelRelationStatus failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update relation status'),
    }
  }
}

export async function updateRelationClaimStatusAction(
  spaceId: string,
  claimId: string,
  claimStatus: 'OPEN' | 'NEEDS_MAPPING' | 'REJECTED' | 'RESOLVED',
): Promise<ActionResult<RelationClaimResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await updateRelationClaimStatus(
      spaceId,
      claimId,
      { claim_status: claimStatus },
      token,
    )
    revalidateCuration(spaceId)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateRelationClaimStatus failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update relation claim status'),
    }
  }
}

export async function searchKernelRelationNodesAction(
  spaceId: string,
  query: string,
  offset = 0,
  limit = 40,
): Promise<ActionResult<NodeSearchResult>> {
  const trimmedQuery = query.trim()
  if (trimmedQuery.length < 2) {
    return {
      success: true,
      data: {
        options: [],
        hasMore: false,
        nextOffset: 0,
      },
    }
  }

  try {
    const token = await requireAccessToken()
    const response = await fetchKernelEntities(
      spaceId,
      {
        q: trimmedQuery,
        offset: Math.max(0, offset),
        limit: Math.max(1, Math.min(limit, 100)),
      },
      token,
    )
    const options: NodeSearchOption[] = response.entities.map((entity) => {
      const label =
        typeof entity.display_label === 'string' && entity.display_label.trim().length > 0
          ? entity.display_label.trim()
          : entity.entity_type
      return {
        id: entity.id,
        label,
        entityType: entity.entity_type,
      }
    })
    return {
      success: true,
      data: {
        options,
        hasMore: options.length >= Math.max(1, Math.min(limit, 100)),
        nextOffset: Math.max(0, offset) + options.length,
      },
    }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] searchKernelRelationNodesAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to search nodes'),
    }
  }
}
