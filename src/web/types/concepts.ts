import type { JSONObject } from '@/types/generated'

export type ConceptReviewStatus = 'ACTIVE' | 'PENDING_REVIEW' | 'REVOKED'
export type ConceptPolicyMode = 'PRECISION' | 'BALANCED' | 'DISCOVERY'
export type ConceptDecisionType =
  | 'CREATE'
  | 'MAP'
  | 'MERGE'
  | 'SPLIT'
  | 'LINK'
  | 'PROMOTE'
  | 'DEMOTE'
export type ConceptDecisionStatus =
  | 'PROPOSED'
  | 'NEEDS_REVIEW'
  | 'APPROVED'
  | 'REJECTED'
  | 'APPLIED'
export type ConceptHarnessOutcome = 'PASS' | 'FAIL' | 'NEEDS_REVIEW'

export interface ConceptSetResponse {
  id: string
  research_space_id: string
  name: string
  slug: string
  domain_context: string
  description: string | null
  review_status: ConceptReviewStatus
  is_active: boolean
  created_by: string
  source_ref: string | null
  created_at: string
  updated_at: string
}

export interface ConceptSetListResponse {
  concept_sets: ConceptSetResponse[]
  total: number
}

export interface ConceptMemberResponse {
  id: string
  concept_set_id: string
  research_space_id: string
  domain_context: string
  canonical_label: string
  normalized_label: string
  sense_key: string
  dictionary_dimension: string | null
  dictionary_entry_id: string | null
  is_provisional: boolean
  metadata_payload: JSONObject
  review_status: ConceptReviewStatus
  is_active: boolean
  created_by: string
  source_ref: string | null
  created_at: string
  updated_at: string
}

export interface ConceptMemberListResponse {
  concept_members: ConceptMemberResponse[]
  total: number
}

export interface ConceptAliasResponse {
  id: number
  concept_member_id: string
  research_space_id: string
  domain_context: string
  alias_label: string
  alias_normalized: string
  source: string | null
  review_status: ConceptReviewStatus
  is_active: boolean
  created_by: string
  source_ref: string | null
  created_at: string
  updated_at: string
}

export interface ConceptAliasListResponse {
  concept_aliases: ConceptAliasResponse[]
  total: number
}

export interface ConceptPolicyResponse {
  id: string
  research_space_id: string
  profile_name: string
  mode: ConceptPolicyMode
  minimum_edge_confidence: number
  minimum_distinct_documents: number
  allow_generic_relations: boolean
  max_edges_per_document: number | null
  policy_payload: JSONObject
  is_active: boolean
  created_by: string
  source_ref: string | null
  created_at: string
  updated_at: string
}

export interface ConceptDecisionResponse {
  id: string
  research_space_id: string
  concept_set_id: string | null
  concept_member_id: string | null
  concept_link_id: string | null
  decision_type: ConceptDecisionType
  decision_status: ConceptDecisionStatus
  proposed_by: string
  decided_by: string | null
  confidence: number | null
  rationale: string | null
  evidence_payload: JSONObject
  decision_payload: JSONObject
  harness_outcome: ConceptHarnessOutcome | null
  decided_at: string | null
  created_at: string
  updated_at: string
}

export interface ConceptDecisionListResponse {
  concept_decisions: ConceptDecisionResponse[]
  total: number
}

export interface ConceptSetCreateRequest {
  name: string
  slug: string
  domain_context: string
  description?: string | null
  source_ref?: string | null
}

export interface ConceptMemberCreateRequest {
  concept_set_id: string
  domain_context: string
  canonical_label: string
  normalized_label: string
  sense_key?: string
  dictionary_dimension?: string | null
  dictionary_entry_id?: string | null
  is_provisional?: boolean
  metadata_payload?: JSONObject
  source_ref?: string | null
}

export interface ConceptAliasCreateRequest {
  concept_member_id: string
  domain_context: string
  alias_label: string
  alias_normalized: string
  source?: string | null
  source_ref?: string | null
}

export interface ConceptPolicyUpsertRequest {
  mode: ConceptPolicyMode
  minimum_edge_confidence?: number
  minimum_distinct_documents?: number
  allow_generic_relations?: boolean
  max_edges_per_document?: number | null
  policy_payload?: JSONObject
  source_ref?: string | null
}

export interface ConceptDecisionProposeRequest {
  decision_type: ConceptDecisionType
  decision_payload?: JSONObject
  evidence_payload?: JSONObject
  confidence?: number | null
  rationale?: string | null
  concept_set_id?: string | null
  concept_member_id?: string | null
  concept_link_id?: string | null
}

export interface ConceptDecisionStatusRequest {
  decision_status: ConceptDecisionStatus
}
