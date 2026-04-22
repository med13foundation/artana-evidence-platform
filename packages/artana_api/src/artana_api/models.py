"""Typed request and response models for the public Artana SDK."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._json import JSONObject, JSONValue


class SDKResponseModel(BaseModel):
    """Base response model that tolerates additive server changes."""

    model_config = ConfigDict(extra="allow")


class SDKRequestModel(BaseModel):
    """Base request model for SDK-side validation."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(SDKResponseModel):
    status: str
    version: str


class ResearchSpace(SDKResponseModel):
    id: str
    slug: str
    name: str
    description: str
    status: str
    role: str
    is_default: bool = False


class ResearchSpaceListResponse(SDKResponseModel):
    spaces: list[ResearchSpace]
    total: int


class CreateSpaceRequest(SDKRequestModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class AuthenticatedUser(SDKResponseModel):
    id: str
    email: str
    username: str
    full_name: str
    role: str
    status: str


class IssuedApiKey(SDKResponseModel):
    id: str
    name: str
    key_prefix: str
    status: str
    api_key: str
    created_at: str


class AuthContextResponse(SDKResponseModel):
    user: AuthenticatedUser
    default_space: ResearchSpace | None = None


class AuthCredentialResponse(SDKResponseModel):
    user: AuthenticatedUser
    api_key: IssuedApiKey
    default_space: ResearchSpace | None = None


class BootstrapApiKeyRequest(SDKRequestModel):
    email: str = Field(min_length=3, max_length=255)
    username: str | None = Field(default=None, min_length=1, max_length=50)
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["viewer", "researcher", "curator", "admin"] = "researcher"
    api_key_name: str = Field(default="Default SDK Key", min_length=1, max_length=100)
    api_key_description: str = Field(default="", max_length=500)
    create_default_space: bool = True


class CreateApiKeyRequest(SDKRequestModel):
    name: str = Field(default="Default SDK Key", min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class Run(SDKResponseModel):
    id: str
    space_id: str
    harness_id: str
    title: str
    status: str
    input_payload: JSONObject
    graph_service_status: str
    graph_service_version: str
    created_at: str
    updated_at: str


class RunListResponse(SDKResponseModel):
    runs: list[Run]
    total: int


class Artifact(SDKResponseModel):
    key: str
    media_type: str
    content: JSONObject
    created_at: str
    updated_at: str


class ArtifactListResponse(SDKResponseModel):
    artifacts: list[Artifact]
    total: int


class Workspace(SDKResponseModel):
    snapshot: JSONObject
    created_at: str
    updated_at: str


class EvidenceItem(SDKResponseModel):
    source_type: Literal["tool", "db", "paper", "web", "note", "api"]
    locator: str
    excerpt: str
    relevance: float = Field(ge=0.0, le=1.0)


class BaseAgentResult(SDKResponseModel):
    confidence_score: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


class GraphSearchAssessment(SDKResponseModel):
    support_band: Literal["INSUFFICIENT", "TENTATIVE", "SUPPORTED", "STRONG"]
    grounding_level: Literal["NONE", "ENTITY", "RELATION", "OBSERVATION", "AGGREGATED"]
    confidence_rationale: str = Field(min_length=1, max_length=2000)


_GRAPH_SEARCH_STRONG_THRESHOLD = 0.85
_GRAPH_SEARCH_SUPPORTED_THRESHOLD = 0.7
_GRAPH_SEARCH_TENTATIVE_THRESHOLD = 0.45
_GRAPH_SEARCH_NONE_GROUNDING_CAP = 0.4


def build_graph_search_assessment_from_confidence(
    confidence: float,
    *,
    confidence_rationale: str,
    grounding_level: Literal[
        "NONE",
        "ENTITY",
        "RELATION",
        "OBSERVATION",
        "AGGREGATED",
    ],
) -> GraphSearchAssessment:
    if confidence >= _GRAPH_SEARCH_STRONG_THRESHOLD:
        support_band = "STRONG"
    elif confidence >= _GRAPH_SEARCH_SUPPORTED_THRESHOLD:
        support_band = "SUPPORTED"
    elif confidence >= _GRAPH_SEARCH_TENTATIVE_THRESHOLD:
        support_band = "TENTATIVE"
    else:
        support_band = "INSUFFICIENT"
    return GraphSearchAssessment(
        support_band=support_band,
        grounding_level=grounding_level,
        confidence_rationale=confidence_rationale,
    )


def graph_search_assessment_confidence(assessment: GraphSearchAssessment) -> float:
    base_weight = {
        "INSUFFICIENT": 0.2,
        "TENTATIVE": 0.45,
        "SUPPORTED": 0.7,
        "STRONG": 0.9,
    }[assessment.support_band]
    grounding_cap = (
        _GRAPH_SEARCH_NONE_GROUNDING_CAP
        if assessment.grounding_level == "NONE"
        else 1.0
    )
    return max(0.0, min(base_weight, grounding_cap, 1.0))


def graph_search_grounding_level_from_counts(
    *,
    relation_count: int,
    observation_count: int,
) -> Literal["NONE", "ENTITY", "RELATION", "OBSERVATION", "AGGREGATED"]:
    if relation_count > 0 and observation_count > 0:
        return "AGGREGATED"
    if observation_count > 0:
        return "OBSERVATION"
    if relation_count > 0:
        return "RELATION"
    return "ENTITY"


class EvidenceChainItem(SDKResponseModel):
    provenance_id: str | None = None
    relation_id: str | None = None
    observation_id: str | None = None
    evidence_tier: str | None = None
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Derived numeric weight for compatibility and ranking.",
    )
    assessment: GraphSearchAssessment | None = Field(
        default=None,
        description="Qualitative assessment for this evidence reference.",
    )
    evidence_sentence: str | None = None
    source_ref: str | None = None

    @model_validator(mode="after")
    def _normalize_assessment(self) -> EvidenceChainItem:
        if self.assessment is None:
            source_confidence = self.confidence if self.confidence is not None else 0.45
            grounding_level = (
                "RELATION"
                if self.relation_id is not None
                else "OBSERVATION" if self.observation_id is not None else "NONE"
            )
            rationale = (
                "Derived from numeric evidence confidence."
                if self.confidence is not None
                else "No explicit graph-search assessment was supplied."
            )
            self.assessment = build_graph_search_assessment_from_confidence(
                source_confidence,
                confidence_rationale=rationale,
                grounding_level=grounding_level,
            )
        self.confidence = graph_search_assessment_confidence(self.assessment)
        return self


class GraphSearchResultEntry(SDKResponseModel):
    entity_id: str
    entity_type: str
    display_label: str | None = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    assessment: GraphSearchAssessment | None = Field(
        default=None,
        description="Qualitative assessment for the search result.",
    )
    matching_observation_ids: list[str] = Field(default_factory=list)
    matching_relation_ids: list[str] = Field(default_factory=list)
    evidence_chain: list[EvidenceChainItem] = Field(default_factory=list)
    explanation: str
    support_summary: str

    @model_validator(mode="after")
    def _normalize_assessment(self) -> GraphSearchResultEntry:
        if self.assessment is None:
            grounding_level = graph_search_grounding_level_from_counts(
                relation_count=len(self.matching_relation_ids),
                observation_count=len(self.matching_observation_ids),
            )
            rationale = (
                f"Derived from relevance_score={self.relevance_score:.2f} "
                f"and {len(self.matching_relation_ids)} relation(s) / "
                f"{len(self.matching_observation_ids)} observation(s)."
            )
            self.assessment = build_graph_search_assessment_from_confidence(
                self.relevance_score,
                confidence_rationale=rationale,
                grounding_level=grounding_level,
            )
        return self


class GraphSearchResult(BaseAgentResult):
    decision: Literal["generated", "fallback", "escalate"]
    research_space_id: str
    original_query: str
    interpreted_intent: str
    query_plan_summary: str
    total_results: int = Field(default=0, ge=0)
    results: list[GraphSearchResultEntry] = Field(default_factory=list)
    assessment: GraphSearchAssessment | None = Field(
        default=None,
        description="Qualitative assessment for the overall search result set.",
    )
    confidence_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Derived numeric weight for routing compatibility.",
    )
    executed_path: Literal["deterministic", "agent", "agent_fallback"] = "deterministic"
    warnings: list[str] = Field(default_factory=list)
    agent_run_id: str | None = None

    @model_validator(mode="after")
    def _normalize_assessment(self) -> GraphSearchResult:
        if self.assessment is None:
            if self.results:
                mean_relevance = sum(
                    result.relevance_score for result in self.results
                ) / len(self.results)
                grounding_level = (
                    "AGGREGATED"
                    if any(result.evidence_chain for result in self.results)
                    else "ENTITY"
                )
                rationale = (
                    f"Derived from {len(self.results)} ranked result(s) with "
                    f"mean relevance {mean_relevance:.2f}."
                )
                self.assessment = build_graph_search_assessment_from_confidence(
                    mean_relevance,
                    confidence_rationale=rationale,
                    grounding_level=grounding_level,
                )
            elif self.confidence_score is not None:
                self.assessment = build_graph_search_assessment_from_confidence(
                    self.confidence_score,
                    confidence_rationale=(
                        "Derived from the graph-search summary confidence score."
                    ),
                    grounding_level="NONE",
                )
            else:
                self.assessment = build_graph_search_assessment_from_confidence(
                    0.2,
                    confidence_rationale="No ranked graph-search results were produced.",
                    grounding_level="NONE",
                )
        self.confidence_score = graph_search_assessment_confidence(self.assessment)
        return self


class GraphSearchRequest(SDKRequestModel):
    question: str = Field(min_length=1, max_length=2000)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    max_depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    curation_statuses: list[str] | None = None
    include_evidence_chains: bool = True


class GraphSearchRunResponse(SDKResponseModel):
    run: Run
    result: GraphSearchResult


class FactAssessment(SDKResponseModel):
    support_band: Literal["INSUFFICIENT", "TENTATIVE", "SUPPORTED", "STRONG"]
    grounding_level: Literal[
        "SPAN",
        "SECTION",
        "DOCUMENT",
        "GENERATED",
        "GRAPH_INFERENCE",
    ]
    mapping_status: Literal["RESOLVED", "AMBIGUOUS", "NOT_APPLICABLE"]
    speculation_level: Literal["DIRECT", "HEDGED", "HYPOTHETICAL", "NOT_APPLICABLE"]
    confidence_rationale: str


class ProposedRelation(SDKResponseModel):
    source_id: str
    relation_type: str
    target_id: str
    assessment: FactAssessment
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_summary: str
    evidence_tier: Literal["COMPUTATIONAL"] = "COMPUTATIONAL"
    supporting_provenance_ids: list[str] = Field(default_factory=list)
    supporting_document_count: int = Field(default=0, ge=0)
    reasoning: str


class RejectedCandidate(SDKResponseModel):
    source_id: str
    relation_type: str
    target_id: str
    assessment: FactAssessment
    reason: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class GraphConnectionOutcome(BaseAgentResult):
    decision: Literal["generated", "fallback", "escalate"]
    source_type: str
    research_space_id: str
    seed_entity_id: str
    proposed_relations: list[ProposedRelation] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)
    shadow_mode: bool = True
    agent_run_id: str | None = None


class GraphConnectionRequest(SDKRequestModel):
    seed_entity_ids: list[str] = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    source_id: str | None = Field(default=None, min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    relation_types: list[str] | None = None
    max_depth: int = Field(default=2, ge=1, le=4)
    shadow_mode: bool = True
    pipeline_run_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_seed_entity_ids(self) -> GraphConnectionRequest:
        self.seed_entity_ids = [value.strip() for value in self.seed_entity_ids]
        if any(value == "" for value in self.seed_entity_ids):
            raise ValueError("seed_entity_ids cannot contain blank values")
        return self


class GraphConnectionRunResponse(SDKResponseModel):
    run: Run
    outcomes: list[GraphConnectionOutcome]


class OnboardingSection(SDKResponseModel):
    heading: str
    body: str


class OnboardingQuestion(SDKResponseModel):
    id: str
    prompt: str
    helper_text: str | None = None


class OnboardingSuggestedAction(SDKResponseModel):
    id: str
    label: str
    action_type: Literal["reply", "review"] = "reply"


class OnboardingArtifact(SDKResponseModel):
    artifact_key: str
    label: str
    kind: str


class OnboardingStatePatch(SDKResponseModel):
    thread_status: Literal["your_turn", "review_needed"]
    onboarding_status: Literal["awaiting_researcher_reply", "plan_ready"]
    pending_question_count: int = Field(ge=0)
    objective: str | None = None
    explored_questions: list[str] = Field(default_factory=list)
    pending_questions: list[str] = Field(default_factory=list)
    current_hypotheses: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_pending_question_count(self) -> OnboardingStatePatch:
        if self.pending_question_count != len(self.pending_questions):
            raise ValueError(
                "pending_question_count must match pending_questions length",
            )
        return self


class OnboardingAssistantMessage(BaseAgentResult):
    message_type: Literal["clarification_request", "plan_ready"]
    title: str
    summary: str
    sections: list[OnboardingSection] = Field(default_factory=list)
    questions: list[OnboardingQuestion] = Field(default_factory=list)
    suggested_actions: list[OnboardingSuggestedAction] = Field(default_factory=list)
    artifacts: list[OnboardingArtifact] = Field(default_factory=list)
    state_patch: OnboardingStatePatch
    agent_run_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ResearchState(SDKResponseModel):
    space_id: str
    objective: str | None = None
    current_hypotheses: list[str] = Field(default_factory=list)
    explored_questions: list[str] = Field(default_factory=list)
    pending_questions: list[str] = Field(default_factory=list)
    last_graph_snapshot_id: str | None = None
    active_schedules: list[str] = Field(default_factory=list)
    confidence_model: JSONObject = Field(default_factory=dict)
    budget_policy: JSONObject = Field(default_factory=dict)
    metadata: JSONObject = Field(default_factory=dict)
    created_at: str
    updated_at: str


class ResearchOnboardingStartRequest(SDKRequestModel):
    research_title: str = Field(min_length=1, max_length=100)
    primary_objective: str = Field(default="", max_length=4000)
    space_description: str = Field(default="", max_length=500)


class ResearchOnboardingReplyRequest(SDKRequestModel):
    thread_id: str = Field(min_length=1, max_length=100)
    message_id: str = Field(min_length=1, max_length=100)
    intent: str = Field(min_length=1, max_length=100)
    mode: str = Field(min_length=1, max_length=100)
    reply_text: str = Field(min_length=1, max_length=12000)
    reply_html: str = Field(default="", max_length=24000)
    attachments: list[JSONObject] = Field(default_factory=list)
    contextual_anchor: JSONObject | None = None


class ResearchOnboardingRunResponse(SDKResponseModel):
    run: Run
    research_state: ResearchState
    intake_artifact: JSONObject
    assistant_message: OnboardingAssistantMessage


class ResearchOnboardingTurnResponse(SDKResponseModel):
    run: Run
    research_state: ResearchState
    assistant_message: OnboardingAssistantMessage


class DocumentSummary(SDKResponseModel):
    id: str
    space_id: str
    created_by: str
    title: str
    source_type: Literal["pdf", "text"]
    filename: str | None = None
    media_type: str
    sha256: str
    byte_size: int = Field(ge=0)
    page_count: int | None = Field(default=None, ge=0)
    text_excerpt: str
    ingestion_run_id: str
    last_enrichment_run_id: str | None = None
    last_extraction_run_id: str | None = None
    enrichment_status: str
    extraction_status: str
    metadata: JSONObject = Field(default_factory=dict)
    created_at: str
    updated_at: str


class DocumentDetail(DocumentSummary):
    text_content: str


class DocumentListResponse(SDKResponseModel):
    documents: list[DocumentSummary]
    total: int


class SubmitTextDocumentRequest(SDKRequestModel):
    title: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=120000)
    metadata: JSONObject = Field(default_factory=dict)


class DocumentIngestionResponse(SDKResponseModel):
    run: Run
    document: DocumentDetail


class Proposal(SDKResponseModel):
    id: str
    space_id: str
    run_id: str
    proposal_type: str
    source_kind: str
    source_key: str
    document_id: str | None = None
    title: str
    summary: str
    status: str
    confidence: float = Field(ge=0.0, le=1.0)
    ranking_score: float = Field(ge=0.0, le=1.0)
    reasoning_path: JSONObject = Field(default_factory=dict)
    evidence_bundle: list[JSONObject] = Field(default_factory=list)
    payload: JSONObject = Field(default_factory=dict)
    metadata: JSONObject = Field(default_factory=dict)
    decision_reason: str | None = None
    decided_at: str | None = None
    created_at: str
    updated_at: str


class ReviewQueueItem(SDKResponseModel):
    id: str
    item_type: str
    resource_id: str
    kind: str
    status: str
    title: str
    summary: str
    priority: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    ranking_score: float | None = Field(default=None, ge=0.0, le=1.0)
    run_id: str | None = None
    document_id: str | None = None
    source_family: str
    source_kind: str
    source_key: str
    linked_resource: JSONObject | None = None
    available_actions: list[str] = Field(default_factory=list)
    payload: JSONObject = Field(default_factory=dict)
    metadata: JSONObject = Field(default_factory=dict)
    evidence_bundle: list[JSONObject] = Field(default_factory=list)
    decision_reason: str | None = None
    decided_at: str | None = None
    created_at: str
    updated_at: str


class ProposalListResponse(SDKResponseModel):
    proposals: list[Proposal]
    total: int


class ReviewQueueListResponse(SDKResponseModel):
    items: list[ReviewQueueItem]
    total: int
    offset: int
    limit: int


class ReviewQueueActionRequest(SDKRequestModel):
    action: str = Field(min_length=1, max_length=64)
    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    metadata: JSONObject = Field(default_factory=dict)


class DocumentExtractionResponse(SDKResponseModel):
    run: Run
    document: DocumentDetail
    proposals: list[Proposal] = Field(default_factory=list)
    proposal_count: int = Field(ge=0)
    review_items: list[ReviewQueueItem] = Field(default_factory=list)
    review_item_count: int = Field(default=0, ge=0)
    skipped_candidates: list[JSONObject] = Field(default_factory=list)


class ChatSession(SDKResponseModel):
    id: str
    space_id: str
    title: str
    created_by: str
    last_run_id: str | None = None
    status: str
    created_at: str
    updated_at: str


class ChatMessage(SDKResponseModel):
    id: str
    session_id: str
    role: str
    content: str
    run_id: str | None = None
    metadata: JSONObject = Field(default_factory=dict)
    created_at: str
    updated_at: str


class ChatSessionDetailResponse(SDKResponseModel):
    session: ChatSession
    messages: list[ChatMessage]


class ChatGraphWriteCandidate(SDKResponseModel):
    source_entity_id: str
    relation_type: str
    target_entity_id: str
    evidence_entity_ids: list[str] = Field(default_factory=list)
    title: str | None = None
    summary: str | None = None
    rationale: str | None = None
    ranking_score: float | None = Field(default=None, ge=0.0, le=1.0)
    ranking_metadata: JSONObject | None = None


class GraphChatEvidenceItem(SDKResponseModel):
    entity_id: str
    entity_type: str
    display_label: str | None = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    support_summary: str
    explanation: str


class GraphChatVerification(SDKResponseModel):
    status: Literal["verified", "needs_review", "unverified"]
    reason: str
    grounded_match_count: int = Field(ge=0)
    top_relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    warning_count: int = Field(ge=0)
    allows_graph_write: bool


class GraphChatLiteratureRefresh(SDKResponseModel):
    source: Literal["pubmed"]
    trigger_reason: Literal["needs_review", "unverified"]
    search_job_id: str
    query_preview: str
    total_results: int = Field(ge=0)
    preview_records: list[JSONObject] = Field(default_factory=list)


class GraphChatResult(SDKResponseModel):
    answer_text: str
    chat_summary: str
    evidence_bundle: list[GraphChatEvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    verification: GraphChatVerification
    graph_write_candidates: list[ChatGraphWriteCandidate] = Field(default_factory=list)
    fresh_literature: GraphChatLiteratureRefresh | None = None
    search: GraphSearchResult


class ChatMessageRunResponse(SDKResponseModel):
    run: Run
    session: ChatSession
    user_message: ChatMessage
    assistant_message: ChatMessage
    result: GraphChatResult


class ChatMessageAcceptedResponse(SDKResponseModel):
    run: Run
    session: ChatSession
    progress_url: str
    events_url: str
    workspace_url: str
    artifacts_url: str
    stream_url: str


class ChatGraphWriteProposalResponse(SDKResponseModel):
    run: Run
    session: ChatSession
    proposals: list[Proposal]
    proposal_count: int = Field(ge=0)


class PubMedSearchParameters(SDKRequestModel):
    gene_symbol: str | None = None
    search_term: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    publication_types: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    sort_by: Literal[
        "relevance",
        "publication_date",
        "author",
        "journal",
        "title",
    ] = "relevance"
    max_results: int = Field(default=100, ge=1, le=1000)
    additional_terms: str | None = None


class PubMedSearchRequest(SDKRequestModel):
    parameters: PubMedSearchParameters


class PubMedSearchJob(SDKResponseModel):
    id: str
    owner_id: str
    session_id: str | None = None
    provider: Literal["pubmed"]
    status: Literal["queued", "running", "completed", "failed"]
    query_preview: str
    parameters: PubMedSearchParameters
    total_results: int = Field(ge=0)
    result_metadata: JSONObject = Field(default_factory=dict)
    error_message: str | None = None
    storage_key: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class ChatDocumentWorkflowResponse(SDKResponseModel):
    ingestion: DocumentIngestionResponse
    extraction: DocumentExtractionResponse
    chat: ChatMessageRunResponse


__all__ = [
    "AuthContextResponse",
    "AuthCredentialResponse",
    "AuthenticatedUser",
    "Artifact",
    "ArtifactListResponse",
    "BaseAgentResult",
    "BootstrapApiKeyRequest",
    "ChatDocumentWorkflowResponse",
    "ChatGraphWriteCandidate",
    "ChatGraphWriteProposalResponse",
    "ChatMessageAcceptedResponse",
    "ChatMessage",
    "ChatMessageRunResponse",
    "ChatSession",
    "ChatSessionDetailResponse",
    "CreateApiKeyRequest",
    "CreateSpaceRequest",
    "DocumentDetail",
    "DocumentExtractionResponse",
    "DocumentIngestionResponse",
    "DocumentListResponse",
    "DocumentSummary",
    "EvidenceChainItem",
    "EvidenceItem",
    "GraphSearchAssessment",
    "GraphChatEvidenceItem",
    "GraphChatLiteratureRefresh",
    "GraphChatResult",
    "GraphChatVerification",
    "GraphConnectionOutcome",
    "GraphConnectionRequest",
    "GraphConnectionRunResponse",
    "GraphSearchRequest",
    "GraphSearchResult",
    "GraphSearchResultEntry",
    "GraphSearchRunResponse",
    "HealthResponse",
    "IssuedApiKey",
    "OnboardingArtifact",
    "OnboardingAssistantMessage",
    "OnboardingQuestion",
    "OnboardingSection",
    "OnboardingStatePatch",
    "OnboardingSuggestedAction",
    "Proposal",
    "ProposalListResponse",
    "ProposedRelation",
    "PubMedSearchJob",
    "PubMedSearchParameters",
    "PubMedSearchRequest",
    "RejectedCandidate",
    "ResearchOnboardingReplyRequest",
    "ResearchOnboardingRunResponse",
    "ResearchOnboardingStartRequest",
    "ResearchOnboardingTurnResponse",
    "ResearchSpace",
    "ResearchSpaceListResponse",
    "ResearchState",
    "Run",
    "RunListResponse",
    "SubmitTextDocumentRequest",
    "Workspace",
]

_MODEL_TYPES = (
    HealthResponse,
    AuthenticatedUser,
    IssuedApiKey,
    AuthContextResponse,
    AuthCredentialResponse,
    ResearchSpace,
    ResearchSpaceListResponse,
    BootstrapApiKeyRequest,
    CreateApiKeyRequest,
    CreateSpaceRequest,
    Run,
    RunListResponse,
    Artifact,
    ArtifactListResponse,
    Workspace,
    EvidenceItem,
    BaseAgentResult,
    GraphSearchAssessment,
    EvidenceChainItem,
    GraphSearchResultEntry,
    GraphSearchResult,
    GraphSearchRequest,
    GraphSearchRunResponse,
    ProposedRelation,
    RejectedCandidate,
    GraphConnectionOutcome,
    GraphConnectionRequest,
    GraphConnectionRunResponse,
    OnboardingSection,
    OnboardingQuestion,
    OnboardingSuggestedAction,
    OnboardingArtifact,
    OnboardingStatePatch,
    OnboardingAssistantMessage,
    ResearchState,
    ResearchOnboardingStartRequest,
    ResearchOnboardingReplyRequest,
    ResearchOnboardingRunResponse,
    ResearchOnboardingTurnResponse,
    DocumentSummary,
    DocumentDetail,
    DocumentListResponse,
    SubmitTextDocumentRequest,
    DocumentIngestionResponse,
    Proposal,
    ProposalListResponse,
    DocumentExtractionResponse,
    ChatSession,
    ChatMessage,
    ChatMessageAcceptedResponse,
    ChatSessionDetailResponse,
    ChatGraphWriteCandidate,
    GraphChatEvidenceItem,
    GraphChatVerification,
    GraphChatLiteratureRefresh,
    GraphChatResult,
    ChatMessageRunResponse,
    ChatGraphWriteProposalResponse,
    PubMedSearchParameters,
    PubMedSearchRequest,
    PubMedSearchJob,
    ChatDocumentWorkflowResponse,
)

for _model in _MODEL_TYPES:
    _model.model_rebuild(
        _types_namespace={
            "JSONObject": JSONObject,
            "JSONValue": JSONValue,
        },
    )
