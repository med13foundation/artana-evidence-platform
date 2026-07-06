"""Typed contracts for the relation feasibility audit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.evidence_support_verifier import (
        TripleSupport,
    )

ValueLevel = Literal["high", "medium", "low", "reject"]
Verdict = Literal["GREEN", "YELLOW", "RED"]
ExtractorMode = Literal["agent", "deterministic", "custom"]
RelationGovernanceStatus = Literal["canonical", "requires_relation_review"]
CurieSource = Literal["none", "model", "verified_linker"]
RelationReviewStatus = Literal["candidate", "review_only"]
CandidateExtractionStatus = Literal[
    "not_needed",
    "completed",
    "llm_empty",
    "fallback",
    "fallback_error",
    "unavailable",
]


@dataclass(frozen=True, slots=True)
class GoldRelation:
    """One manually curated expected relation for an audit case."""

    subject: str
    relation_type: str
    object: str
    support_sentence: str
    value_level: ValueLevel
    rationale: str
    subject_curie: str | None = None
    object_curie: str | None = None
    requires_entailment: bool = True
    review_status: RelationReviewStatus = "candidate"

    def to_json(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "subject": self.subject,
            "relation_type": self.relation_type,
            "object": self.object,
            "support_sentence": self.support_sentence,
            "value_level": self.value_level,
            "rationale": self.rationale,
            "subject_curie": self.subject_curie,
            "object_curie": self.object_curie,
            "requires_entailment": self.requires_entailment,
            "review_status": self.review_status,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One text input and its manually curated expected relations."""

    case_id: str
    title: str
    category: str
    text: str
    gold_relations: tuple[GoldRelation, ...]

    def to_json(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "case_id": self.case_id,
            "title": self.title,
            "category": self.category,
            "text": self.text,
            "gold_relations": [relation.to_json() for relation in self.gold_relations],
        }


@dataclass(frozen=True, slots=True)
class ExtractedRelation:
    """One relation candidate emitted by the current extraction pipeline."""

    subject: str
    relation_type: str
    object: str
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

    @property
    def trusted_evidence_eligible(self) -> bool:
        """Return whether this candidate can be treated as a trusted graph edge."""

        return (
            self.relation_governance_status == "canonical"
            and self.review_status != "review_only"
        )

    def to_json(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "subject": self.subject,
            "relation_type": self.relation_type,
            "proposed_relation_type": self.proposed_relation_type,
            "new_relation_type_rationale": self.new_relation_type_rationale,
            "relation_governance_status": self.relation_governance_status,
            "trusted_evidence_eligible": self.trusted_evidence_eligible,
            "review_status": self.review_status,
            "review_reason_codes": list(self.review_reason_codes),
            "object": self.object,
            "sentence": self.sentence,
            "subject_curie": self.subject_curie,
            "object_curie": self.object_curie,
            "subject_curie_source": self.subject_curie_source,
            "object_curie_source": self.object_curie_source,
        }


@dataclass(frozen=True, slots=True)
class RelationTypeSurface:
    """One relation-type value observed on a candidate, review, proposal, or graph surface."""

    surface: str
    relation_type: str
    source_ref: str
    governance_status: RelationGovernanceStatus | None = None

    def to_json(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "surface": self.surface,
            "relation_type": self.relation_type,
            "source_ref": self.source_ref,
            "governance_status": self.governance_status,
        }


@dataclass(frozen=True, slots=True)
class ExtractionTrace:
    """Runtime trace for one benchmark extraction pass."""

    extractor_mode: ExtractorMode
    llm_candidate_status: CandidateExtractionStatus | None = None
    llm_candidate_error: str | None = None
    llm_candidate_count: int = 0
    fallback_candidate_count: int = 0
    pruned_generic_relation_count: int = 0
    quality_filtered_candidate_count: int = 0

    @property
    def agent_completed(self) -> bool:
        """Return whether the agent/LLM extraction path completed."""

        if self.extractor_mode != "agent" or self.fallback_used:
            return False
        if self.llm_candidate_status == "completed":
            return True
        return (
            self.llm_candidate_status == "llm_empty"
            and self.llm_candidate_count == 0
        )

    @property
    def fallback_used(self) -> bool:
        """Return whether the result used or represented a fallback path."""

        return (
            self.extractor_mode == "agent"
            and (
                self.llm_candidate_status
                in {"fallback", "fallback_error", "unavailable"}
                or self.fallback_candidate_count > 0
            )
        )

    def to_json(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "extractor_mode": self.extractor_mode,
            "llm_candidate_status": self.llm_candidate_status,
            "llm_candidate_error": self.llm_candidate_error,
            "llm_candidate_count": self.llm_candidate_count,
            "fallback_candidate_count": self.fallback_candidate_count,
            "pruned_generic_relation_count": self.pruned_generic_relation_count,
            "quality_filtered_candidate_count": self.quality_filtered_candidate_count,
            "agent_completed": self.agent_completed,
            "fallback_used": self.fallback_used,
        }


@dataclass(frozen=True, slots=True)
class RelationExtractionResult:
    """Relations plus runtime trace for one extraction pass."""

    relations: tuple[ExtractedRelation, ...]
    trace: ExtractionTrace
    relation_type_surfaces: tuple[RelationTypeSurface, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    """Quality judgment for one extracted relation candidate."""

    candidate: ExtractedRelation
    matched_gold_index: int | None
    proposal_matched_gold_index: int | None
    is_supported_by_gold: bool
    is_governed_relation_proposal: bool
    is_trusted_evidence_eligible: bool
    has_specific_subject: bool
    has_specific_object: bool
    is_relation_specific: bool
    has_grounded_sentence: bool
    has_subject_in_sentence: bool
    has_object_in_sentence: bool
    has_both_arguments_in_sentence: bool
    has_gold_support_sentence: bool
    has_known_relation_type: bool
    requires_entailment: bool
    support_verification: TripleSupport | None
    has_support_verification: bool
    has_entailment_support: bool
    has_subject_curie: bool
    has_object_curie: bool
    has_verified_subject_curie: bool
    has_verified_object_curie: bool
    subject_curie_matches_gold: bool
    object_curie_matches_gold: bool
    is_valuable: bool
    quality_flags: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "candidate": self.candidate.to_json(),
            "matched_gold_index": self.matched_gold_index,
            "proposal_matched_gold_index": self.proposal_matched_gold_index,
            "is_supported_by_gold": self.is_supported_by_gold,
            "is_governed_relation_proposal": self.is_governed_relation_proposal,
            "is_trusted_evidence_eligible": self.is_trusted_evidence_eligible,
            "has_specific_subject": self.has_specific_subject,
            "has_specific_object": self.has_specific_object,
            "is_relation_specific": self.is_relation_specific,
            "has_grounded_sentence": self.has_grounded_sentence,
            "has_subject_in_sentence": self.has_subject_in_sentence,
            "has_object_in_sentence": self.has_object_in_sentence,
            "has_both_arguments_in_sentence": self.has_both_arguments_in_sentence,
            "has_gold_support_sentence": self.has_gold_support_sentence,
            "has_known_relation_type": self.has_known_relation_type,
            "requires_entailment": self.requires_entailment,
            "support_verification": self.support_verification,
            "has_support_verification": self.has_support_verification,
            "has_entailment_support": self.has_entailment_support,
            "has_subject_curie": self.has_subject_curie,
            "has_object_curie": self.has_object_curie,
            "has_verified_subject_curie": self.has_verified_subject_curie,
            "has_verified_object_curie": self.has_verified_object_curie,
            "subject_curie_matches_gold": self.subject_curie_matches_gold,
            "object_curie_matches_gold": self.object_curie_matches_gold,
            "is_valuable": self.is_valuable,
            "quality_flags": list(self.quality_flags),
        }


@dataclass(frozen=True, slots=True)
class CaseResult:
    """Audit result for one benchmark case."""

    case: BenchmarkCase
    candidate_assessments: tuple[CandidateAssessment, ...]
    missed_gold_indices: tuple[int, ...]
    extraction_trace: ExtractionTrace
    relation_type_surfaces: tuple[RelationTypeSurface, ...]

    @property
    def agent_completed(self) -> bool:
        """Return whether this case completed through the agent path."""

        if not self.extraction_trace.agent_completed:
            return False
        if self.extraction_trace.llm_candidate_status == "llm_empty":
            return len(self.candidate_assessments) == 0
        return True

    def to_json(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        extraction_trace = self.extraction_trace.to_json()
        extraction_trace["agent_completed"] = self.agent_completed
        return {
            "case": self.case.to_json(),
            "extraction_trace": extraction_trace,
            "relation_type_surfaces": [
                surface.to_json() for surface in self.relation_type_surfaces
            ],
            "candidate_assessments": [
                assessment.to_json() for assessment in self.candidate_assessments
            ],
            "missed_gold_indices": list(self.missed_gold_indices),
            "missed_gold_relations": [
                self.case.gold_relations[index].to_json()
                for index in self.missed_gold_indices
            ],
        }


@dataclass(frozen=True, slots=True)
class FeasibilitySummary:
    """Aggregate quality metrics across all benchmark cases."""

    case_count: int
    gold_relation_count: int
    candidate_count: int
    supported_candidate_count: int
    valuable_candidate_count: int
    generic_relation_count: int
    pruned_generic_relation_count: int
    quality_filtered_candidate_count: int
    raw_unknown_relation_type_count: int
    relation_type_surface_count: int
    raw_unknown_relation_type_surface_count: int
    proposal_candidate_count: int
    proposal_gold_match_count: int
    proposal_eligible_gold_count: int
    gold_curie_endpoint_count: int
    candidate_curie_endpoint_count: int
    curie_linked_gold_endpoint_count: int
    verified_curie_match_count: int
    model_curie_wrong_count: int
    wrong_verified_curie_link_count: int
    support_sentence_aligned_count: int
    both_arguments_present_count: int
    entailment_required_count: int
    entailment_checked_count: int
    entailment_supported_count: int
    agent_completed_case_count: int
    fallback_case_count: int
    fallback_candidate_count: int
    fallback_credited_as_agent_count: int
    completed_agent_candidate_count: int
    completed_agent_supported_candidate_count: int
    completed_agent_valuable_candidate_count: int
    completed_agent_gold_relation_count: int
    completed_agent_missed_gold_count: int
    invalid_agent_case_count: int
    high_value_gold_relation_count: int
    high_value_missed_gold_count: int
    trusted_high_value_match_count: int
    trusted_high_value_recall: float
    high_value_review_gold_relation_count: int
    high_value_review_candidate_count: int
    high_value_review_gold_match_count: int
    high_value_review_recall: float
    low_value_gold_relation_count: int
    low_value_missed_gold_count: int
    low_value_review_candidate_count: int
    low_value_review_gold_match_count: int
    low_value_review_recall: float
    trusted_eligible_gold_curie_endpoint_count: int
    trusted_eligible_curie_linked_gold_endpoint_count: int
    trusted_eligible_curie_linked_gold_endpoint_rate: float
    low_value_review_gold_curie_endpoint_count: int
    low_value_review_curie_linked_gold_endpoint_count: int
    low_value_review_curie_endpoint_capture_rate: float
    weak_claim_trusted_leakage_count: int
    negative_control_case_count: int
    negative_control_empty_count: int
    negative_control_leakage_count: int
    missed_gold_count: int
    precision_against_gold: float
    recall_against_gold: float
    high_value_recall: float
    low_value_recall: float
    completed_agent_precision_against_gold: float
    completed_agent_recall_against_gold: float
    specificity_rate: float
    relation_specificity_rate: float
    generic_relation_rate: float
    raw_unknown_relation_type_rate: float
    raw_unknown_relation_type_surface_rate: float
    proposal_recall_against_gold: float
    proposal_recall_against_proposal_eligible_gold: float
    candidate_curie_present_rate: float
    verified_curie_match_rate: float
    curie_linked_gold_endpoint_rate: float
    valuable_candidate_rate: float
    completed_agent_valuable_candidate_rate: float
    grounded_sentence_rate: float
    both_arguments_present_rate: float
    support_sentence_alignment_rate: float
    entailment_checked_rate: float
    entailment_supported_rate: float
    verdict: Verdict
    verdict_reason: str
    agent_zero_candidate_case_count: int = 0
    negative_control_empty_rate: float = 0.0
    blocking_reasons: tuple[str, ...] = ()
    warning_reasons: tuple[str, ...] = ()

    def to_json(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "case_count": self.case_count,
            "gold_relation_count": self.gold_relation_count,
            "candidate_count": self.candidate_count,
            "supported_candidate_count": self.supported_candidate_count,
            "valuable_candidate_count": self.valuable_candidate_count,
            "generic_relation_count": self.generic_relation_count,
            "pruned_generic_relation_count": self.pruned_generic_relation_count,
            "quality_filtered_candidate_count": self.quality_filtered_candidate_count,
            "raw_unknown_relation_type_count": self.raw_unknown_relation_type_count,
            "relation_type_surface_count": self.relation_type_surface_count,
            "raw_unknown_relation_type_surface_count": self.raw_unknown_relation_type_surface_count,
            "proposal_candidate_count": self.proposal_candidate_count,
            "proposal_gold_match_count": self.proposal_gold_match_count,
            "proposal_eligible_gold_count": self.proposal_eligible_gold_count,
            "proposal_recall_against_gold": self.proposal_recall_against_gold,
            "proposal_recall_against_proposal_eligible_gold": self.proposal_recall_against_proposal_eligible_gold,
            "gold_curie_endpoint_count": self.gold_curie_endpoint_count,
            "candidate_curie_endpoint_count": self.candidate_curie_endpoint_count,
            "curie_linked_gold_endpoint_count": self.curie_linked_gold_endpoint_count,
            "verified_curie_match_count": self.verified_curie_match_count,
            "model_curie_wrong_count": self.model_curie_wrong_count,
            "wrong_verified_curie_link_count": self.wrong_verified_curie_link_count,
            "support_sentence_aligned_count": self.support_sentence_aligned_count,
            "both_arguments_present_count": self.both_arguments_present_count,
            "entailment_required_count": self.entailment_required_count,
            "entailment_checked_count": self.entailment_checked_count,
            "entailment_supported_count": self.entailment_supported_count,
            "agent_completed_case_count": self.agent_completed_case_count,
            "agent_zero_candidate_case_count": self.agent_zero_candidate_case_count,
            "fallback_case_count": self.fallback_case_count,
            "fallback_candidate_count": self.fallback_candidate_count,
            "fallback_credited_as_agent_count": self.fallback_credited_as_agent_count,
            "completed_agent_candidate_count": self.completed_agent_candidate_count,
            "completed_agent_supported_candidate_count": self.completed_agent_supported_candidate_count,
            "completed_agent_valuable_candidate_count": self.completed_agent_valuable_candidate_count,
            "completed_agent_gold_relation_count": self.completed_agent_gold_relation_count,
            "completed_agent_missed_gold_count": self.completed_agent_missed_gold_count,
            "invalid_agent_case_count": self.invalid_agent_case_count,
            "high_value_gold_relation_count": self.high_value_gold_relation_count,
            "high_value_missed_gold_count": self.high_value_missed_gold_count,
            "high_value_recall": self.high_value_recall,
            "trusted_high_value_match_count": self.trusted_high_value_match_count,
            "trusted_high_value_recall": self.trusted_high_value_recall,
            "high_value_review_gold_relation_count": self.high_value_review_gold_relation_count,
            "high_value_review_candidate_count": self.high_value_review_candidate_count,
            "high_value_review_gold_match_count": self.high_value_review_gold_match_count,
            "high_value_review_recall": self.high_value_review_recall,
            "low_value_gold_relation_count": self.low_value_gold_relation_count,
            "low_value_missed_gold_count": self.low_value_missed_gold_count,
            "low_value_recall": self.low_value_recall,
            "low_value_review_candidate_count": self.low_value_review_candidate_count,
            "low_value_review_gold_match_count": self.low_value_review_gold_match_count,
            "low_value_review_recall": self.low_value_review_recall,
            "trusted_eligible_gold_curie_endpoint_count": self.trusted_eligible_gold_curie_endpoint_count,
            "trusted_eligible_curie_linked_gold_endpoint_count": self.trusted_eligible_curie_linked_gold_endpoint_count,
            "trusted_eligible_curie_linked_gold_endpoint_rate": self.trusted_eligible_curie_linked_gold_endpoint_rate,
            "low_value_review_gold_curie_endpoint_count": self.low_value_review_gold_curie_endpoint_count,
            "low_value_review_curie_linked_gold_endpoint_count": self.low_value_review_curie_linked_gold_endpoint_count,
            "low_value_review_curie_endpoint_capture_rate": self.low_value_review_curie_endpoint_capture_rate,
            "weak_claim_trusted_leakage_count": self.weak_claim_trusted_leakage_count,
            "negative_control_case_count": self.negative_control_case_count,
            "negative_control_empty_count": self.negative_control_empty_count,
            "negative_control_empty_rate": self.negative_control_empty_rate,
            "negative_control_leakage_count": self.negative_control_leakage_count,
            "missed_gold_count": self.missed_gold_count,
            "precision_against_gold": self.precision_against_gold,
            "recall_against_gold": self.recall_against_gold,
            "completed_agent_precision_against_gold": self.completed_agent_precision_against_gold,
            "completed_agent_recall_against_gold": self.completed_agent_recall_against_gold,
            "specificity_rate": self.specificity_rate,
            "relation_specificity_rate": self.relation_specificity_rate,
            "generic_relation_rate": self.generic_relation_rate,
            "raw_unknown_relation_type_rate": self.raw_unknown_relation_type_rate,
            "raw_unknown_relation_type_surface_rate": self.raw_unknown_relation_type_surface_rate,
            "curie_linked_gold_endpoint_rate": self.curie_linked_gold_endpoint_rate,
            "candidate_curie_present_rate": self.candidate_curie_present_rate,
            "verified_curie_match_rate": self.verified_curie_match_rate,
            "valuable_candidate_rate": self.valuable_candidate_rate,
            "completed_agent_valuable_candidate_rate": self.completed_agent_valuable_candidate_rate,
            "grounded_sentence_rate": self.grounded_sentence_rate,
            "both_arguments_present_rate": self.both_arguments_present_rate,
            "support_sentence_alignment_rate": self.support_sentence_alignment_rate,
            "entailment_checked_rate": self.entailment_checked_rate,
            "entailment_supported_rate": self.entailment_supported_rate,
            "verdict": self.verdict,
            "verdict_reason": self.verdict_reason,
            "blocking_reasons": list(self.blocking_reasons),
            "warning_reasons": list(self.warning_reasons),
        }


@dataclass(frozen=True, slots=True)
class FeasibilityReport:
    """Complete relation feasibility audit report."""

    summary: FeasibilitySummary
    case_results: tuple[CaseResult, ...]

    def to_json(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "summary": self.summary.to_json(),
            "case_results": [result.to_json() for result in self.case_results],
        }
