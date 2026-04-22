import type { JSONValue, JSONObject } from '@/types/generated'

export interface FactAssessment {
  support_band: 'INSUFFICIENT' | 'TENTATIVE' | 'SUPPORTED' | 'STRONG'
  grounding_level: 'SPAN' | 'SECTION' | 'DOCUMENT' | 'GENERATED' | 'GRAPH_INFERENCE'
  mapping_status: 'RESOLVED' | 'AMBIGUOUS' | 'NOT_APPLICABLE'
  speculation_level: 'DIRECT' | 'HEDGED' | 'HYPOTHETICAL' | 'NOT_APPLICABLE'
  confidence_rationale: string
}

export interface KernelEntityCreateRequest {
  entity_type: string
  display_label?: string | null
  aliases?: string[]
  metadata?: JSONObject
  identifiers?: Record<string, string>
}

export interface KernelEntityUpdateRequest {
  display_label?: string | null
  aliases?: string[] | null
  metadata?: JSONObject | null
  identifiers?: Record<string, string> | null
}

export interface KernelEntityResponse {
  id: string
  research_space_id: string
  entity_type: string
  display_label: string | null
  aliases: string[]
  metadata: JSONObject
  created_at: string
  updated_at: string
}

export interface KernelEntityUpsertResponse {
  entity: KernelEntityResponse
  created: boolean
}

export interface KernelEntityListResponse {
  entities: KernelEntityResponse[]
  total: number
  offset: number
  limit: number
}

export interface KernelEntitySimilarityScoreBreakdown {
  vector_score: number
  graph_overlap_score: number
}

export interface KernelEntitySimilarityResponse {
  entity_id: string
  entity_type: string
  display_label: string | null
  similarity_score: number
  score_breakdown: KernelEntitySimilarityScoreBreakdown
}

export interface KernelEntitySimilarityListResponse {
  source_entity_id: string
  results: KernelEntitySimilarityResponse[]
  total: number
  limit: number
  min_similarity: number
}

export interface KernelEntityEmbeddingRefreshRequest {
  entity_ids?: string[]
  limit?: number
  model_name?: string
  embedding_version?: number
}

export interface KernelEntityEmbeddingRefreshResponse {
  requested: number
  processed: number
  refreshed: number
  unchanged: number
  missing_entities: string[]
}

export interface KernelObservationCreateRequest {
  subject_id: string
  variable_id: string
  value: JSONValue
  unit?: string | null
  observed_at?: string | null
  provenance_id?: string | null
  confidence?: number
}

export interface KernelObservationResponse {
  id: string
  research_space_id: string
  subject_id: string
  variable_id: string

  value_numeric: number | null
  value_text: string | null
  value_date: string | null
  value_coded: string | null
  value_boolean: boolean | null
  value_json: JSONValue | null

  unit: string | null
  observed_at: string | null
  provenance_id: string | null
  confidence: number

  created_at: string
  updated_at: string
}

export interface KernelObservationListResponse {
  observations: KernelObservationResponse[]
  total: number
  offset: number
  limit: number
}

export interface KernelRelationCreateRequest {
  source_id: string
  relation_type: string
  target_id: string
  assessment: FactAssessment
  evidence_summary?: string | null
  evidence_sentence?: string | null
  evidence_sentence_source?: string | null
  evidence_sentence_confidence?: string | null
  evidence_sentence_rationale?: string | null
  evidence_tier?: string | null
  provenance_id?: string | null
  source_document_ref?: string | null
  metadata?: JSONObject
}

export interface KernelRelationCurationUpdateRequest {
  curation_status: string
}

export interface KernelRelationPaperLink {
  label: string
  url: string
  source: string
}

export interface KernelRelationResponse {
  id: string
  research_space_id: string
  source_claim_id?: string | null
  source_id: string
  relation_type: string
  target_id: string

  confidence?: number
  evidence_summary?: string | null
  evidence_sentence?: string | null
  evidence_sentence_source?: string | null
  evidence_sentence_confidence?: string | null
  evidence_sentence_rationale?: string | null
  paper_links?: KernelRelationPaperLink[]
  evidence_tier?: string | null
  aggregate_confidence?: number
  source_count?: number
  highest_evidence_tier?: string | null
  curation_status: string

  provenance_id: string | null
  reviewed_by: string | null
  reviewed_at: string | null

  created_at: string
  updated_at: string
}

export interface KernelRelationListResponse {
  relations: KernelRelationResponse[]
  total: number
  offset: number
  limit: number
}

export interface KernelRelationSuggestionRequest {
  source_entity_ids: string[]
  limit_per_source?: number
  min_score?: number
  allowed_relation_types?: string[]
  target_entity_types?: string[]
  exclude_existing_relations?: boolean
}

export interface KernelRelationSuggestionScoreBreakdown {
  vector_score: number
  graph_overlap_score: number
  relation_prior_score: number
}

export interface KernelRelationSuggestionConstraintCheck {
  passed: boolean
  source_entity_type: string
  relation_type: string
  target_entity_type: string
}

export interface KernelRelationSuggestionResponse {
  source_entity_id: string
  target_entity_id: string
  relation_type: string
  final_score: number
  score_breakdown: KernelRelationSuggestionScoreBreakdown
  constraint_check: KernelRelationSuggestionConstraintCheck
}

export interface KernelRelationSuggestionListResponse {
  suggestions: KernelRelationSuggestionResponse[]
  total: number
  limit_per_source: number
  min_score: number
}

export interface RelationClaimResponse {
  id: string
  research_space_id: string
  source_document_id: string | null
  source_document_ref?: string | null
  agent_run_id: string | null
  source_type: string
  relation_type: string
  target_type: string
  source_label: string | null
  target_label: string | null
  confidence: number
  validation_state: string
  validation_reason: string | null
  persistability: 'PERSISTABLE' | 'NON_PERSISTABLE'
  claim_status: 'OPEN' | 'NEEDS_MAPPING' | 'REJECTED' | 'RESOLVED'
  polarity: 'SUPPORT' | 'REFUTE' | 'UNCERTAIN' | 'HYPOTHESIS'
  claim_text: string | null
  claim_section: string | null
  linked_relation_id: string | null
  metadata: JSONObject
  triaged_by: string | null
  triaged_at: string | null
  created_at: string
  updated_at: string
}

export interface RelationClaimListResponse {
  claims: RelationClaimResponse[]
  total: number
  offset: number
  limit: number
}

export interface CreateManualHypothesisRequest {
  statement: string
  rationale: string
  seed_entity_ids?: string[]
  source_type?: string
}

export interface GenerateHypothesesRequest {
  seed_entity_ids?: string[] | null
  source_type?: string
  relation_types?: string[] | null
  max_depth?: number
  max_hypotheses?: number
  model_id?: string | null
}

export interface HypothesisResponse {
  claim_id: string
  polarity: 'HYPOTHESIS' | 'SUPPORT' | 'REFUTE' | 'UNCERTAIN'
  claim_status: 'OPEN' | 'NEEDS_MAPPING' | 'REJECTED' | 'RESOLVED'
  validation_state: string
  persistability: 'PERSISTABLE' | 'NON_PERSISTABLE'
  confidence: number
  source_label: string | null
  relation_type: string
  target_label: string | null
  claim_text: string | null
  linked_relation_id?: string | null
  origin: string
  seed_entity_ids: string[]
  supporting_provenance_ids: string[]
  reasoning_path_id?: string | null
  supporting_claim_ids: string[]
  direct_supporting_claim_ids?: string[]
  transferred_supporting_claim_ids?: string[]
  transferred_from_entities?: string[]
  transfer_basis?: string[]
  contradiction_claim_ids?: string[]
  explanation?: string | null
  path_confidence?: number | null
  path_length?: number | null
  created_at: string
  metadata: JSONObject
}

export interface HypothesisListResponse {
  hypotheses: HypothesisResponse[]
  total: number
  offset: number
  limit: number
}

export interface GenerateHypothesesResponse {
  run_id: string
  requested_seed_count: number
  used_seed_count: number
  candidates_seen: number
  created_count: number
  deduped_count: number
  errors: string[]
  hypotheses: HypothesisResponse[]
}

export type ClaimRelationType =
  | 'SUPPORTS'
  | 'CONTRADICTS'
  | 'REFINES'
  | 'CAUSES'
  | 'UPSTREAM_OF'
  | 'DOWNSTREAM_OF'
  | 'SAME_AS'
  | 'GENERALIZES'
  | 'INSTANCE_OF'

export type ClaimRelationReviewStatus = 'PROPOSED' | 'ACCEPTED' | 'REJECTED'

export interface ClaimRelationResponse {
  id: string
  research_space_id: string
  source_claim_id: string
  target_claim_id: string
  relation_type: ClaimRelationType
  agent_run_id: string | null
  source_document_id: string | null
  source_document_ref?: string | null
  confidence: number
  review_status: ClaimRelationReviewStatus
  evidence_summary: string | null
  metadata: JSONObject
  created_at: string
}

export interface ClaimRelationListResponse {
  claim_relations: ClaimRelationResponse[]
  total: number
  offset: number
  limit: number
}

export interface ClaimRelationCreateRequest {
  source_claim_id: string
  target_claim_id: string
  relation_type: ClaimRelationType
  agent_run_id?: string | null
  source_document_id?: string | null
  source_document_ref?: string | null
  assessment: FactAssessment
  review_status?: ClaimRelationReviewStatus
  evidence_summary?: string | null
  metadata?: JSONObject
}

export interface ClaimRelationReviewUpdateRequest {
  review_status: ClaimRelationReviewStatus
}

export type ClaimParticipantRole = 'SUBJECT' | 'OBJECT' | 'MODIFIER' | 'QUALIFIER' | 'CONTEXT' | 'OUTCOME'

export interface ClaimParticipantResponse {
  id: string
  claim_id: string
  research_space_id: string
  label: string | null
  entity_id: string | null
  role: ClaimParticipantRole
  position: number | null
  qualifiers: JSONObject
  created_at: string
}

export interface ClaimParticipantListResponse {
  claim_id: string
  participants: ClaimParticipantResponse[]
  total: number
}

export interface ClaimParticipantCoverageResponse {
  total_claims: number
  claims_with_any_participants: number
  claims_with_subject: number
  claims_with_object: number
  unresolved_subject_endpoints: number
  unresolved_object_endpoints: number
  unresolved_endpoint_rate: number
}

export interface ClaimParticipantBackfillRequest {
  dry_run: boolean
  limit?: number
  offset?: number
}

export interface ClaimParticipantBackfillResponse {
  operation_run_id: string
  scanned_claims: number
  created_participants: number
  skipped_existing: number
  unresolved_endpoints: number
  dry_run: boolean
}

export interface ClaimEvidenceResponse {
  id: string
  claim_id: string
  source_document_id: string | null
  source_document_ref?: string | null
  agent_run_id: string | null
  sentence: string | null
  sentence_source: 'verbatim_span' | 'artana_generated' | null
  sentence_confidence: 'low' | 'medium' | 'high' | null
  sentence_rationale: string | null
  figure_reference: string | null
  table_reference: string | null
  confidence: number
  metadata: JSONObject
  paper_links?: KernelRelationPaperLink[]
  created_at: string
}

export interface ClaimEvidenceListResponse {
  claim_id: string
  evidence: ClaimEvidenceResponse[]
  total: number
}

export interface RelationConflictResponse {
  relation_id: string
  support_count: number
  refute_count: number
  support_claim_ids: string[]
  refute_claim_ids: string[]
}

export interface RelationConflictListResponse {
  conflicts: RelationConflictResponse[]
  total: number
  offset: number
  limit: number
}

export interface RelationClaimTriageRequest {
  claim_status: 'OPEN' | 'NEEDS_MAPPING' | 'REJECTED' | 'RESOLVED'
}

export interface KernelProvenanceResponse {
  id: string
  research_space_id: string
  source_type: string
  source_ref: string | null
  extraction_run_id: string | null
  mapping_method: string | null
  mapping_confidence: number | null
  agent_model: string | null
  raw_input: JSONObject | null
  created_at: string
  updated_at: string
}

export interface KernelProvenanceListResponse {
  provenance: KernelProvenanceResponse[]
  total: number
  offset: number
  limit: number
}

export interface KernelGraphExportResponse {
  nodes: KernelEntityResponse[]
  edges: KernelRelationResponse[]
}

export type KernelGraphSubgraphMode = 'starter' | 'seeded'

export interface KernelGraphSubgraphRequest {
  mode: KernelGraphSubgraphMode
  seed_entity_ids: string[]
  depth?: number
  top_k?: number
  relation_types?: string[] | null
  curation_statuses?: string[] | null
  max_nodes?: number
  max_edges?: number
}

export interface KernelGraphSubgraphMeta {
  mode: KernelGraphSubgraphMode
  seed_entity_ids: string[]
  requested_depth: number
  requested_top_k: number
  pre_cap_node_count: number
  pre_cap_edge_count: number
  truncated_nodes: boolean
  truncated_edges: boolean
}

export interface KernelGraphSubgraphResponse {
  nodes: KernelEntityResponse[]
  edges: KernelRelationResponse[]
  meta: KernelGraphSubgraphMeta
}

export type KernelGraphDocumentNodeKind = 'ENTITY' | 'CLAIM' | 'EVIDENCE'
export type KernelGraphDocumentEdgeKind = 'CANONICAL_RELATION' | 'CLAIM_PARTICIPANT' | 'CLAIM_EVIDENCE'

export interface KernelGraphDocumentRequest {
  mode: KernelGraphSubgraphMode
  seed_entity_ids: string[]
  depth?: number
  top_k?: number
  relation_types?: string[] | null
  curation_statuses?: string[] | null
  max_nodes?: number
  max_edges?: number
  include_claims?: boolean
  include_evidence?: boolean
  max_claims?: number
  evidence_limit_per_claim?: number
}

export interface KernelGraphDocumentNode {
  id: string
  resource_id: string
  kind: KernelGraphDocumentNodeKind
  type_label: string
  label: string
  confidence: number | null
  curation_status: string | null
  claim_status: string | null
  polarity: string | null
  canonical_relation_id: string | null
  metadata: JSONObject
  created_at: string
  updated_at: string
}

export interface KernelGraphDocumentEdge {
  id: string
  resource_id: string | null
  kind: KernelGraphDocumentEdgeKind
  source_id: string
  target_id: string
  type_label: string
  label: string
  confidence: number | null
  curation_status: string | null
  claim_id: string | null
  canonical_relation_id: string | null
  evidence_id: string | null
  metadata: JSONObject
  created_at: string
  updated_at: string
}

export interface KernelGraphDocumentCounts {
  entity_nodes: number
  claim_nodes: number
  evidence_nodes: number
  canonical_edges: number
  claim_participant_edges: number
  claim_evidence_edges: number
}

export interface KernelGraphDocumentMeta {
  mode: KernelGraphSubgraphMode
  seed_entity_ids: string[]
  requested_depth: number
  requested_top_k: number
  pre_cap_entity_node_count: number
  pre_cap_canonical_edge_count: number
  truncated_entity_nodes: boolean
  truncated_canonical_edges: boolean
  included_claims: boolean
  included_evidence: boolean
  max_claims: number
  evidence_limit_per_claim: number
  counts: KernelGraphDocumentCounts
}

export interface KernelGraphDocumentResponse {
  nodes: KernelGraphDocumentNode[]
  edges: KernelGraphDocumentEdge[]
  meta: KernelGraphDocumentMeta
}

export interface PipelineRunRequest {
  source_id: string
  run_id?: string | null
  resume_from_stage?: 'ingestion' | 'enrichment' | 'extraction' | 'graph' | null
  force_recover_lock?: boolean
  enrichment_limit?: number
  extraction_limit?: number
  source_type?: string | null
  model_id?: string | null
  shadow_mode?: boolean | null
  graph_seed_entity_ids?: string[] | null
  graph_max_depth?: number
  graph_relation_types?: string[] | null
}

export interface PipelineRunResponse {
  run_id: string
  source_id: string
  research_space_id: string
  accepted_at: string
  status: string
}

export interface PipelineRunCancelResponse {
  run_id: string
  source_id: string
  status: string
  cancelled: boolean
}

export interface SourcePipelineRunsResponse {
  source_id: string
  runs: JSONObject[]
  total: number
}

export interface ArtanaStageProgressSnapshot {
  stage: string
  run_id: string | null
  status: string | null
  percent: number | null
  current_stage: string | null
  completed_stages: string[]
  started_at: string | null
  updated_at: string | null
  eta_seconds: number | null
  candidate_run_ids: string[]
}

export interface SourceWorkflowMonitorResponse {
  source_snapshot: JSONObject
  last_run: JSONObject | null
  pipeline_runs: JSONObject[]
  documents: JSONObject[]
  paper_candidates?: JSONObject[]
  document_status_counts: Record<string, number>
  extraction_queue: JSONObject[]
  extraction_queue_status_counts: Record<string, number>
  publication_extractions: JSONObject[]
  publication_extraction_status_counts: Record<string, number>
  relation_review: JSONObject
  graph_summary: JSONObject | null
  operational_counters: JSONObject
  artana_progress?: Record<string, ArtanaStageProgressSnapshot>
  warnings: string[]
}

export type SourceWorkflowEventCategory = 'run' | 'stage' | 'document' | 'queue' | 'extraction' | 'review' | 'graph'

export interface SourceWorkflowEvent {
  event_id: string
  source_id: string
  run_id: string | null
  occurred_at: string
  category: SourceWorkflowEventCategory
  event_type?: string | null
  stage: string | null
  status: string | null
  level?: string | null
  scope_kind?: string | null
  scope_id?: string | null
  agent_kind?: string | null
  agent_run_id?: string | null
  error_code?: string | null
  message: string
  started_at?: string | null
  completed_at?: string | null
  duration_ms?: number | null
  queue_wait_ms?: number | null
  timeout_budget_ms?: number | null
  payload: JSONObject
}

export interface SourceWorkflowEventsResponse {
  source_id: string
  run_id: string | null
  generated_at: string
  events: SourceWorkflowEvent[]
  total: number
  has_more: boolean
}

export interface PipelineRunSummaryEnvelopeResponse {
  source_id: string
  run_id: string
  generated_at: string
  run: JSONObject
}

export interface SourceWorkflowDocumentTraceResponse {
  source_id: string
  run_id: string
  document_id: string
  generated_at: string
  document: JSONObject | null
  extraction_rows: JSONObject[]
  events: SourceWorkflowEvent[]
}

export interface SourceWorkflowQueryTraceResponse {
  source_id: string
  run_id: string
  generated_at: string
  base_query: string | null
  executed_query: string | null
  query_generation: JSONObject
  events: SourceWorkflowEvent[]
}

export interface PipelineRunTimingSummaryResponse {
  source_id: string
  run_id: string
  generated_at: string
  timing_summary: JSONObject
}

export interface PipelineRunCostSummaryResponse {
  source_id: string
  run_id: string
  generated_at: string
  cost_summary: JSONObject
}

export interface PipelineRunCostReportItem {
  run_id: string
  source_id: string
  research_space_id: string
  source_name: string | null
  source_type: string | null
  status: string | null
  run_owner_user_id: string | null
  run_owner_source: string | null
  started_at: string | null
  completed_at: string | null
  total_duration_ms: number | null
  total_cost_usd: number
  extracted_documents: number
  persisted_relations: number
}

export interface PipelineRunCostReportResponse {
  generated_at: string
  items: PipelineRunCostReportItem[]
  total: number
}

export interface PipelineRunComparisonResponse {
  source_id: string
  run_a_id: string
  run_b_id: string
  generated_at: string
  run_a: JSONObject
  run_b: JSONObject
  delta: JSONObject
}

export interface SourceWorkflowCardStatusPayload {
  active_pipeline_run_id?: string | null
  last_pipeline_status: string | null
  last_failed_stage: 'ingestion' | 'enrichment' | 'extraction' | 'graph' | null
  pending_paper_count: number
  pending_relation_review_count: number
  extraction_extracted_count: number
  extraction_failed_count: number
  extraction_skipped_count: number
  extraction_timeout_failed_count: number
  graph_edges_delta_last_run: number
  graph_edges_total: number
  artana_progress?: Record<string, ArtanaStageProgressSnapshot>
}

export interface WorkflowEventCardItem {
  event_id: string
  occurred_at: string | null
  category: string | null
  stage: string | null
  status: string | null
  message: string
}

export interface SourceWorkflowStreamBootstrapPayload {
  monitor: SourceWorkflowMonitorResponse
  events: SourceWorkflowEvent[]
  generated_at: string
  run_id: string | null
}

export interface SourceWorkflowStreamSnapshotPayload {
  monitor: SourceWorkflowMonitorResponse
  generated_at: string
  run_id: string | null
}

export interface SourceWorkflowStreamEventsPayload {
  events: SourceWorkflowEvent[]
  generated_at: string
  run_id: string | null
}

export interface SpaceWorkflowSourceCardPayload {
  source_id: string
  workflow_status: SourceWorkflowCardStatusPayload
  events: WorkflowEventCardItem[]
  generated_at: string
}

export interface SpaceWorkflowBootstrapPayload {
  sources: SpaceWorkflowSourceCardPayload[]
  generated_at: string
}

export interface GraphSearchRequest {
  question: string
  max_depth?: number
  top_k?: number
  curation_statuses?: string[] | null
  include_evidence_chains?: boolean
  force_agent?: boolean
}

export interface GraphSearchEvidenceItem {
  source_type: 'tool' | 'db' | 'paper' | 'web' | 'note' | 'api'
  locator: string
  excerpt: string
  relevance: number
}

export interface GraphSearchEvidenceChainItem {
  provenance_id: string | null
  relation_id: string | null
  observation_id: string | null
  evidence_tier: string | null
  confidence: number | null
  evidence_sentence: string | null
  source_ref: string | null
}

export interface GraphSearchResultEntry {
  entity_id: string
  entity_type: string
  display_label: string | null
  relevance_score: number
  matching_observation_ids: string[]
  matching_relation_ids: string[]
  evidence_chain: GraphSearchEvidenceChainItem[]
  explanation: string
  support_summary: string
}

export type GraphSearchDecision = 'generated' | 'fallback' | 'escalate'
export type GraphSearchExecutedPath = 'deterministic' | 'agent' | 'agent_fallback'

export interface GraphSearchResponse {
  confidence_score: number
  rationale: string
  evidence: GraphSearchEvidenceItem[]
  decision: GraphSearchDecision
  research_space_id: string
  original_query: string
  interpreted_intent: string
  query_plan_summary: string
  total_results: number
  results: GraphSearchResultEntry[]
  executed_path: GraphSearchExecutedPath
  warnings: string[]
  agent_run_id: string | null
}

export interface GraphConnectionDiscoverRequest {
  seed_entity_ids: string[]
  source_type?: string
  model_id?: string | null
  relation_types?: string[] | null
  max_depth?: number
  shadow_mode?: boolean | null
}

export interface GraphConnectionSingleRequest {
  source_type?: string
  model_id?: string | null
  relation_types?: string[] | null
  max_depth?: number
  shadow_mode?: boolean | null
}

export interface GraphConnectionOutcomeResponse {
  seed_entity_id: string
  research_space_id: string
  status: string
  reason: string
  review_required: boolean
  shadow_mode: boolean
  wrote_to_graph: boolean
  run_id: string | null
  proposed_relations_count: number
  persisted_relations_count: number
  rejected_candidates_count: number
  errors: string[]
}

export interface GraphConnectionDiscoverResponse {
  requested: number
  processed: number
  discovered: number
  failed: number
  review_required: number
  shadow_runs: number
  proposed_relations_count: number
  persisted_relations_count: number
  rejected_candidates_count: number
  errors: string[]
  outcomes: GraphConnectionOutcomeResponse[]
}

export type SpaceSourceRunStatus = 'completed' | 'skipped' | 'failed'

export interface SpaceSourceIngestionRunResponse {
  source_id: string
  source_name: string
  status: SpaceSourceRunStatus
  message?: string | null
  fetched_records: number
  parsed_publications: number
  created_publications: number
  updated_publications: number
  executed_query?: string | null
}

export interface SpaceRunActiveSourcesResponse {
  total_sources: number
  active_sources: number
  runnable_sources: number
  completed_sources: number
  skipped_sources: number
  failed_sources: number
  runs: SpaceSourceIngestionRunResponse[]
}
