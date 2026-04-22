"""Service-local graph agent contracts for graph-harness workflows."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    assessment_confidence,
)


class EvidenceSourceType(str, Enum):
    """Types of evidence sources that can support agent decisions."""

    TOOL = "tool"
    DATABASE = "db"
    PAPER = "paper"
    WEB = "web"
    NOTE = "note"
    API = "api"


class EvidenceItem(BaseModel):
    """Structured evidence supporting a graph-harness agent decision."""

    source_type: Literal["tool", "db", "paper", "web", "note", "api"]
    locator: str = Field(
        ...,
        description="DOI, URL, query-id, row-id, run-id, or other unique identifier",
    )
    excerpt: str = Field(
        ...,
        description="Relevant excerpt or summary from the source",
    )
    relevance: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance score of this evidence to the decision",
    )


class BaseAgentContract(BaseModel):
    """Base contract for graph-harness agent outputs."""

    confidence_score: float = Field(..., ge=0.0, le=1.0)
    rationale: str
    evidence: list[EvidenceItem] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True)


class EvidenceBackedAgentContract(BaseModel):
    """Base contract for service-local evidence-backed agent outputs."""

    rationale: str
    evidence: list[EvidenceItem] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True)


class GraphSearchSupportBand(str, Enum):
    """Coarse support strength for graph-search results."""

    INSUFFICIENT = "INSUFFICIENT"
    TENTATIVE = "TENTATIVE"
    SUPPORTED = "SUPPORTED"
    STRONG = "STRONG"


class GraphSearchGroundingLevel(str, Enum):
    """How directly a graph-search result is grounded in graph evidence."""

    NONE = "NONE"
    ENTITY = "ENTITY"
    RELATION = "RELATION"
    OBSERVATION = "OBSERVATION"
    AGGREGATED = "AGGREGATED"


class GraphSearchAssessment(BaseModel):
    """Structured qualitative assessment for graph-search results and evidence."""

    support_band: GraphSearchSupportBand = Field(
        ...,
        description="Coarse support strength for the search result.",
    )
    grounding_level: GraphSearchGroundingLevel = Field(
        ...,
        description="How directly the result is grounded in graph evidence.",
    )
    confidence_rationale: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Short explanation for why this assessment was chosen.",
    )

    model_config = ConfigDict(use_enum_values=True)


_GRAPH_SEARCH_STRONG_THRESHOLD = 0.85
_GRAPH_SEARCH_SUPPORTED_THRESHOLD = 0.7
_GRAPH_SEARCH_TENTATIVE_THRESHOLD = 0.45
_GRAPH_SEARCH_NONE_GROUNDING_CAP = 0.4


def build_graph_search_assessment_from_confidence(
    confidence: float,
    *,
    confidence_rationale: str,
    grounding_level: GraphSearchGroundingLevel,
) -> GraphSearchAssessment:
    """Convert a legacy numeric score into a qualitative graph-search assessment."""
    if confidence >= _GRAPH_SEARCH_STRONG_THRESHOLD:
        support_band = GraphSearchSupportBand.STRONG
    elif confidence >= _GRAPH_SEARCH_SUPPORTED_THRESHOLD:
        support_band = GraphSearchSupportBand.SUPPORTED
    elif confidence >= _GRAPH_SEARCH_TENTATIVE_THRESHOLD:
        support_band = GraphSearchSupportBand.TENTATIVE
    else:
        support_band = GraphSearchSupportBand.INSUFFICIENT
    return GraphSearchAssessment(
        support_band=support_band,
        grounding_level=grounding_level,
        confidence_rationale=confidence_rationale,
    )


def graph_search_assessment_confidence(assessment: GraphSearchAssessment) -> float:
    """Derive a deterministic numeric weight from a qualitative assessment."""
    base_weight = {
        GraphSearchSupportBand.INSUFFICIENT: 0.2,
        GraphSearchSupportBand.TENTATIVE: 0.45,
        GraphSearchSupportBand.SUPPORTED: 0.7,
        GraphSearchSupportBand.STRONG: 0.9,
    }[GraphSearchSupportBand(assessment.support_band)]
    grounding_cap = (
        _GRAPH_SEARCH_NONE_GROUNDING_CAP
        if GraphSearchGroundingLevel(assessment.grounding_level)
        == GraphSearchGroundingLevel.NONE
        else 1.0
    )
    return max(0.0, min(base_weight, grounding_cap, 1.0))


def graph_search_grounding_level_from_counts(
    *,
    relation_count: int,
    observation_count: int,
) -> GraphSearchGroundingLevel:
    """Infer a grounding level from the available graph evidence counts."""
    if relation_count > 0 and observation_count > 0:
        return GraphSearchGroundingLevel.AGGREGATED
    if observation_count > 0:
        return GraphSearchGroundingLevel.OBSERVATION
    if relation_count > 0:
        return GraphSearchGroundingLevel.RELATION
    return GraphSearchGroundingLevel.ENTITY


class EvidenceChainItem(BaseModel):
    """One provenance-linked evidence reference backing a search result."""

    provenance_id: str | None = Field(default=None, min_length=1, max_length=64)
    relation_id: str | None = Field(default=None, min_length=1, max_length=64)
    observation_id: str | None = Field(default=None, min_length=1, max_length=64)
    evidence_tier: str | None = Field(default=None, min_length=1, max_length=32)
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
    evidence_sentence: str | None = Field(default=None, max_length=2000)
    source_ref: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _normalize_assessment(self) -> EvidenceChainItem:
        if self.assessment is None:
            source_confidence = self.confidence if self.confidence is not None else 0.45
            grounding_level = (
                GraphSearchGroundingLevel.RELATION
                if self.relation_id is not None
                else (
                    GraphSearchGroundingLevel.OBSERVATION
                    if self.observation_id is not None
                    else GraphSearchGroundingLevel.NONE
                )
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


class GraphSearchResultEntry(BaseModel):
    """One ranked graph search result."""

    entity_id: str = Field(..., min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=64)
    display_label: str | None = Field(default=None, max_length=512)
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    assessment: GraphSearchAssessment | None = Field(
        default=None,
        description="Qualitative assessment for the search result.",
    )
    matching_observation_ids: list[str] = Field(default_factory=list)
    matching_relation_ids: list[str] = Field(default_factory=list)
    evidence_chain: list[EvidenceChainItem] = Field(default_factory=list)
    explanation: str = Field(..., min_length=1, max_length=4000)
    support_summary: str = Field(..., min_length=1, max_length=1000)

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


class GraphSearchContract(EvidenceBackedAgentContract):
    """Contract for graph-search outputs."""

    decision: Literal["generated", "fallback", "escalate"]
    evidence: list[EvidenceItem] = Field(default_factory=list)
    research_space_id: str = Field(..., min_length=1, max_length=64)
    original_query: str = Field(..., min_length=1, max_length=2000)
    interpreted_intent: str = Field(..., min_length=1, max_length=2000)
    query_plan_summary: str = Field(..., min_length=1, max_length=4000)
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
    executed_path: Literal["deterministic", "agent", "agent_fallback"] = Field(
        default="deterministic",
    )
    warnings: list[str] = Field(default_factory=list)
    agent_run_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _normalize_assessment(self) -> GraphSearchContract:
        if self.assessment is None:
            if self.results:
                mean_relevance = sum(
                    result.relevance_score for result in self.results
                ) / len(self.results)
                grounding_level = (
                    GraphSearchGroundingLevel.AGGREGATED
                    if any(result.evidence_chain for result in self.results)
                    else GraphSearchGroundingLevel.ENTITY
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
                    grounding_level=GraphSearchGroundingLevel.NONE,
                )
            else:
                self.assessment = build_graph_search_assessment_from_confidence(
                    0.2,
                    confidence_rationale="No ranked graph-search results were produced.",
                    grounding_level=GraphSearchGroundingLevel.NONE,
                )
        self.confidence_score = graph_search_assessment_confidence(self.assessment)
        return self


class OnboardingSection(BaseModel):
    """One channel-neutral content section for onboarding assistant output."""

    heading: str = Field(..., min_length=1, max_length=160)
    body: str = Field(..., min_length=1, max_length=4000)

    model_config = ConfigDict(extra="forbid")


class OnboardingQuestion(BaseModel):
    """One explicit clarification question emitted by the onboarding agent."""

    id: str = Field(..., min_length=1, max_length=64)
    prompt: str = Field(..., min_length=1, max_length=512)
    helper_text: str | None = Field(default=None, max_length=1000)
    suggested_answers: list[OnboardingSuggestedAnswer] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class OnboardingSuggestedAction(BaseModel):
    """One next-step action suggestion associated with an onboarding message."""

    id: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=80)
    action_type: Literal["reply", "review"] = "reply"

    model_config = ConfigDict(extra="forbid")


class OnboardingSuggestedAnswer(BaseModel):
    """One quick-reply answer suggestion for a clarification question."""

    id: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=160)

    model_config = ConfigDict(extra="forbid")


class OnboardingArtifact(BaseModel):
    """One artifact reference surfaced to the inbox runtime."""

    artifact_key: str = Field(..., min_length=1, max_length=128)
    label: str = Field(..., min_length=1, max_length=120)
    kind: str = Field(..., min_length=1, max_length=64)

    model_config = ConfigDict(extra="forbid")


class OnboardingStatePatch(BaseModel):
    """Structured research-state patch returned by the onboarding agent."""

    thread_status: Literal["your_turn", "review_needed"]
    onboarding_status: Literal["awaiting_researcher_reply", "plan_ready"]
    pending_question_count: int = Field(..., ge=0)
    objective: str | None = Field(default=None, max_length=4000)
    seed_terms: list[str] = Field(default_factory=list)
    explored_questions: list[str] = Field(default_factory=list)
    pending_questions: list[str] = Field(default_factory=list)
    current_hypotheses: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_patch(self) -> OnboardingStatePatch:
        if self.pending_question_count != len(self.pending_questions):
            msg = "pending_question_count must match pending_questions length."
            raise ValueError(msg)
        if self.thread_status == "review_needed":
            if self.onboarding_status != "plan_ready":
                msg = "review_needed requires onboarding_status='plan_ready'."
                raise ValueError(msg)
            if self.pending_questions:
                msg = "review_needed state cannot retain pending questions."
                raise ValueError(msg)
        return self


def _extract_onboarding_question_prompts(raw_questions: list[object]) -> list[str]:
    prompts: list[str] = []
    for question in raw_questions:
        prompt: str | None = None
        if isinstance(question, dict):
            raw_prompt = question.get("prompt")
            if isinstance(raw_prompt, str):
                prompt = raw_prompt
        elif isinstance(question, OnboardingQuestion):
            prompt = question.prompt
        if isinstance(prompt, str) and prompt.strip():
            prompts.append(prompt.strip())
    return prompts


def _normalize_onboarding_state_patch_payload(
    raw_state_patch: object,
    *,
    pending_question_prompts: list[str],
) -> dict[str, object] | None:
    state_patch: dict[str, object] | None = None
    if isinstance(raw_state_patch, dict):
        state_patch = dict(raw_state_patch)
    elif isinstance(raw_state_patch, OnboardingStatePatch):
        state_patch = raw_state_patch.model_dump(mode="python")
    if state_patch is None:
        return None

    state_patch["thread_status"] = "your_turn"
    state_patch["onboarding_status"] = "awaiting_researcher_reply"
    if not isinstance(state_patch.get("pending_questions"), list) or not [
        value
        for value in state_patch.get("pending_questions", [])
        if isinstance(value, str) and value.strip()
    ]:
        state_patch["pending_questions"] = pending_question_prompts
    pending_questions = state_patch.get("pending_questions")
    if isinstance(pending_questions, list):
        state_patch["pending_question_count"] = len(
            [
                value
                for value in pending_questions
                if isinstance(value, str) and value.strip()
            ],
        )
    return state_patch


class OnboardingAssistantContract(BaseAgentContract):
    """Typed Artana contract for research onboarding assistant turns."""

    message_type: Literal["clarification_request", "plan_ready"]
    title: str = Field(..., min_length=1, max_length=160)
    summary: str = Field(..., min_length=1, max_length=1200)
    sections: list[OnboardingSection] = Field(default_factory=list)
    questions: list[OnboardingQuestion] = Field(default_factory=list)
    suggested_actions: list[OnboardingSuggestedAction] = Field(default_factory=list)
    artifacts: list[OnboardingArtifact] = Field(default_factory=list)
    state_patch: OnboardingStatePatch
    agent_run_id: str | None = Field(default=None, max_length=128)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _coerce_plan_ready_with_questions(
        cls,
        data: object,
    ) -> object:
        if not isinstance(data, dict):
            return data
        message_type = data.get("message_type")
        raw_questions = data.get("questions")
        if message_type != "plan_ready" or not isinstance(raw_questions, list):
            return data
        if not raw_questions:
            return data

        normalized = dict(data)
        normalized["message_type"] = "clarification_request"
        raw_warnings = normalized.get("warnings")
        warnings = (
            [warning for warning in raw_warnings if isinstance(warning, str)]
            if isinstance(raw_warnings, list)
            else []
        )
        warning_message = (
            "Normalized plan_ready output with open questions into "
            "clarification_request."
        )
        if warning_message not in warnings:
            warnings.append(warning_message)
        normalized["warnings"] = warnings

        state_patch = _normalize_onboarding_state_patch_payload(
            normalized.get("state_patch"),
            pending_question_prompts=_extract_onboarding_question_prompts(
                raw_questions,
            ),
        )
        if state_patch is not None:
            normalized["state_patch"] = state_patch

        return normalized

    @model_validator(mode="after")
    def _validate_message_type_constraints(self) -> OnboardingAssistantContract:
        if self.message_type == "clarification_request" and not self.questions:
            msg = "clarification_request output must include at least one question."
            raise ValueError(msg)
        if self.message_type == "plan_ready" and self.questions:
            msg = "plan_ready output cannot include open questions."
            raise ValueError(msg)
        return self


class ProposedRelation(BaseModel):
    """One relation candidate proposed by graph-level reasoning."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_id: str = Field(..., min_length=1, max_length=64)
    assessment: FactAssessment = Field(
        ...,
        description="Qualitative assessment for this proposed relation.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Derived backend weight normalized from assessment.",
    )
    evidence_summary: str = Field(..., min_length=1, max_length=2000)
    evidence_tier: Literal["COMPUTATIONAL"] = "COMPUTATIONAL"
    supporting_provenance_ids: list[str] = Field(default_factory=list)
    supporting_document_count: int = Field(default=0, ge=0)
    reasoning: str = Field(..., min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _normalize_confidence(self) -> ProposedRelation:
        self.confidence = assessment_confidence(self.assessment)
        return self


class RejectedCandidate(BaseModel):
    """One relation candidate that was considered but not proposed."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_id: str = Field(..., min_length=1, max_length=64)
    assessment: FactAssessment = Field(
        ...,
        description="Qualitative assessment explaining why the candidate was rejected.",
    )
    reason: str = Field(..., min_length=1, max_length=512)
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Derived backend weight normalized from assessment.",
    )

    @model_validator(mode="after")
    def _normalize_confidence(self) -> RejectedCandidate:
        self.confidence = assessment_confidence(self.assessment)
        return self


class GraphConnectionContract(BaseAgentContract):
    """Contract for graph-connection outputs."""

    decision: Literal["generated", "fallback", "escalate"]
    source_type: str = Field(..., min_length=1, max_length=64)
    research_space_id: str = Field(..., min_length=1, max_length=64)
    seed_entity_id: str = Field(..., min_length=1, max_length=64)
    proposed_relations: list[ProposedRelation] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)
    shadow_mode: bool = True
    agent_run_id: str | None = None


ProposedRelation.model_rebuild()
RejectedCandidate.model_rebuild()
GraphConnectionContract.model_rebuild()
GraphSearchContract.model_rebuild()


__all__ = [
    "BaseAgentContract",
    "EvidenceChainItem",
    "EvidenceItem",
    "EvidenceSourceType",
    "GraphConnectionContract",
    "GraphSearchAssessment",
    "GraphSearchGroundingLevel",
    "GraphSearchContract",
    "GraphSearchResultEntry",
    "OnboardingArtifact",
    "OnboardingAssistantContract",
    "OnboardingQuestion",
    "OnboardingSection",
    "OnboardingStatePatch",
    "OnboardingSuggestedAnswer",
    "OnboardingSuggestedAction",
    "ProposedRelation",
    "RejectedCandidate",
]
