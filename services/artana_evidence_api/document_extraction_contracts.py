"""Typed contracts for document extraction and review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from artana_evidence_api.types.common import JSONObject

FactualSupportScale = Literal["strong", "moderate", "tentative", "unsupported"]
GoalRelevanceScale = Literal[
    "direct",
    "supporting",
    "peripheral",
    "off_target",
    "unscoped",
]
PriorityScale = Literal["prioritize", "review", "background", "ignore"]
RelationGovernanceStatus = Literal["canonical", "requires_relation_review"]
CurieSource = Literal["none", "model", "verified_linker"]
PdfTextExtractionOutcome = Literal[
    "text",
    "no_text_image_likely",
    "partial_text_ocr_needed",
    "no_pages",
]

FACTUAL_SUPPORT_SCORES: dict[FactualSupportScale, float] = {
    "strong": 0.92,
    "moderate": 0.72,
    "tentative": 0.46,
    "unsupported": 0.18,
}
GOAL_RELEVANCE_SCORES: dict[GoalRelevanceScale, float] = {
    "direct": 0.96,
    "supporting": 0.72,
    "peripheral": 0.38,
    "off_target": 0.12,
    "unscoped": 0.5,
}
PRIORITY_SCORES: dict[PriorityScale, float] = {
    "prioritize": 0.96,
    "review": 0.72,
    "background": 0.36,
    "ignore": 0.08,
}


class LLMRelationLike(Protocol):
    """Typed relation payload returned by an LLM extraction schema."""

    subject: str
    subject_curie: str | None
    relation_type: str
    proposed_relation_type: str | None
    new_relation_type_rationale: str | None
    object: str
    object_curie: str | None
    sentence: str


class LLMExtractionResultLike(Protocol):
    """Typed extraction result returned by an LLM extraction schema."""

    relations: list[LLMRelationLike]


class ProposalReviewItemLike(Protocol):
    """Typed review item returned by a proposal-review schema."""

    index: int
    factual_support: FactualSupportScale
    goal_relevance: GoalRelevanceScale
    priority: PriorityScale
    rationale: str
    factual_rationale: str
    relevance_rationale: str


class ProposalReviewResultLike(Protocol):
    """Typed review result returned by a proposal-review schema."""

    reviews: list[ProposalReviewItemLike]


@dataclass(frozen=True, slots=True)
class ExtractedRelationCandidate:
    """One relation-like statement extracted from document text."""

    subject_label: str
    relation_type: str
    object_label: str
    sentence: str
    subject_curie: str | None = None
    object_curie: str | None = None
    subject_curie_source: CurieSource = "none"
    object_curie_source: CurieSource = "none"
    proposed_relation_type: str | None = None
    new_relation_type_rationale: str | None = None
    relation_governance_status: RelationGovernanceStatus = "canonical"

    @property
    def trusted_evidence_eligible(self) -> bool:
        """Return whether this candidate can be treated as a trusted graph edge."""

        return self.relation_governance_status == "canonical"


@dataclass(frozen=True, slots=True)
class DocumentTextExtraction:
    """Normalized extracted text and metadata for one uploaded PDF."""

    text_content: str
    page_count: int | None
    extraction_outcome: PdfTextExtractionOutcome = "text"
    pages_without_text: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentExtractionReviewContext:
    """Research-goal context used to review extracted claims."""

    objective: str | None
    current_hypotheses: tuple[str, ...] = ()
    pending_questions: tuple[str, ...] = ()
    explored_questions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentProposalReview:
    """One categorical review for an extracted proposal."""

    factual_support: FactualSupportScale
    goal_relevance: GoalRelevanceScale
    priority: PriorityScale
    rationale: str
    factual_rationale: str
    relevance_rationale: str
    method: str
    model_id: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentProposalReviewDiagnostics:
    """Runtime diagnostics for the proposal-review LLM pass."""

    llm_review_status: Literal[
        "not_needed",
        "completed",
        "unavailable",
        "fallback_error",
    ]
    llm_review_error: str | None = None

    def as_metadata(self) -> JSONObject:
        """Serialize diagnostics into JSON-safe metadata."""

        payload: JSONObject = {
            "llm_review_status": self.llm_review_status,
            "llm_review_attempted": self.llm_review_status
            in {"completed", "fallback_error"},
            "llm_review_failed": self.llm_review_status
            in {"unavailable", "fallback_error"},
        }
        if self.llm_review_error is not None:
            payload["llm_review_error"] = self.llm_review_error
        return payload


@dataclass(frozen=True, slots=True)
class DocumentCandidateExtractionDiagnostics:
    """Runtime diagnostics for relation-candidate discovery."""

    llm_candidate_status: Literal[
        "not_needed",
        "completed",
        "llm_empty",
        "fallback",
        "fallback_error",
        "unavailable",
    ]
    llm_candidate_error: str | None = None
    llm_candidate_count: int = 0
    fallback_candidate_count: int = 0
    pruned_generic_relation_count: int = 0
    quality_filtered_candidate_count: int = 0
    llm_extraction_chunk_count: int = 0
    llm_extraction_text_char_count: int = 0

    @property
    def agent_extraction_completed(self) -> bool:
        """Return whether the agent path completed relation extraction."""

        return self.llm_candidate_status == "completed"

    @property
    def fallback_output_used(self) -> bool:
        """Return whether candidates came from a fallback/non-agent source."""

        return (
            self.llm_candidate_status
            in {"fallback", "fallback_error", "unavailable"}
            or self.fallback_candidate_count > 0
        )

    @property
    def trusted_evidence_eligible(self) -> bool:
        """Return whether candidate output may enter trusted-evidence gates."""

        return self.agent_extraction_completed and not self.fallback_output_used

    def as_metadata(self) -> JSONObject:
        """Serialize diagnostics into JSON-safe metadata."""

        payload: JSONObject = {
            "llm_candidate_status": self.llm_candidate_status,
            "llm_candidate_attempted": self.llm_candidate_status
            in {"completed", "llm_empty", "fallback", "fallback_error"},
            "llm_candidate_failed": self.llm_candidate_status
            in {"fallback", "fallback_error", "unavailable"},
            "agent_extraction_completed": self.agent_extraction_completed,
            "fallback_output_used": self.fallback_output_used,
            "trusted_evidence_eligible": self.trusted_evidence_eligible,
        }
        if self.llm_candidate_count > 0:
            payload["llm_candidate_count"] = self.llm_candidate_count
        if self.fallback_candidate_count > 0:
            payload["fallback_candidate_count"] = self.fallback_candidate_count
        if self.pruned_generic_relation_count > 0:
            payload["pruned_generic_relation_count"] = (
                self.pruned_generic_relation_count
            )
        if self.quality_filtered_candidate_count > 0:
            payload["quality_filtered_candidate_count"] = (
                self.quality_filtered_candidate_count
            )
        if self.llm_extraction_chunk_count > 0:
            payload["llm_extraction_chunk_count"] = self.llm_extraction_chunk_count
        if self.llm_extraction_text_char_count > 0:
            payload["llm_extraction_text_char_count"] = (
                self.llm_extraction_text_char_count
            )
        if self.llm_candidate_error is not None:
            payload["llm_candidate_error"] = self.llm_candidate_error
        return payload


__all__ = [
    "DocumentCandidateExtractionDiagnostics",
    "DocumentExtractionReviewContext",
    "DocumentProposalReview",
    "DocumentProposalReviewDiagnostics",
    "DocumentTextExtraction",
    "ExtractedRelationCandidate",
    "FACTUAL_SUPPORT_SCORES",
    "FactualSupportScale",
    "CurieSource",
    "GOAL_RELEVANCE_SCORES",
    "GoalRelevanceScale",
    "LLMExtractionResultLike",
    "LLMRelationLike",
    "PRIORITY_SCORES",
    "PriorityScale",
    "ProposalReviewItemLike",
    "ProposalReviewResultLike",
    "RelationGovernanceStatus",
    "PdfTextExtractionOutcome",
]
