import type { JSONObject } from '@/types/generated'

export type KernelDataType =
  | 'INTEGER'
  | 'FLOAT'
  | 'STRING'
  | 'DATE'
  | 'CODED'
  | 'BOOLEAN'
  | 'JSON'

export type KernelSensitivity = 'PUBLIC' | 'INTERNAL' | 'PHI'
export type KernelReviewStatus = 'ACTIVE' | 'PENDING_REVIEW' | 'REVOKED'

export interface VariableDefinitionCreateRequest {
  id: string
  canonical_name: string
  display_name: string
  data_type: KernelDataType
  domain_context?: string
  sensitivity?: KernelSensitivity
  preferred_unit?: string | null
  constraints?: JSONObject
  description?: string | null
}

export interface VariableDefinitionResponse {
  id: string
  canonical_name: string
  display_name: string
  data_type: KernelDataType
  preferred_unit: string | null
  constraints: JSONObject
  domain_context: string
  sensitivity: KernelSensitivity
  description: string | null
  created_by: string
  is_active: boolean
  valid_from: string | null
  valid_to: string | null
  superseded_by: string | null
  source_ref: string | null
  review_status: KernelReviewStatus
  reviewed_by: string | null
  reviewed_at: string | null
  revocation_reason: string | null
  created_at: string
  updated_at: string
}

export interface VariableDefinitionListResponse {
  variables: VariableDefinitionResponse[]
  total: number
}

export interface TransformRegistryResponse {
  id: string
  input_unit: string
  output_unit: string
  implementation_ref: string
  status: string
  created_at: string
  updated_at: string
}

export interface TransformRegistryListResponse {
  transforms: TransformRegistryResponse[]
  total: number
}

export interface EntityResolutionPolicyResponse {
  entity_type: string
  policy_strategy: string
  required_anchors: string[]
  auto_merge_threshold: number
  created_by: string
  is_active: boolean
  valid_from: string | null
  valid_to: string | null
  superseded_by: string | null
  source_ref: string | null
  review_status: KernelReviewStatus
  reviewed_by: string | null
  reviewed_at: string | null
  revocation_reason: string | null
  created_at: string
  updated_at: string
}

export interface EntityResolutionPolicyListResponse {
  policies: EntityResolutionPolicyResponse[]
  total: number
}

export interface RelationConstraintResponse {
  id: number
  source_type: string
  relation_type: string
  target_type: string
  is_allowed: boolean
  requires_evidence: boolean
  created_by: string
  is_active: boolean
  valid_from: string | null
  valid_to: string | null
  superseded_by: string | null
  source_ref: string | null
  review_status: KernelReviewStatus
  reviewed_by: string | null
  reviewed_at: string | null
  revocation_reason: string | null
  created_at: string
  updated_at: string
}

export interface RelationConstraintListResponse {
  constraints: RelationConstraintResponse[]
  total: number
}

export interface DictionaryEntityTypeResponse {
  id: string
  display_name: string
  description: string
  domain_context: string
  external_ontology_ref: string | null
  expected_properties: JSONObject
  created_by: string
  is_active: boolean
  valid_from: string | null
  valid_to: string | null
  superseded_by: string | null
  source_ref: string | null
  review_status: KernelReviewStatus
  reviewed_by: string | null
  reviewed_at: string | null
  revocation_reason: string | null
  created_at: string
  updated_at: string
}

export interface DictionaryEntityTypeListResponse {
  entity_types: DictionaryEntityTypeResponse[]
  total: number
}

export interface DictionaryRelationTypeResponse {
  id: string
  display_name: string
  description: string
  domain_context: string
  is_directional: boolean
  inverse_label: string | null
  created_by: string
  is_active: boolean
  valid_from: string | null
  valid_to: string | null
  superseded_by: string | null
  source_ref: string | null
  review_status: KernelReviewStatus
  reviewed_by: string | null
  reviewed_at: string | null
  revocation_reason: string | null
  created_at: string
  updated_at: string
}

export interface DictionaryRelationTypeListResponse {
  relation_types: DictionaryRelationTypeResponse[]
  total: number
}

export interface DictionaryMergeRequest {
  target_id: string
  reason: string
}

export interface DictionaryRevokeRequest {
  reason: string
}
