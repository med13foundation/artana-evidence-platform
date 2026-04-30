"""Service-local graph API contracts used by graph-harness."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import JSONObject, JSONValue
from .graph_decision_contracts import (
    DecisionConfidenceAssessment,
    DecisionConfidenceResult,
    DecisionDuplicateConflictState,
    DecisionEvidenceState,
    DecisionRiskTier,
    DecisionSourceReliability,
    DecisionValidationState,
)
from .graph_dictionary_contracts import (
    DictionaryEntityTypeListResponse,
    DictionaryEntityTypeProposalCreateRequest,
    DictionaryEntityTypeResponse,
    DictionaryProposalResponse,
    DictionaryProposalStatus,
    DictionaryProposalType,
    DictionaryRelationConstraintProposalCreateRequest,
    DictionaryRelationSynonymListResponse,
    DictionaryRelationSynonymResponse,
    DictionaryRelationTypeListResponse,
    DictionaryRelationTypeProposalCreateRequest,
    DictionaryRelationTypeResponse,
    DictionarySearchListResponse,
    DictionarySearchResultResponse,
)
from .graph_fact_assessment import (
    FactAssessment,
    assessment_confidence,
)
from .graph_workflow_contracts import (
    CreateManualHypothesisRequest,
    ExplanationResponse,
    GraphOperatingMode,
    GraphWorkflowAction,
    GraphWorkflowActionRequest,
    GraphWorkflowAIDecisionEnvelope,
    GraphWorkflowCreateRequest,
    GraphWorkflowKind,
    GraphWorkflowListResponse,
    GraphWorkflowPolicy,
    GraphWorkflowResponse,
    GraphWorkflowRiskTier,
    GraphWorkflowStatus,
    HypothesisListResponse,
    HypothesisResponse,
    OperatingModeCapabilitiesResponse,
    OperatingModeRequest,
    OperatingModeResponse,
    ValidationExplanationRequest,
)


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
    "DecisionDuplicateConflictState",
    "DecisionEvidenceState",
    "DecisionRiskTier",
    "DecisionSourceReliability",
    "DecisionValidationState",
    "DictionaryEntityTypeListResponse",
    "DictionaryEntityTypeProposalCreateRequest",
    "DictionaryEntityTypeResponse",
    "DictionaryProposalResponse",
    "DictionaryProposalStatus",
    "DictionaryProposalType",
    "DictionaryRelationConstraintProposalCreateRequest",
    "DictionaryRelationSynonymListResponse",
    "DictionaryRelationSynonymResponse",
    "DictionaryRelationTypeListResponse",
    "DictionaryRelationTypeProposalCreateRequest",
    "DictionaryRelationTypeResponse",
    "DictionarySearchListResponse",
    "DictionarySearchResultResponse",
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
