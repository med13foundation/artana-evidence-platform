import { revalidatePath } from 'next/cache'

import { fetchKernelEntities } from '@/lib/api/kernel'
import type { ConceptDecisionType } from '@/types/concepts'
import type { JSONObject } from '@/types/generated'
import type { KernelEntityResponse } from '@/types/kernel'

export type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

export type NearDuplicateAction = 'MERGE' | 'LINK_AS_RELATED' | 'NOT_DUPLICATE' | 'SNOOZE'
export type EdgeSuggestionAction = 'ACCEPT_AS_DRAFT' | 'REJECT' | 'SNOOZE'

export interface NearDuplicateDecisionInput {
  sourceEntityId: string
  targetEntityId: string
  sourceEntityType: string
  targetEntityType: string
  similarityScore: number
  vectorScore: number
  graphOverlapScore: number
  sharedIdentifierCount: number
  provenanceOverlapCount: number
  reason: string
  action: NearDuplicateAction
}

export interface EdgeSuggestionDecisionInput {
  sourceEntityId: string
  targetEntityId: string
  relationType: string
  sourceEntityType: string
  targetEntityType: string
  finalScore: number
  vectorScore: number
  graphOverlapScore: number
  relationPriorScore: number
  reason: string
  action: EdgeSuggestionAction
}

export interface NearDuplicateCandidate {
  source_entity_id: string
  source_display_label: string
  source_entity_type: string
  target_entity_id: string
  target_display_label: string
  target_entity_type: string
  similarity_score: number
  vector_score: number
  graph_overlap_score: number
  shared_neighbor_count: number
  shared_identifier_count: number
  provenance_overlap_count: number
  plausible_message: string
  risk_note: string
}

export interface EdgeSuggestionCandidate {
  source_entity_id: string
  source_display_label: string
  source_entity_type: string
  target_entity_id: string
  target_display_label: string
  target_entity_type: string
  relation_type: string
  final_score: number
  vector_score: number
  graph_overlap_score: number
  relation_prior_score: number
  plausible_message: string
  risk_note: string
}

export function revalidateHybridPaths(spaceId: string): void {
  revalidatePath(`/spaces/${spaceId}/concepts`)
  revalidatePath(`/spaces/${spaceId}/curation`)
  revalidatePath(`/spaces/${spaceId}/knowledge-graph`)
  revalidatePath('/admin/dictionary')
}

export function normalizeLabel(label: string | null | undefined, fallbackId: string): string {
  const trimmed = typeof label === 'string' ? label.trim() : ''
  return trimmed.length > 0 ? trimmed : `Entity ${fallbackId.slice(0, 8)}`
}

export function normalizeForAlias(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '')
}

export function toJsonObject(value: unknown): JSONObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return {}
  }
  return value as JSONObject
}

export function extractTokenSet(metadata: JSONObject, keys: string[]): Set<string> {
  const tokens = new Set<string>()
  for (const key of keys) {
    const raw = metadata[key]
    if (typeof raw === 'string' && raw.trim().length > 0) {
      tokens.add(raw.trim().toLowerCase())
      continue
    }
    if (Array.isArray(raw)) {
      for (const entry of raw) {
        if (typeof entry === 'string' && entry.trim().length > 0) {
          tokens.add(entry.trim().toLowerCase())
        }
      }
      continue
    }
    if (typeof raw === 'object' && raw !== null && !Array.isArray(raw)) {
      for (const [entryKey, entryValue] of Object.entries(raw)) {
        if (typeof entryValue === 'string' && entryValue.trim().length > 0) {
          tokens.add(`${entryKey}:${entryValue.trim().toLowerCase()}`)
        }
      }
    }
  }
  return tokens
}

export function intersectionCount(left: Set<string>, right: Set<string>): number {
  if (left.size === 0 || right.size === 0) {
    return 0
  }
  let count = 0
  for (const value of left) {
    if (right.has(value)) {
      count += 1
    }
  }
  return count
}

export function decisionTypeForNearDuplicate(action: NearDuplicateAction): ConceptDecisionType {
  if (action === 'MERGE') return 'MERGE'
  if (action === 'LINK_AS_RELATED') return 'LINK'
  if (action === 'NOT_DUPLICATE') return 'SPLIT'
  return 'DEMOTE'
}

export function decisionTypeForEdge(action: EdgeSuggestionAction): ConceptDecisionType {
  if (action === 'ACCEPT_AS_DRAFT') return 'PROMOTE'
  return 'DEMOTE'
}

export async function fetchEntityIndex(
  spaceId: string,
  entityIds: string[],
  token: string,
): Promise<Map<string, KernelEntityResponse>> {
  if (entityIds.length === 0) {
    return new Map()
  }
  const response = await fetchKernelEntities(
    spaceId,
    {
      ids: entityIds,
      offset: 0,
      limit: Math.min(entityIds.length, 100),
    },
    token,
  )
  const index = new Map<string, KernelEntityResponse>()
  for (const entity of response.entities) {
    index.set(entity.id, entity)
  }
  return index
}
