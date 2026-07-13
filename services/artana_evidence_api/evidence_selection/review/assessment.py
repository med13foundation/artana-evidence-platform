"""Categorical human-review findings for evidence-selection explanations."""

from __future__ import annotations

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BinaryReviewFinding = Literal["yes", "no"]
CitationEntailmentFinding = Literal["yes", "no", "unclear"]
ExplanationAdequacy = Literal["adequate", "inadequate", "unclear"]


class EvidenceSelectionReviewCitation(BaseModel):
    """Literal source evidence cited by a reviewer."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_id: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    quoted_text: str = Field(min_length=1)

    @field_validator("record_id", "source_locator", "quoted_text")
    @classmethod
    def _reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            msg = "Review citation fields must not be blank."
            raise ValueError(msg)
        return value


class EvidenceSelectionExplanationAssessment(BaseModel):
    """Atomic reviewer findings from which explanation adequacy is derived."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    literal_citation_present: BinaryReviewFinding
    citation_entails_claim: CitationEntailmentFinding
    all_required_criteria_addressed: BinaryReviewFinding
    unsupported_material_claim_present: BinaryReviewFinding
    cited_evidence: tuple[EvidenceSelectionReviewCitation, ...]
    reviewer_explanation: str = Field(min_length=1)

    @field_validator("cited_evidence", mode="before")
    @classmethod
    def _accept_json_citation_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("reviewer_explanation")
    @classmethod
    def _reject_blank_explanation(cls, value: str) -> str:
        if not value.strip():
            msg = "reviewer_explanation must not be blank."
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _citation_findings_must_match_evidence(self) -> Self:
        if self.literal_citation_present == "yes" and not self.cited_evidence:
            msg = "cited_evidence is required when a literal citation is present."
            raise ValueError(msg)
        if self.literal_citation_present == "no" and self.cited_evidence:
            msg = "cited_evidence must be empty when no literal citation is present."
            raise ValueError(msg)
        if (
            self.literal_citation_present == "no"
            and self.citation_entails_claim != "unclear"
        ):
            msg = "citation_entails_claim must be unclear when no citation is present."
            raise ValueError(msg)
        return self


class EvidenceSelectionOverclaimFinding(BaseModel):
    """One material unsupported claim identified by a reviewer."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_id: str = Field(min_length=1)
    material_claim: str = Field(min_length=1)
    reviewer_explanation: str = Field(min_length=1)
    cited_evidence: tuple[EvidenceSelectionReviewCitation, ...] = ()

    @field_validator("cited_evidence", mode="before")
    @classmethod
    def _accept_json_citation_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("record_id", "material_claim", "reviewer_explanation")
    @classmethod
    def _reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            msg = "Overclaim finding fields must not be blank."
            raise ValueError(msg)
        return value


def derive_explanation_adequacy(
    assessment: EvidenceSelectionExplanationAssessment,
) -> ExplanationAdequacy:
    """Derive a stable category without accepting a reviewer-authored score."""

    if (
        assessment.literal_citation_present == "no"
        or assessment.citation_entails_claim == "no"
        or assessment.all_required_criteria_addressed == "no"
        or assessment.unsupported_material_claim_present == "yes"
    ):
        return "inadequate"
    if assessment.citation_entails_claim == "unclear":
        return "unclear"
    return "adequate"


class EvidenceSelectionReviewInput(BaseModel):
    """Reviewer-labeled comparison input for one evidence-selection run."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    run_id: UUID
    goal: str
    reviewer_id: str | None = None
    harness_selected_record_ids: tuple[str, ...]
    human_selected_record_ids: tuple[str, ...]
    harness_skipped_record_ids: tuple[str, ...] = ()
    duplicate_suggestion_ids: tuple[str, ...] = ()
    explanation_assessment: EvidenceSelectionExplanationAssessment | None = None
    high_severity_overclaim_findings: (
        tuple[EvidenceSelectionOverclaimFinding, ...] | None
    ) = None
    reviewer_notes: str | None = None
    false_positive_notes: dict[str, str] | None = None
    false_negative_notes: dict[str, str] | None = None

    @field_validator("run_id", mode="before")
    @classmethod
    def _accept_json_run_id(cls, value: object) -> object:
        if isinstance(value, str):
            return UUID(value)
        return value

    @field_validator(
        "harness_selected_record_ids",
        "human_selected_record_ids",
        "harness_skipped_record_ids",
        "duplicate_suggestion_ids",
        "high_severity_overclaim_findings",
        mode="before",
    )
    @classmethod
    def _accept_json_record_id_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator(
        "harness_selected_record_ids",
        "human_selected_record_ids",
        "harness_skipped_record_ids",
        "duplicate_suggestion_ids",
    )
    @classmethod
    def _normalize_record_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(record_id.strip() for record_id in value)
        if any(record_id == "" for record_id in normalized):
            msg = "record IDs must not be blank"
            raise ValueError(msg)
        return normalized

    @field_validator("false_positive_notes", "false_negative_notes")
    @classmethod
    def _normalize_finding_notes(
        cls,
        value: dict[str, str] | None,
    ) -> dict[str, str] | None:
        if value is None:
            return None
        normalized = {
            record_id.strip(): note.strip() for record_id, note in value.items()
        }
        if any(record_id == "" for record_id in normalized):
            msg = "finding-note record IDs must not be blank"
            raise ValueError(msg)
        if any(note == "" for note in normalized.values()):
            msg = "finding notes must not be blank"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def _selected_and_skipped_must_not_overlap(self) -> EvidenceSelectionReviewInput:
        overlap = set(self.harness_selected_record_ids).intersection(
            self.harness_skipped_record_ids,
        )
        if overlap:
            msg = "harness_selected_record_ids and harness_skipped_record_ids overlap"
            raise ValueError(msg)
        if (
            self.explanation_assessment is not None
            and self.explanation_assessment.unsupported_material_claim_present == "yes"
            and not self.high_severity_overclaim_findings
        ):
            msg = (
                "Unsupported material claims require at least one explicit "
                "high-severity overclaim finding."
            )
            raise ValueError(msg)
        if (
            self.explanation_assessment is not None
            and self.explanation_assessment.unsupported_material_claim_present == "no"
            and self.high_severity_overclaim_findings
        ):
            msg = (
                "High-severity overclaim findings require "
                "unsupported_material_claim_present to be yes."
            )
            raise ValueError(msg)
        return self


class EvidenceSelectionReviewReport(BaseModel):
    """Computed review metrics for one evidence-selection run."""

    model_config = ConfigDict(strict=True, frozen=True)

    run_id: UUID
    goal: str
    true_positive_ids: tuple[str, ...]
    false_positive_ids: tuple[str, ...]
    false_negative_ids: tuple[str, ...]
    confirmed_skip_ids: tuple[str, ...]
    duplicate_suggestion_ids: tuple[str, ...]
    precision: float | None
    recall: float | None
    duplicate_suggestion_count: int
    explanation_assessment: EvidenceSelectionExplanationAssessment | None
    explanation_adequacy: ExplanationAdequacy | None
    high_severity_overclaim_findings: (
        tuple[EvidenceSelectionOverclaimFinding, ...] | None
    )
    high_severity_overclaim_count: int | None
    overclaim_gate_passed: bool
    reviewer_id: str | None
    reviewer_notes: str | None
    false_positive_notes: dict[str, str] | None
    false_negative_notes: dict[str, str] | None


def compare_evidence_selection_review(
    review: EvidenceSelectionReviewInput,
) -> EvidenceSelectionReviewReport:
    """Compare harness-selected records with reviewer-selected records."""

    harness_selected = tuple(dict.fromkeys(review.harness_selected_record_ids))
    human_selected = tuple(dict.fromkeys(review.human_selected_record_ids))
    harness_skipped = tuple(dict.fromkeys(review.harness_skipped_record_ids))
    duplicate_suggestions = tuple(dict.fromkeys(review.duplicate_suggestion_ids))
    harness_selected_set = set(harness_selected)
    human_selected_set = set(human_selected)
    true_positive_ids = tuple(
        record_id for record_id in harness_selected if record_id in human_selected_set
    )
    false_positive_ids = tuple(
        record_id
        for record_id in harness_selected
        if record_id not in human_selected_set
    )
    false_negative_ids = tuple(
        record_id
        for record_id in human_selected
        if record_id not in harness_selected_set
    )
    confirmed_skip_ids = tuple(
        record_id
        for record_id in harness_skipped
        if record_id not in human_selected_set
    )
    return EvidenceSelectionReviewReport(
        run_id=review.run_id,
        goal=review.goal,
        true_positive_ids=true_positive_ids,
        false_positive_ids=false_positive_ids,
        false_negative_ids=false_negative_ids,
        confirmed_skip_ids=confirmed_skip_ids,
        duplicate_suggestion_ids=duplicate_suggestions,
        precision=_safe_ratio(len(true_positive_ids), len(harness_selected)),
        recall=_safe_ratio(len(true_positive_ids), len(human_selected)),
        duplicate_suggestion_count=len(duplicate_suggestions),
        explanation_assessment=review.explanation_assessment,
        explanation_adequacy=(
            derive_explanation_adequacy(review.explanation_assessment)
            if review.explanation_assessment is not None
            else None
        ),
        high_severity_overclaim_findings=review.high_severity_overclaim_findings,
        high_severity_overclaim_count=(
            len(review.high_severity_overclaim_findings)
            if review.high_severity_overclaim_findings is not None
            else None
        ),
        overclaim_gate_passed=(
            review.high_severity_overclaim_findings is not None
            and not review.high_severity_overclaim_findings
        ),
        reviewer_id=review.reviewer_id,
        reviewer_notes=review.reviewer_notes,
        false_positive_notes=review.false_positive_notes,
        false_negative_notes=review.false_negative_notes,
    )


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


__all__ = [
    "BinaryReviewFinding",
    "CitationEntailmentFinding",
    "EvidenceSelectionExplanationAssessment",
    "EvidenceSelectionOverclaimFinding",
    "EvidenceSelectionReviewCitation",
    "EvidenceSelectionReviewInput",
    "EvidenceSelectionReviewReport",
    "ExplanationAdequacy",
    "compare_evidence_selection_review",
    "derive_explanation_adequacy",
]
