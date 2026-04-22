import { useCallback, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { listClaimsByEntityAction } from '@/app/actions/kernel-claim-relations'
import type { ClaimRelationResponse, RelationClaimResponse } from '@/types/kernel'

import type { ReviewStatusFilter } from './claim-overlay-toolbar'

interface TraversalEdge {
  nextClaimId: string
  relationId: string
}

interface TraversalPath {
  claimIds: string[]
  relationIds: string[]
}

interface UseClaimOverlayFocusPathArgs {
  spaceId: string
  relations: ClaimRelationResponse[]
  reviewFilter: ReviewStatusFilter
}

interface UseClaimOverlayFocusPathResult {
  focusSourceEntityId: string
  focusTargetEntityId: string
  focusedClaimIds: string[]
  focusedRelationIds: string[]
  focusSummary: string | null
  isPathFinding: boolean
  setFocusSourceEntityId: (value: string) => void
  setFocusTargetEntityId: (value: string) => void
  findFocusPath: () => Promise<void>
  clearFocusPath: () => void
}

function toClaimIdSet(claims: RelationClaimResponse[]): Set<string> {
  return new Set(
    claims
      .map((claim) => claim.id.trim())
      .filter((claimId) => claimId.length > 0),
  )
}

function buildClaimTraversalIndex(
  relations: ClaimRelationResponse[],
): Record<string, TraversalEdge[]> {
  const index: Record<string, TraversalEdge[]> = {}
  for (const relation of relations) {
    const source = relation.source_claim_id
    const target = relation.target_claim_id
    if (!index[source]) {
      index[source] = []
    }
    if (!index[target]) {
      index[target] = []
    }
    index[source].push({ nextClaimId: target, relationId: relation.id })
    index[target].push({ nextClaimId: source, relationId: relation.id })
  }
  return index
}

function findShortestTraversalPath({
  relations,
  sourceClaimIds,
  targetClaimIds,
}: {
  relations: ClaimRelationResponse[]
  sourceClaimIds: Set<string>
  targetClaimIds: Set<string>
}): TraversalPath | null {
  if (sourceClaimIds.size === 0 || targetClaimIds.size === 0) {
    return null
  }
  for (const sourceClaimId of sourceClaimIds) {
    if (targetClaimIds.has(sourceClaimId)) {
      return { claimIds: [sourceClaimId], relationIds: [] }
    }
  }
  const adjacency = buildClaimTraversalIndex(relations)
  const queue: string[] = []
  const parentClaimById: Record<string, string | null> = {}
  const parentRelationByClaimId: Record<string, string> = {}
  const visited = new Set<string>()
  for (const sourceClaimId of sourceClaimIds) {
    queue.push(sourceClaimId)
    visited.add(sourceClaimId)
    parentClaimById[sourceClaimId] = null
  }

  let targetHit: string | null = null
  let offset = 0
  while (offset < queue.length && targetHit === null) {
    const current = queue[offset]
    offset += 1
    const neighbors = adjacency[current] ?? []
    for (const neighbor of neighbors) {
      const nextClaimId = neighbor.nextClaimId
      if (visited.has(nextClaimId)) {
        continue
      }
      visited.add(nextClaimId)
      parentClaimById[nextClaimId] = current
      parentRelationByClaimId[nextClaimId] = neighbor.relationId
      if (targetClaimIds.has(nextClaimId)) {
        targetHit = nextClaimId
        break
      }
      queue.push(nextClaimId)
    }
  }
  if (targetHit === null) {
    return null
  }

  const claimIds: string[] = []
  const relationIds: string[] = []
  let cursor: string | null = targetHit
  while (cursor !== null) {
    claimIds.push(cursor)
    const relationId = parentRelationByClaimId[cursor]
    if (typeof relationId === 'string' && relationId.trim().length > 0) {
      relationIds.push(relationId)
    }
    cursor = parentClaimById[cursor] ?? null
  }

  claimIds.reverse()
  relationIds.reverse()
  return { claimIds, relationIds }
}

export function compactId(value: string): string {
  if (value.length <= 18) {
    return value
  }
  return `${value.slice(0, 8)}...${value.slice(-6)}`
}

export function useClaimOverlayFocusPath({
  spaceId,
  relations,
  reviewFilter,
}: UseClaimOverlayFocusPathArgs): UseClaimOverlayFocusPathResult {
  const [focusSourceEntityId, setFocusSourceEntityId] = useState('')
  const [focusTargetEntityId, setFocusTargetEntityId] = useState('')
  const [focusedClaimIds, setFocusedClaimIds] = useState<string[]>([])
  const [focusedRelationIds, setFocusedRelationIds] = useState<string[]>([])
  const [focusSummary, setFocusSummary] = useState<string | null>(null)
  const [isPathFinding, setIsPathFinding] = useState(false)

  const traversalRelations = useMemo(
    () =>
      reviewFilter === 'ALL'
        ? relations
        : relations.filter((relation) => relation.review_status === reviewFilter),
    [relations, reviewFilter],
  )

  const clearFocusPath = useCallback((): void => {
    setFocusedClaimIds([])
    setFocusedRelationIds([])
    setFocusSummary(null)
  }, [])

  const findFocusPath = useCallback(async (): Promise<void> => {
    const sourceEntityId = focusSourceEntityId.trim()
    const targetEntityId = focusTargetEntityId.trim()
    if (sourceEntityId.length === 0 || targetEntityId.length === 0) {
      toast.error('Enter both source and target entity IDs to find a path.')
      return
    }
    if (sourceEntityId === targetEntityId) {
      toast.error('Source and target entity IDs must be different.')
      return
    }

    setIsPathFinding(true)
    setFocusSummary(null)
    const [sourceClaimsResult, targetClaimsResult] = await Promise.all([
      listClaimsByEntityAction(spaceId, sourceEntityId, { offset: 0, limit: 200 }),
      listClaimsByEntityAction(spaceId, targetEntityId, { offset: 0, limit: 200 }),
    ])
    setIsPathFinding(false)

    if (!sourceClaimsResult.success) {
      clearFocusPath()
      setFocusSummary(sourceClaimsResult.error)
      toast.error(sourceClaimsResult.error)
      return
    }
    if (!targetClaimsResult.success) {
      clearFocusPath()
      setFocusSummary(targetClaimsResult.error)
      toast.error(targetClaimsResult.error)
      return
    }

    const sourceClaimIds = toClaimIdSet(sourceClaimsResult.data.claims)
    const targetClaimIds = toClaimIdSet(targetClaimsResult.data.claims)
    if (sourceClaimIds.size === 0 || targetClaimIds.size === 0) {
      clearFocusPath()
      setFocusSummary('No claim endpoints were found for one or both entities.')
      return
    }

    const traversalPath = findShortestTraversalPath({
      relations: traversalRelations,
      sourceClaimIds,
      targetClaimIds,
    })
    if (traversalPath === null) {
      clearFocusPath()
      setFocusSummary('No claim path found with the current overlay review filter.')
      return
    }

    setFocusedClaimIds(traversalPath.claimIds)
    setFocusedRelationIds(traversalPath.relationIds)
    setFocusSummary(
      `Focused path with ${traversalPath.claimIds.length} claims across ${traversalPath.relationIds.length} links.`,
    )
  }, [
    clearFocusPath,
    focusSourceEntityId,
    focusTargetEntityId,
    spaceId,
    traversalRelations,
  ])

  return {
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
  }
}
