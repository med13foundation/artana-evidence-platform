"""Typed contracts for document extraction and review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, cast

from artana_evidence_api.types.common import JSONObject, json_value

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        ClaimFrame,
        ClaimQualifier,
        ClaimSourceMeasurement,
        EpistemicStatus,
        Polarity,
    )

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
RelationReviewStatus = Literal["candidate", "review_only"]
ClaimFramingDecisionValue = Literal[
    "SINGLE_FRAME",
    "MULTIPLE_VALID_FRAMES",
    "AMBIGUOUS",
    "ABSTAIN",
]
ClaimExtractionRoutingStatus = Literal[
    "not_run",
    "complete",
    "candidate_overflow",
    "semantic_incomplete",
]
_CLAIM_EXTRACTION_ROUTING_STATUSES = frozenset(
    {"not_run", "complete", "candidate_overflow", "semantic_incomplete"},
)


def normalize_claim_extraction_routing_status(
    value: object,
) -> ClaimExtractionRoutingStatus:
    """Read a closed routing status from compatibility-list telemetry."""

    if isinstance(value, str) and value in _CLAIM_EXTRACTION_ROUTING_STATUSES:
        return cast("ClaimExtractionRoutingStatus", value)
    return "not_run"


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
    polarity: Polarity
    epistemic_status: EpistemicStatus
    biological_or_variant_state: ClaimQualifier
    condition: ClaimQualifier
    population: ClaimQualifier
    intervention: ClaimQualifier
    comparator: ClaimQualifier
    outcome: ClaimQualifier
    study_design: ClaimQualifier
    treatment_setting: ClaimQualifier
    timeframe: ClaimQualifier
    threshold: ClaimQualifier
    source_measurements: list[ClaimSourceMeasurement]
    extraction_rationale: str


class LLMExtractionResultLike(Protocol):
    """Typed extraction result returned by an LLM extraction schema."""

    relations: list[LLMRelationLike]


class ProposalReviewItemLike(Protocol):
    """Typed review item returned by a proposal-review schema."""

    draft_ref: str
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
    review_status: RelationReviewStatus = "candidate"
    review_reason_codes: tuple[str, ...] = ()
    claim_frame: ClaimFrame | None = None
    framing_decision: ClaimFramingDecisionValue | None = None
    framing_decision_rationale: str | None = None

    @property
    def trusted_evidence_eligible(self) -> bool:
        """Return whether this candidate can be treated as a trusted graph edge."""

        return (
            self.relation_governance_status == "canonical"
            and self.review_status != "review_only"
            and self.claim_frame is not None
            and self.claim_frame.is_positive_projection_eligible
            and self.framing_decision == "SINGLE_FRAME"
            and isinstance(self.framing_decision_rationale, str)
            and bool(self.framing_decision_rationale.strip())
        )


@dataclass(frozen=True, slots=True)
class ClaimExtractionLineage:
    """Production-visible join from inventory unit to audited framing output."""

    inventory_id: str
    source_sha256: str
    source_start: int
    source_end: int
    claim_local_source_start: int
    claim_local_source_end: int
    inventory_payload: dict[str, object]
    framing_decision: ClaimFramingDecisionValue
    candidates: tuple[ExtractedRelationCandidate, ...]
    decision_rationale: str
    framing_attempt: dict[str, object]
    raw_agent_output: dict[str, object]

    def as_metadata(self) -> JSONObject:
        """Serialize complete claim-unit provenance for workflow metadata."""

        candidate_payloads = [
            {
                "subject_label": candidate.subject_label,
                "relation_type": candidate.relation_type,
                "object_label": candidate.object_label,
                "sentence": candidate.sentence,
                "review_status": candidate.review_status,
                "review_reason_codes": candidate.review_reason_codes,
                "claim_frame": (
                    candidate.claim_frame.model_dump(mode="json")
                    if candidate.claim_frame is not None
                    else None
                ),
            }
            for candidate in self.candidates
        ]
        return {
            "inventory_id": self.inventory_id,
            "source_sha256": self.source_sha256,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "claim_local_source_start": self.claim_local_source_start,
            "claim_local_source_end": self.claim_local_source_end,
            "inventory_payload": json_value(self.inventory_payload),
            "framing_decision": self.framing_decision,
            "candidates": json_value(candidate_payloads),
            "decision_rationale": self.decision_rationale,
            "framing_attempt": json_value(self.framing_attempt),
            "raw_agent_output": json_value(self.raw_agent_output),
        }


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
        "semantic_incomplete",
    ]
    llm_candidate_error: str | None = None
    llm_candidate_count: int = 0
    fallback_candidate_count: int = 0
    pruned_generic_relation_count: int = 0
    quality_filtered_candidate_count: int = 0
    llm_extraction_chunk_count: int = 0
    llm_extraction_text_char_count: int = 0
    claim_extraction_routing_status: ClaimExtractionRoutingStatus = "not_run"
    candidate_overflow_count: int = 0
    claim_lineage: tuple[ClaimExtractionLineage, ...] = ()
    raw_agent_outputs: tuple[dict[str, object], ...] = ()
    model_attempt_records: tuple[dict[str, object], ...] = ()
    inventory_binding_rejections: tuple[dict[str, object], ...] = ()

    @property
    def agent_extraction_completed(self) -> bool:
        """Return whether the agent path completed relation extraction."""

        return (
            self.llm_candidate_status == "completed"
            and self.claim_extraction_routing_status != "semantic_incomplete"
        )

    @property
    def fallback_output_used(self) -> bool:
        """Return whether candidates came from a fallback/non-agent source."""

        return (
            self.llm_candidate_status in {"fallback", "fallback_error", "unavailable"}
            or self.fallback_candidate_count > 0
        )

    @property
    def trusted_evidence_eligible(self) -> bool:
        """Return whether candidate output may enter trusted-evidence gates."""

        return (
            self.agent_extraction_completed
            and not self.fallback_output_used
            and self.claim_extraction_routing_status in {"not_run", "complete"}
            and self.candidate_overflow_count == 0
        )

    def as_metadata(self) -> JSONObject:
        """Serialize diagnostics into JSON-safe metadata."""

        payload: JSONObject = {
            "llm_candidate_status": self.llm_candidate_status,
            "llm_candidate_attempted": self.llm_candidate_status
            in {
                "completed",
                "llm_empty",
                "fallback",
                "fallback_error",
                "semantic_incomplete",
            },
            "llm_candidate_failed": self.llm_candidate_status
            in {"fallback", "fallback_error", "unavailable", "semantic_incomplete"},
            "agent_extraction_completed": self.agent_extraction_completed,
            "fallback_output_used": self.fallback_output_used,
            "trusted_evidence_eligible": self.trusted_evidence_eligible,
        }
        for field_name, value in (
            ("llm_candidate_count", self.llm_candidate_count),
            ("fallback_candidate_count", self.fallback_candidate_count),
            ("pruned_generic_relation_count", self.pruned_generic_relation_count),
            ("quality_filtered_candidate_count", self.quality_filtered_candidate_count),
            ("llm_extraction_chunk_count", self.llm_extraction_chunk_count),
            ("llm_extraction_text_char_count", self.llm_extraction_text_char_count),
        ):
            if value > 0:
                payload[field_name] = value
        if self.claim_extraction_routing_status != "not_run":
            payload["claim_extraction_routing_status"] = (
                self.claim_extraction_routing_status
            )
        if self.candidate_overflow_count > 0:
            payload["candidate_overflow_count"] = self.candidate_overflow_count
        if self.claim_lineage:
            payload["claim_lineage"] = [
                lineage.as_metadata() for lineage in self.claim_lineage
            ]
        if self.raw_agent_outputs:
            payload["raw_agent_outputs"] = json_value(self.raw_agent_outputs)
        if self.model_attempt_records:
            payload["model_attempt_records"] = json_value(
                self.model_attempt_records,
            )
        if self.inventory_binding_rejections:
            payload["inventory_binding_rejections"] = json_value(
                self.inventory_binding_rejections,
            )
        if self.llm_candidate_error is not None:
            payload["llm_candidate_error"] = self.llm_candidate_error
        return payload


__all__ = [
    "ClaimExtractionLineage",
    "ClaimExtractionRoutingStatus",
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
    "normalize_claim_extraction_routing_status",
    "PdfTextExtractionOutcome",
]
