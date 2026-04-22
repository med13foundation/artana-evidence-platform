"""Service-local graph API contracts used by graph-harness."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import JSONObject, JSONValue
from .graph_fact_assessment import (
    FactAssessment,
    assessment_confidence,
)

DecisionValidationState = Literal[
    "VALID",
    "VALID_WITH_GRAPH_REPAIR",
    "REVIEW_REQUIRED",
    "INVALID",
]
DecisionEvidenceState = Literal[
    "ACCEPTED_DIRECT_EVIDENCE",
    "DIRECT_EVIDENCE_PRESENT",
    "EVIDENCE_LOCATOR_ONLY",
    "GENERATED_SUMMARY_ONLY",
    "REQUIRED_EVIDENCE_MISSING",
]
DecisionDuplicateConflictState = Literal[
    "CLEAR",
    "DUPLICATE_EXISTING",
    "POSSIBLE_DUPLICATE",
    "CONFLICTING_CLAIM",
]
DecisionSourceReliability = Literal[
    "CURATED",
    "TRUSTED_EXTERNAL",
    "USER_UPLOADED",
    "UNKNOWN",
    "AI_GENERATED_ONLY",
]
DecisionRiskTier = Literal["low", "medium", "high"]


class DecisionConfidenceAssessment(BaseModel):
    """Qualitative inputs the graph DB uses to score governed AI decisions."""

    model_config = ConfigDict(strict=False, extra="forbid")

    fact_assessment: FactAssessment
    validation_state: DecisionValidationState = "VALID"
    evidence_state: DecisionEvidenceState = "DIRECT_EVIDENCE_PRESENT"
    duplicate_conflict_state: DecisionDuplicateConflictState = "CLEAR"
    source_reliability: DecisionSourceReliability = "UNKNOWN"
    risk_tier: DecisionRiskTier = "low"
    rationale: str | None = Field(default=None, max_length=4000)


class DecisionConfidenceResult(BaseModel):
    """DB-computed policy confidence result."""

    model_config = ConfigDict(strict=True)

    confidence_model_version: str
    computed_confidence: float = Field(ge=0.0, le=1.0)
    cap_values: dict[str, float]
    blocking_reasons: list[str]
    human_review_reasons: list[str]


class KernelRelationPaperLinkResponse(BaseModel):
    """One source-paper link for relation evidence review."""

    model_config = ConfigDict(strict=True)

    label: str
    url: str
    source: str


class ClaimParticipantResponse(BaseModel):
    """Response model for one claim participant row."""

    model_config = ConfigDict(strict=True)

    id: UUID
    claim_id: UUID
    research_space_id: UUID
    label: str | None
    entity_id: UUID | None
    role: str
    position: int | None
    qualifiers: JSONObject
    created_at: datetime


class KernelEntityResponse(BaseModel):
    """Response model for one graph entity."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    entity_type: str
    display_label: str | None = None
    aliases: list[str] = Field(default_factory=list)
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


class KernelEntityListResponse(BaseModel):
    """List response for graph entities within a research space."""

    model_config = ConfigDict(strict=True)

    entities: list[KernelEntityResponse]
    total: int
    offset: int
    limit: int


class KernelObservationCreateRequest(BaseModel):
    """Request model for recording one graph observation."""

    model_config = ConfigDict(strict=False, extra="forbid")

    subject_id: UUID
    variable_id: str = Field(..., min_length=1, max_length=64)
    value: JSONValue
    unit: str | None = Field(default=None, max_length=64)
    observed_at: datetime | None = None
    provenance_id: UUID | None = None
    observation_origin: Literal["MANUAL", "IMPORTED", "AI_AUTHORED"] = "MANUAL"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class KernelObservationResponse(BaseModel):
    """Response model for one graph observation."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    subject_id: UUID
    variable_id: str
    value_numeric: float | None
    value_text: str | None
    value_date: datetime | None
    value_coded: str | None
    value_boolean: bool | None
    value_json: JSONValue | None
    unit: str | None
    observed_at: datetime | None
    provenance_id: UUID | None
    confidence: float
    created_at: datetime
    updated_at: datetime


class KernelObservationListResponse(BaseModel):
    """List response for observations in one graph space."""

    model_config = ConfigDict(strict=True)

    observations: list[KernelObservationResponse]
    total: int
    offset: int
    limit: int


class KernelEntityEmbeddingStatusResponse(BaseModel):
    """Per-entity readiness metadata for graph-owned embedding projections."""

    model_config = ConfigDict(strict=True)

    entity_id: UUID
    state: str = Field(min_length=1, max_length=16)
    desired_fingerprint: str = Field(min_length=64, max_length=64)
    embedding_model: str = Field(min_length=1, max_length=100)
    embedding_version: int = Field(ge=1)
    last_requested_at: datetime
    last_attempted_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    last_error_code: str | None = Field(default=None, max_length=64)
    last_error_message: str | None = Field(default=None, max_length=2000)


class KernelEntityEmbeddingStatusListResponse(BaseModel):
    """List response for graph-owned entity embedding readiness."""

    model_config = ConfigDict(strict=True)

    statuses: list[KernelEntityEmbeddingStatusResponse]
    total: int


class KernelEntityEmbeddingRefreshRequest(BaseModel):
    """Request payload for explicit entity embedding refresh operations."""

    model_config = ConfigDict(strict=False)

    entity_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=500)
    limit: int = Field(default=500, ge=1, le=5000)
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    embedding_version: int | None = Field(default=None, ge=1, le=1000)


class KernelEntityEmbeddingRefreshResponse(BaseModel):
    """Response summary for explicit embedding refresh operations."""

    model_config = ConfigDict(strict=True)

    requested: int
    processed: int
    refreshed: int
    unchanged: int
    failed: int
    missing_entities: list[str]


class ClaimParticipantListResponse(BaseModel):
    """List response for participants on one claim."""

    model_config = ConfigDict(strict=True)

    claim_id: UUID
    participants: list[ClaimParticipantResponse]
    total: int


class ClaimRelationResponse(BaseModel):
    """Response model for one claim-relation edge."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    source_claim_id: UUID
    target_claim_id: UUID
    relation_type: str
    agent_run_id: str | None
    source_document_id: UUID | None = None
    source_document_ref: str | None = None
    confidence: float
    review_status: str
    evidence_summary: str | None
    metadata: JSONObject
    created_at: datetime


class KernelGraphViewCountsResponse(BaseModel):
    """Count summary for one graph view payload."""

    model_config = ConfigDict(strict=True)

    canonical_relations: int
    claims: int
    claim_relations: int
    participants: int
    evidence: int


class ClaimAIProvenanceEnvelope(BaseModel):
    """Required audit metadata for AI-authored relation claims."""

    model_config = ConfigDict(strict=False, extra="forbid")

    model_id: str = Field(..., min_length=1, max_length=128)
    model_version: str = Field(..., min_length=1, max_length=128)
    prompt_id: str = Field(..., min_length=1, max_length=128)
    prompt_version: str = Field(..., min_length=1, max_length=128)
    input_hash: str = Field(..., min_length=1, max_length=128)
    rationale: str = Field(..., min_length=1, max_length=4000)
    evidence_references: list[str] = Field(default_factory=list, max_length=50)
    tool_trace_ref: str | None = Field(default=None, max_length=1024)


class KernelRelationClaimCreateRequest(BaseModel):
    """Request model for creating a relation claim without materializing it."""

    model_config = ConfigDict(strict=False, extra="forbid")

    source_entity_id: UUID
    target_entity_id: UUID
    relation_type: str = Field(..., min_length=1, max_length=64)
    assessment: FactAssessment
    claim_text: str | None = Field(default=None, max_length=4000)
    evidence_summary: str | None = Field(default=None, max_length=2000)
    evidence_sentence: str | None = Field(default=None, max_length=4000)
    evidence_sentence_source: str | None = Field(default=None, max_length=32)
    evidence_sentence_confidence: str | None = Field(default=None, max_length=32)
    evidence_sentence_rationale: str | None = Field(default=None, max_length=4000)
    source_document_ref: str | None = Field(default=None, max_length=512)
    source_ref: str | None = Field(default=None, max_length=1024)
    agent_run_id: str | None = Field(default=None, max_length=255)
    ai_provenance: ClaimAIProvenanceEnvelope | None = None
    metadata: JSONObject = Field(default_factory=dict)

    @property
    def derived_confidence(self) -> float:
        return assessment_confidence(self.assessment)


class GraphValidationNextAction(BaseModel):
    """One suggested next action for a graph validation result."""

    model_config = ConfigDict(strict=True)

    action: str
    reason: str
    proposal_type: str | None = None
    endpoint: str | None = None
    payload: JSONObject = Field(default_factory=dict)


class KernelGraphValidationResponse(BaseModel):
    """Response model for graph-side validation checks."""

    model_config = ConfigDict(strict=True)

    valid: bool
    code: str
    message: str
    severity: str
    next_actions: list[GraphValidationNextAction] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    normalized_relation_type: str | None = None
    source_type: str | None = None
    target_type: str | None = None
    requires_evidence: bool | None = None
    profile: str | None = None
    validation_state: str | None = None
    validation_reason: str | None = None
    persistability: str | None = None


class KernelRelationCreateRequest(BaseModel):
    """Request model for creating a canonical relation (claim + materialization)."""

    model_config = ConfigDict(strict=False, extra="forbid")

    source_id: UUID
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_id: UUID
    assessment: FactAssessment
    evidence_summary: str | None = None
    evidence_sentence: str | None = Field(default=None, max_length=2000)
    evidence_sentence_source: str | None = Field(default=None, max_length=64)
    evidence_sentence_confidence: str | None = Field(default=None, max_length=32)
    evidence_sentence_rationale: str | None = Field(default=None, max_length=2000)
    evidence_tier: str | None = Field(default=None, max_length=32)
    provenance_id: UUID | None = None
    source_document_ref: str | None = Field(default=None, max_length=512)
    metadata: JSONObject = Field(default_factory=dict)

    @property
    def derived_confidence(self) -> float:
        return assessment_confidence(self.assessment)


class KernelRelationResponse(BaseModel):
    """Response model for a kernel relation."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    source_claim_id: UUID | None = None
    source_id: UUID
    relation_type: str
    target_id: UUID
    confidence: float
    aggregate_confidence: float
    source_count: int
    highest_evidence_tier: str | None
    curation_status: str
    evidence_summary: str | None = None
    evidence_sentence: str | None = None
    evidence_sentence_source: str | None = None
    evidence_sentence_confidence: str | None = None
    evidence_sentence_rationale: str | None = None
    paper_links: list[KernelRelationPaperLinkResponse] = Field(default_factory=list)
    provenance_id: UUID | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class KernelRelationClaimResponse(BaseModel):
    """Response model for one extraction relation claim."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    source_document_id: UUID | None = None
    source_document_ref: str | None = None
    agent_run_id: str | None = None
    source_type: str
    relation_type: str
    target_type: str
    source_label: str | None
    target_label: str | None
    confidence: float
    validation_state: str
    validation_reason: str | None
    persistability: str
    claim_status: str
    polarity: str
    claim_text: str | None
    claim_section: str | None
    linked_relation_id: UUID | None
    metadata: JSONObject
    triaged_by: UUID | None
    triaged_at: datetime | None
    created_at: datetime
    updated_at: datetime


class KernelRelationClaimListResponse(BaseModel):
    """List response for relation claims in one research space."""

    model_config = ConfigDict(strict=True)

    claims: list[KernelRelationClaimResponse]
    total: int
    offset: int
    limit: int


class KernelClaimEvidenceResponse(BaseModel):
    """Response model for one claim evidence row."""

    model_config = ConfigDict(strict=True)

    id: UUID
    claim_id: UUID
    source_document_id: UUID | None = None
    source_document_ref: str | None = None
    agent_run_id: str | None = None
    sentence: str | None
    sentence_source: str | None
    sentence_confidence: str | None
    sentence_rationale: str | None
    figure_reference: str | None
    table_reference: str | None
    confidence: float
    metadata: JSONObject
    paper_links: list[KernelRelationPaperLinkResponse] = Field(default_factory=list)
    created_at: datetime


class KernelClaimEvidenceListResponse(BaseModel):
    """List response for claim evidence rows."""

    model_config = ConfigDict(strict=True)

    claim_id: UUID
    evidence: list[KernelClaimEvidenceResponse]
    total: int


class KernelRelationConflictResponse(BaseModel):
    """Conflict summary for one canonical relation."""

    model_config = ConfigDict(strict=True)

    relation_id: UUID
    support_count: int
    refute_count: int
    support_claim_ids: list[UUID]
    refute_claim_ids: list[UUID]


class KernelRelationConflictListResponse(BaseModel):
    """List response for mixed-polarity relation conflicts."""

    model_config = ConfigDict(strict=True)

    conflicts: list[KernelRelationConflictResponse]
    total: int
    offset: int
    limit: int


class KernelGraphDocumentRequest(BaseModel):
    """Request payload for unified graph documents with claim/evidence overlays."""

    model_config = ConfigDict(strict=False)

    mode: Literal["starter", "seeded"]
    seed_entity_ids: list[UUID] = Field(default_factory=list)
    depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    relation_types: list[str] | None = None
    curation_statuses: list[str] | None = None
    max_nodes: int = Field(default=180, ge=20, le=500)
    max_edges: int = Field(default=260, ge=20, le=1000)
    include_claims: bool = True
    include_evidence: bool = True
    max_claims: int = Field(default=250, ge=1, le=1000)
    evidence_limit_per_claim: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def _validate_seeded_mode(self) -> KernelGraphDocumentRequest:
        if self.mode == "seeded" and not self.seed_entity_ids:
            msg = "seed_entity_ids must not be empty when mode is 'seeded'"
            raise ValueError(msg)
        return self


class KernelGraphDocumentNode(BaseModel):
    """One typed graph node in the unified graph document."""

    model_config = ConfigDict(strict=True)

    id: str = Field(min_length=1, max_length=255)
    resource_id: str = Field(min_length=1, max_length=255)
    kind: Literal["ENTITY", "CLAIM", "EVIDENCE"]
    type_label: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=512)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    curation_status: str | None = Field(default=None, max_length=32)
    claim_status: str | None = Field(default=None, max_length=32)
    polarity: str | None = Field(default=None, max_length=32)
    canonical_relation_id: UUID | None = None
    metadata: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KernelGraphDocumentEdge(BaseModel):
    """One typed graph edge in the unified graph document."""

    model_config = ConfigDict(strict=True)

    id: str = Field(min_length=1, max_length=255)
    resource_id: str | None = Field(default=None, max_length=255)
    kind: Literal["CANONICAL_RELATION", "CLAIM_PARTICIPANT", "CLAIM_EVIDENCE"]
    source_id: str = Field(min_length=1, max_length=255)
    target_id: str = Field(min_length=1, max_length=255)
    type_label: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=512)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    curation_status: str | None = Field(default=None, max_length=32)
    claim_id: UUID | None = None
    canonical_relation_id: UUID | None = None
    evidence_id: UUID | None = None
    metadata: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KernelGraphDocumentCounts(BaseModel):
    """Per-kind counts returned with a unified graph document."""

    model_config = ConfigDict(strict=True)

    entity_nodes: int = Field(ge=0)
    claim_nodes: int = Field(ge=0)
    evidence_nodes: int = Field(ge=0)
    canonical_edges: int = Field(ge=0)
    claim_participant_edges: int = Field(ge=0)
    claim_evidence_edges: int = Field(ge=0)


class KernelGraphDocumentMeta(BaseModel):
    """Metadata describing graph-document scope and included overlays."""

    model_config = ConfigDict(strict=True)

    mode: Literal["starter", "seeded"]
    seed_entity_ids: list[UUID]
    requested_depth: int
    requested_top_k: int
    pre_cap_entity_node_count: int
    pre_cap_canonical_edge_count: int
    truncated_entity_nodes: bool
    truncated_canonical_edges: bool
    included_claims: bool
    included_evidence: bool
    max_claims: int
    evidence_limit_per_claim: int
    counts: KernelGraphDocumentCounts


class KernelGraphDocumentResponse(BaseModel):
    """Unified graph document containing canonical, claim, and evidence elements."""

    model_config = ConfigDict(strict=True)

    nodes: list[KernelGraphDocumentNode]
    edges: list[KernelGraphDocumentEdge]
    meta: KernelGraphDocumentMeta


class KernelRelationSuggestionRequest(BaseModel):
    """Request payload for dictionary-constrained relation suggestion runs."""

    model_config = ConfigDict(strict=False)

    source_entity_ids: list[UUID] = Field(min_length=1, max_length=50)
    limit_per_source: int = Field(default=10, ge=1, le=50)
    min_score: float = Field(default=0.70, ge=0.0, le=1.0)
    allowed_relation_types: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    target_entity_types: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    exclude_existing_relations: bool = True
    require_all_ready: bool = False


class KernelRelationSuggestionScoreBreakdownResponse(BaseModel):
    """Score components for one relation suggestion row."""

    model_config = ConfigDict(strict=True)

    vector_score: float = Field(ge=0.0, le=1.0)
    graph_overlap_score: float = Field(ge=0.0, le=1.0)
    relation_prior_score: float = Field(ge=0.0, le=1.0)


class KernelRelationSuggestionConstraintCheckResponse(BaseModel):
    """Constraint trace proving dictionary validation for a suggestion row."""

    model_config = ConfigDict(strict=True)

    passed: bool
    source_entity_type: str = Field(min_length=1, max_length=64)
    relation_type: str = Field(min_length=1, max_length=64)
    target_entity_type: str = Field(min_length=1, max_length=64)


class KernelRelationSuggestionResponse(BaseModel):
    """One relation suggestion row."""

    model_config = ConfigDict(strict=True)

    source_entity_id: UUID
    target_entity_id: UUID
    relation_type: str = Field(min_length=1, max_length=64)
    final_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: KernelRelationSuggestionScoreBreakdownResponse
    constraint_check: KernelRelationSuggestionConstraintCheckResponse


class KernelRelationSuggestionSkippedSourceResponse(BaseModel):
    """One source entity skipped during relation suggestion due to readiness."""

    model_config = ConfigDict(strict=True)

    entity_id: UUID
    state: str = Field(min_length=1, max_length=16)
    reason: str = Field(min_length=1, max_length=128)


class KernelRelationSuggestionListResponse(BaseModel):
    """List response for constrained relation suggestions."""

    model_config = ConfigDict(strict=True)

    suggestions: list[KernelRelationSuggestionResponse]
    total: int
    limit_per_source: int
    min_score: float = Field(ge=0.0, le=1.0)
    incomplete: bool = False
    skipped_sources: list[KernelRelationSuggestionSkippedSourceResponse] = Field(
        default_factory=list,
    )


class DictionaryEntityTypeResponse(BaseModel):
    """Typed dictionary entity-type response."""

    model_config = ConfigDict(strict=True)

    id: str
    display_name: str
    description: str
    domain_context: str
    external_ontology_ref: str | None = None
    expected_properties: JSONObject = Field(default_factory=dict)
    description_embedding: list[float] | None = None
    embedded_at: datetime | None = None
    embedding_model: str | None = None
    created_by: str
    is_active: bool
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = None
    source_ref: str | None = None
    review_status: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionaryEntityTypeListResponse(BaseModel):
    """List response for typed dictionary entity types."""

    model_config = ConfigDict(strict=True)

    entity_types: list[DictionaryEntityTypeResponse]
    total: int


class DictionaryRelationTypeResponse(BaseModel):
    """Typed dictionary relation-type response."""

    model_config = ConfigDict(strict=True)

    id: str
    display_name: str
    description: str
    domain_context: str
    is_directional: bool
    inverse_label: str | None = None
    description_embedding: list[float] | None = None
    embedded_at: datetime | None = None
    embedding_model: str | None = None
    created_by: str
    is_active: bool
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = None
    source_ref: str | None = None
    review_status: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionaryRelationTypeListResponse(BaseModel):
    """List response for typed dictionary relation types."""

    model_config = ConfigDict(strict=True)

    relation_types: list[DictionaryRelationTypeResponse]
    total: int


class DictionaryRelationSynonymResponse(BaseModel):
    """Typed dictionary relation-synonym response."""

    model_config = ConfigDict(strict=True)

    id: int
    relation_type: str
    synonym: str
    source: str | None = None
    created_by: str
    is_active: bool
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    superseded_by: str | None = None
    source_ref: str | None = None
    review_status: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionaryRelationSynonymListResponse(BaseModel):
    """List response for typed dictionary relation synonyms."""

    model_config = ConfigDict(strict=True)

    relation_synonyms: list[DictionaryRelationSynonymResponse]
    total: int


class DictionarySearchResultResponse(BaseModel):
    """Typed dictionary search hit."""

    model_config = ConfigDict(strict=True)

    dimension: str
    entry_id: str
    display_name: str
    description: str | None = None
    domain_context: str | None = None
    match_method: str
    similarity_score: float
    metadata: JSONObject = Field(default_factory=dict)


class DictionarySearchListResponse(BaseModel):
    """List response for typed dictionary search hits."""

    model_config = ConfigDict(strict=True)

    results: list[DictionarySearchResultResponse]
    total: int


DictionaryProposalType = Literal[
    "DOMAIN_CONTEXT",
    "ENTITY_TYPE",
    "VARIABLE",
    "RELATION_TYPE",
    "RELATION_CONSTRAINT",
    "RELATION_SYNONYM",
    "VALUE_SET",
    "VALUE_SET_ITEM",
]
DictionaryProposalStatus = Literal[
    "SUBMITTED",
    "DUPLICATE",
    "CHANGES_REQUESTED",
    "APPROVED",
    "REJECTED",
    "MERGED",
]


class DictionaryProposalResponse(BaseModel):
    """Typed governed dictionary-proposal response."""

    model_config = ConfigDict(strict=True)

    id: str
    proposal_type: DictionaryProposalType
    status: DictionaryProposalStatus
    entity_type: str | None = None
    source_type: str | None = None
    relation_type: str | None = None
    target_type: str | None = None
    value_set_id: str | None = None
    variable_id: str | None = None
    canonical_name: str | None = None
    data_type: str | None = None
    preferred_unit: str | None = None
    constraints: JSONObject = Field(default_factory=dict)
    sensitivity: str | None = None
    code: str | None = None
    synonym: str | None = None
    source: str | None = None
    display_name: str | None = None
    name: str | None = None
    display_label: str | None = None
    description: str | None = None
    domain_context: str | None = None
    external_ontology_ref: str | None = None
    external_ref: str | None = None
    expected_properties: JSONObject = Field(default_factory=dict)
    synonyms: list[str] = Field(default_factory=list)
    is_directional: bool | None = None
    inverse_label: str | None = None
    is_extensible: bool | None = None
    sort_order: int | None = None
    is_active_value: bool | None = None
    is_allowed: bool | None = None
    requires_evidence: bool | None = None
    profile: str | None = None
    rationale: str
    evidence_payload: JSONObject = Field(default_factory=dict)
    proposed_by: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    decision_reason: str | None = None
    merge_target_type: str | None = None
    merge_target_id: str | None = None
    applied_domain_context_id: str | None = None
    applied_entity_type_id: str | None = None
    applied_variable_id: str | None = None
    applied_relation_type_id: str | None = None
    applied_constraint_id: int | None = None
    applied_relation_synonym_id: int | None = None
    applied_value_set_id: str | None = None
    applied_value_set_item_id: int | None = None
    source_ref: str | None = None
    created_at: datetime
    updated_at: datetime


class DictionaryEntityTypeProposalCreateRequest(BaseModel):
    """Governed entity-type proposal request."""

    model_config = ConfigDict(strict=False, extra="forbid")

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    external_ontology_ref: str | None = Field(default=None, max_length=255)
    expected_properties: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class DictionaryRelationTypeProposalCreateRequest(BaseModel):
    """Governed relation-type proposal request."""

    model_config = ConfigDict(strict=False, extra="forbid")

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    is_directional: bool = True
    inverse_label: str | None = Field(default=None, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)


class DictionaryRelationConstraintProposalCreateRequest(BaseModel):
    """Governed relation-constraint proposal request."""

    model_config = ConfigDict(strict=False, extra="forbid")

    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    is_allowed: bool = True
    requires_evidence: bool = True
    profile: Literal["EXPECTED", "ALLOWED", "REVIEW_ONLY", "FORBIDDEN"] = "ALLOWED"
    source_ref: str | None = Field(default=None, max_length=1024)


class KernelReasoningPathResponse(BaseModel):
    """One reasoning path summary row."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    path_kind: str
    status: str
    start_entity_id: UUID
    end_entity_id: UUID
    root_claim_id: UUID
    path_length: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)
    path_signature_hash: str
    generated_by: str | None
    generated_at: datetime
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


class KernelReasoningPathStepResponse(BaseModel):
    """One ordered step inside a reasoning path."""

    model_config = ConfigDict(strict=True)

    id: UUID
    path_id: UUID
    step_index: int
    source_claim_id: UUID
    target_claim_id: UUID
    claim_relation_id: UUID
    canonical_relation_id: UUID | None
    metadata: JSONObject
    created_at: datetime


class KernelReasoningPathListResponse(BaseModel):
    """List response for reasoning paths in one space."""

    model_config = ConfigDict(strict=True)

    paths: list[KernelReasoningPathResponse]
    total: int
    offset: int
    limit: int


class KernelReasoningPathDetailResponse(BaseModel):
    """Fully expanded reasoning-path payload."""

    model_config = ConfigDict(strict=True)

    path: KernelReasoningPathResponse
    steps: list[KernelReasoningPathStepResponse]
    canonical_relations: list[KernelRelationResponse]
    claims: list[KernelRelationClaimResponse]
    claim_relations: list[ClaimRelationResponse]
    participants: list[ClaimParticipantResponse]
    evidence: list[KernelClaimEvidenceResponse]
    counts: KernelGraphViewCountsResponse


class ConceptExternalRefRequest(BaseModel):
    """External identifier attached to an AI Full Mode concept proposal."""

    model_config = ConfigDict(strict=False)

    namespace: str = Field(..., min_length=1, max_length=128)
    identifier: str = Field(..., min_length=1, max_length=255)


class ConceptProposalCreateRequest(BaseModel):
    """Request payload for proposing one governed graph concept."""

    model_config = ConfigDict(strict=False)

    domain_context: str = Field(..., min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=64)
    canonical_label: str = Field(..., min_length=1, max_length=255)
    synonyms: list[str] = Field(default_factory=list)
    external_refs: list[ConceptExternalRefRequest] = Field(default_factory=list)
    evidence_payload: JSONObject = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConceptProposalResponse(BaseModel):
    """Response payload for one governed graph concept proposal."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    status: Literal[
        "SUBMITTED",
        "DUPLICATE_CANDIDATE",
        "CHANGES_REQUESTED",
        "APPROVED",
        "REJECTED",
        "MERGED",
        "APPLIED",
    ]
    candidate_decision: Literal[
        "CREATE_NEW",
        "MATCH_EXISTING",
        "MERGE_AS_SYNONYM",
        "SYNONYM_COLLISION",
        "EXTERNAL_REF_MATCH",
        "NEEDS_REVIEW",
    ]
    domain_context: str
    entity_type: str
    canonical_label: str
    normalized_label: str
    concept_set_id: str | None
    existing_concept_member_id: str | None
    applied_concept_member_id: str | None
    synonyms_payload: list[str]
    external_refs_payload: list[JSONObject]
    evidence_payload: JSONObject
    duplicate_checks_payload: JSONObject
    warnings_payload: list[str]
    decision_payload: JSONObject
    rationale: str | None
    proposed_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    decision_reason: str | None
    source_ref: str | None
    proposal_hash: str
    created_at: datetime
    updated_at: datetime


class GraphChangeConceptRequest(BaseModel):
    """Local concept inside an AI Full Mode graph-change proposal."""

    model_config = ConfigDict(strict=False)

    local_id: str = Field(..., min_length=1, max_length=128)
    domain_context: str = Field(..., min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=64)
    canonical_label: str = Field(..., min_length=1, max_length=255)
    synonyms: list[str] = Field(default_factory=list)
    external_refs: list[ConceptExternalRefRequest] = Field(default_factory=list)
    evidence_payload: JSONObject = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=4000)


class GraphChangeClaimRequest(BaseModel):
    """Local relation claim inside an AI Full Mode graph-change proposal."""

    model_config = ConfigDict(strict=False, extra="forbid")

    source_local_id: str = Field(..., min_length=1, max_length=128)
    target_local_id: str = Field(..., min_length=1, max_length=128)
    relation_type: str = Field(..., min_length=1, max_length=64)
    assessment: FactAssessment
    evidence_payload: JSONObject = Field(default_factory=dict)
    claim_text: str | None = Field(default=None, max_length=4000)
    source_document_ref: str | None = Field(default=None, max_length=1024)

    @property
    def derived_confidence(self) -> float:
        return assessment_confidence(self.assessment)


class GraphChangeProposalCreateRequest(BaseModel):
    """Request payload for proposing a governed mini-graph bundle."""

    model_config = ConfigDict(strict=False)

    concepts: list[GraphChangeConceptRequest] = Field(..., min_length=1)
    claims: list[GraphChangeClaimRequest] = Field(default_factory=list)
    source_ref: str | None = Field(default=None, max_length=1024)


class GraphChangeProposalResponse(BaseModel):
    """Response payload for one governed mini-graph proposal."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    status: Literal["READY_FOR_REVIEW", "CHANGES_REQUESTED", "REJECTED", "APPLIED"]
    proposal_payload: JSONObject
    resolution_plan_payload: JSONObject
    warnings_payload: list[str]
    error_payload: list[str]
    applied_concept_member_ids_payload: list[str]
    applied_claim_ids_payload: list[str]
    proposed_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    decision_reason: str | None
    source_ref: str | None
    proposal_hash: str
    created_at: datetime
    updated_at: datetime


class AIDecisionSubmitRequest(BaseModel):
    """AI decision envelope submitted to the graph DB policy engine."""

    model_config = ConfigDict(strict=False, extra="forbid")

    target_type: Literal["concept_proposal", "graph_change_proposal"]
    target_id: UUID
    action: Literal[
        "APPROVE",
        "MERGE",
        "REJECT",
        "REQUEST_CHANGES",
        "APPLY_RESOLUTION_PLAN",
    ]
    ai_principal: str = Field(..., min_length=1, max_length=128)
    confidence_assessment: DecisionConfidenceAssessment
    risk_tier: Literal["low", "medium", "high"]
    input_hash: str = Field(..., min_length=64, max_length=64)
    evidence_payload: JSONObject = Field(default_factory=dict)
    decision_payload: JSONObject = Field(default_factory=dict)


class AIDecisionResponse(BaseModel):
    """Response payload for one AI Full Mode decision envelope."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    target_type: Literal["concept_proposal", "graph_change_proposal"]
    target_id: str
    action: Literal[
        "APPROVE",
        "MERGE",
        "REJECT",
        "REQUEST_CHANGES",
        "APPLY_RESOLUTION_PLAN",
    ]
    status: Literal["SUBMITTED", "REJECTED", "APPLIED"]
    ai_principal: str
    confidence: float
    computed_confidence: float
    confidence_assessment_payload: JSONObject
    confidence_model_version: str | None
    risk_tier: Literal["low", "medium", "high"]
    input_hash: str
    policy_outcome: Literal[
        "human_required",
        "ai_allowed",
        "ai_allowed_when_low_risk",
        "blocked",
    ]
    evidence_payload: JSONObject
    decision_payload: JSONObject
    rejection_reason: str | None
    created_by: str
    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConnectorProposalCreateRequest(BaseModel):
    """Request payload for proposing connector metadata and mappings."""

    model_config = ConfigDict(strict=False)

    connector_slug: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    connector_kind: str = Field(..., min_length=1, max_length=64)
    domain_context: str = Field(..., min_length=1, max_length=64)
    metadata_payload: JSONObject = Field(default_factory=dict)
    mapping_payload: JSONObject = Field(default_factory=dict)
    evidence_payload: JSONObject = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConnectorProposalResponse(BaseModel):
    """Response payload for one governed connector metadata proposal."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    status: Literal["SUBMITTED", "CHANGES_REQUESTED", "APPROVED", "REJECTED"]
    connector_slug: str
    display_name: str
    connector_kind: str
    domain_context: str
    metadata_payload: JSONObject
    mapping_payload: JSONObject
    validation_payload: JSONObject
    approval_payload: JSONObject
    rationale: str | None
    evidence_payload: JSONObject
    proposed_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    decision_reason: str | None
    source_ref: str | None
    created_at: datetime
    updated_at: datetime


GraphOperatingMode = Literal[
    "manual",
    "ai_assist_human_batch",
    "human_evidence_ai_graph",
    "ai_full_graph",
    "ai_full_evidence",
    "continuous_learning",
]
GraphWorkflowKind = Literal[
    "evidence_approval",
    "batch_review",
    "ai_evidence_decision",
    "conflict_resolution",
    "continuous_learning_review",
    "bootstrap_review",
]
GraphWorkflowStatus = Literal[
    "SUBMITTED",
    "PLAN_READY",
    "WAITING_REVIEW",
    "APPLIED",
    "REJECTED",
    "CHANGES_REQUESTED",
    "BLOCKED",
    "FAILED",
]
GraphWorkflowAction = Literal[
    "apply_plan",
    "approve",
    "reject",
    "request_changes",
    "split",
    "defer_to_human",
    "mark_resolved",
]
GraphWorkflowRiskTier = Literal["low", "medium", "high"]


class GraphWorkflowPolicy(BaseModel):
    """Per-space workflow policy controls for one operating mode."""

    model_config = ConfigDict(strict=True)

    allow_ai_graph_repair: bool = False
    allow_ai_evidence_decisions: bool = False
    batch_auto_apply_low_risk: bool = False
    trusted_ai_principals: list[str] = Field(default_factory=list)
    min_ai_confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class OperatingModeRequest(BaseModel):
    """Request payload for updating one graph space operating mode."""

    model_config = ConfigDict(strict=True)

    mode: GraphOperatingMode
    workflow_policy: GraphWorkflowPolicy = Field(
        default_factory=GraphWorkflowPolicy,
    )


class OperatingModeResponse(BaseModel):
    """Public operating mode response."""

    model_config = ConfigDict(strict=True)

    research_space_id: str
    mode: GraphOperatingMode
    workflow_policy: GraphWorkflowPolicy
    capabilities: JSONObject


class OperatingModeCapabilitiesResponse(BaseModel):
    """Public capabilities for the active operating mode."""

    model_config = ConfigDict(strict=True)

    research_space_id: str
    mode: GraphOperatingMode
    capabilities: JSONObject


class GraphWorkflowCreateRequest(BaseModel):
    """Request payload for creating a unified graph workflow."""

    model_config = ConfigDict(strict=False)

    kind: GraphWorkflowKind
    input_payload: JSONObject = Field(default_factory=dict)
    decision_payload: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class GraphWorkflowAIDecisionEnvelope(BaseModel):
    """Trusted AI actor envelope for workflow actions."""

    model_config = ConfigDict(strict=False)

    ai_principal: str = Field(..., min_length=1, max_length=128)
    model_id: str | None = Field(default=None, max_length=128)
    model_version: str | None = Field(default=None, max_length=128)
    prompt_id: str | None = Field(default=None, max_length=128)
    prompt_version: str | None = Field(default=None, max_length=128)
    evidence_locator: str | None = Field(default=None, max_length=1024)
    rationale: str = Field(..., min_length=1, max_length=4000)


class GraphWorkflowActionRequest(BaseModel):
    """Request payload for acting on one unified graph workflow."""

    model_config = ConfigDict(strict=False, extra="forbid")

    action: GraphWorkflowAction
    input_hash: str | None = Field(default=None, min_length=64, max_length=64)
    risk_tier: GraphWorkflowRiskTier = "low"
    confidence_assessment: DecisionConfidenceAssessment | None = None
    reason: str | None = Field(default=None, max_length=4096)
    decision_payload: JSONObject = Field(default_factory=dict)
    generated_resources_payload: JSONObject = Field(default_factory=dict)
    ai_decision: GraphWorkflowAIDecisionEnvelope | None = None


class GraphWorkflowResponse(BaseModel):
    """Public unified graph workflow response."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    kind: GraphWorkflowKind
    status: GraphWorkflowStatus
    operating_mode: GraphOperatingMode
    input_payload: JSONObject
    plan_payload: JSONObject
    generated_resources_payload: JSONObject
    decision_payload: JSONObject
    policy_payload: JSONObject
    explanation_payload: JSONObject
    source_ref: str | None
    workflow_hash: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class GraphWorkflowListResponse(BaseModel):
    """List response for unified graph workflows."""

    model_config = ConfigDict(strict=True)

    workflows: list[GraphWorkflowResponse]
    total: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)


class ExplanationResponse(BaseModel):
    """Human-readable explanation for graph workflow resources."""

    model_config = ConfigDict(strict=True)

    research_space_id: str
    resource_type: str
    resource_id: str
    why_this_exists: str
    approved_by: str | None = None
    evidence: JSONObject = Field(default_factory=dict)
    policy: JSONObject = Field(default_factory=dict)
    generated_resources: JSONObject = Field(default_factory=dict)
    validation: JSONObject = Field(default_factory=dict)
    next_action: JSONObject = Field(default_factory=dict)
    details: JSONObject = Field(default_factory=dict)


class ValidationExplanationRequest(BaseModel):
    """Request payload for explainable validation preflight."""

    model_config = ConfigDict(strict=False)

    validation_payload: JSONObject = Field(default_factory=dict)
    context_payload: JSONObject = Field(default_factory=dict)


class CreateManualHypothesisRequest(BaseModel):
    """Request payload for manually logging one hypothesis."""

    model_config = ConfigDict(strict=True)

    statement: str = Field(..., min_length=1, max_length=4000)
    rationale: str = Field(..., min_length=1, max_length=4000)
    seed_entity_ids: list[str] = Field(default_factory=list, max_length=100)
    source_type: str = Field(default="manual", min_length=1, max_length=64)


class HypothesisResponse(BaseModel):
    """Serialized hypothesis row derived from relation-claim ledger."""

    model_config = ConfigDict(strict=True)

    claim_id: UUID
    polarity: str
    claim_status: str
    validation_state: str
    persistability: str
    confidence: float
    source_label: str | None
    relation_type: str
    target_label: str | None
    claim_text: str | None
    linked_relation_id: UUID | None
    origin: str
    seed_entity_ids: list[str]
    supporting_provenance_ids: list[str]
    reasoning_path_id: UUID | None
    supporting_claim_ids: list[str]
    direct_supporting_claim_ids: list[str]
    transferred_supporting_claim_ids: list[str]
    transferred_from_entities: list[str]
    transfer_basis: list[str]
    contradiction_claim_ids: list[str]
    explanation: str | None
    path_confidence: float | None
    path_length: int | None
    created_at: datetime
    metadata: JSONObject


class HypothesisListResponse(BaseModel):
    """List response for hypotheses in one research space."""

    model_config = ConfigDict(strict=True)

    hypotheses: list[HypothesisResponse]
    total: int
    offset: int
    limit: int


__all__ = [
    "AIDecisionResponse",
    "AIDecisionSubmitRequest",
    "ClaimParticipantListResponse",
    "ClaimParticipantResponse",
    "ClaimRelationResponse",
    "ConceptExternalRefRequest",
    "ConceptProposalCreateRequest",
    "ConceptProposalResponse",
    "ConnectorProposalCreateRequest",
    "ConnectorProposalResponse",
    "CreateManualHypothesisRequest",
    "DecisionConfidenceAssessment",
    "DecisionConfidenceResult",
    "ExplanationResponse",
    "GraphChangeClaimRequest",
    "GraphChangeConceptRequest",
    "GraphChangeProposalCreateRequest",
    "GraphChangeProposalResponse",
    "GraphOperatingMode",
    "GraphWorkflowAction",
    "GraphWorkflowActionRequest",
    "GraphWorkflowAIDecisionEnvelope",
    "GraphWorkflowCreateRequest",
    "GraphWorkflowKind",
    "GraphWorkflowListResponse",
    "GraphWorkflowPolicy",
    "GraphWorkflowResponse",
    "GraphWorkflowRiskTier",
    "GraphWorkflowStatus",
    "HypothesisListResponse",
    "HypothesisResponse",
    "KernelClaimEvidenceListResponse",
    "KernelClaimEvidenceResponse",
    "KernelEntityEmbeddingRefreshRequest",
    "KernelEntityEmbeddingRefreshResponse",
    "KernelEntityEmbeddingStatusListResponse",
    "KernelEntityEmbeddingStatusResponse",
    "KernelEntityListResponse",
    "KernelEntityResponse",
    "KernelGraphDocumentCounts",
    "KernelGraphDocumentEdge",
    "KernelGraphDocumentMeta",
    "KernelGraphDocumentNode",
    "KernelGraphDocumentRequest",
    "KernelGraphDocumentResponse",
    "KernelGraphViewCountsResponse",
    "KernelReasoningPathDetailResponse",
    "KernelReasoningPathListResponse",
    "KernelReasoningPathResponse",
    "KernelReasoningPathStepResponse",
    "KernelRelationClaimCreateRequest",
    "KernelRelationClaimListResponse",
    "KernelRelationClaimResponse",
    "KernelRelationConflictListResponse",
    "KernelRelationConflictResponse",
    "KernelRelationPaperLinkResponse",
    "KernelRelationResponse",
    "KernelRelationSuggestionConstraintCheckResponse",
    "KernelRelationSuggestionListResponse",
    "KernelRelationSuggestionRequest",
    "KernelRelationSuggestionResponse",
    "KernelRelationSuggestionScoreBreakdownResponse",
    "KernelRelationSuggestionSkippedSourceResponse",
    "OperatingModeCapabilitiesResponse",
    "OperatingModeRequest",
    "OperatingModeResponse",
    "ValidationExplanationRequest",
]
