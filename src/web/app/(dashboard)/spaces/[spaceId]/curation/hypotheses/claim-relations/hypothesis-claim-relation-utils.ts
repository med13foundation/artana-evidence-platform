import type {
  ClaimRelationReviewStatus,
  ClaimRelationType,
  HypothesisResponse,
} from '@/types/kernel'

export const CLAIM_RELATION_TYPES: ClaimRelationType[] = [
  'SUPPORTS',
  'CONTRADICTS',
  'REFINES',
  'CAUSES',
  'UPSTREAM_OF',
  'DOWNSTREAM_OF',
  'SAME_AS',
  'GENERALIZES',
  'INSTANCE_OF',
]

export const CLAIM_RELATION_REVIEW_STATUSES: ClaimRelationReviewStatus[] = [
  'PROPOSED',
  'ACCEPTED',
  'REJECTED',
]

export type ClaimRelationReviewFilter = 'ALL' | ClaimRelationReviewStatus

export function summarizeHypothesis(hypothesis: HypothesisResponse): string {
  const source = hypothesis.source_label?.trim() || 'Unknown source'
  const target = hypothesis.target_label?.trim() || 'Unknown target'
  return `${source} -> ${hypothesis.relation_type} -> ${target}`
}

export function shortId(value: string): string {
  return `${value.slice(0, 8)}...`
}
