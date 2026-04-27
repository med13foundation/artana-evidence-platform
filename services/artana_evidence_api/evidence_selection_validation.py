"""Validation helpers for evidence-selection shadow and expert review."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceSelectionReviewInput(BaseModel):
    """Reviewer-labeled comparison input for one evidence-selection run."""

    model_config = ConfigDict(strict=True, frozen=True)

    run_id: UUID
    goal: str
    harness_selected_record_ids: tuple[str, ...]
    human_selected_record_ids: tuple[str, ...]
    harness_skipped_record_ids: tuple[str, ...] = ()
    duplicate_suggestion_ids: tuple[str, ...] = ()
    explanation_quality_score: int | None = Field(default=None, ge=1, le=5)
    high_severity_overclaim_count: int = Field(default=0, ge=0)
    reviewer_notes: str | None = None

    @model_validator(mode="after")
    def _selected_and_skipped_must_not_overlap(
        self,
    ) -> EvidenceSelectionReviewInput:
        overlap = set(self.harness_selected_record_ids).intersection(
            self.harness_skipped_record_ids,
        )
        if overlap:
            msg = "harness_selected_record_ids and harness_skipped_record_ids overlap"
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
    explanation_quality_score: int | None
    high_severity_overclaim_count: int
    overclaim_gate_passed: bool
    reviewer_notes: str | None


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
        record_id for record_id in harness_selected if record_id not in human_selected_set
    )
    false_negative_ids = tuple(
        record_id for record_id in human_selected if record_id not in harness_selected_set
    )
    confirmed_skip_ids = tuple(
        record_id for record_id in harness_skipped if record_id not in human_selected_set
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
        explanation_quality_score=review.explanation_quality_score,
        high_severity_overclaim_count=review.high_severity_overclaim_count,
        overclaim_gate_passed=review.high_severity_overclaim_count == 0,
        reviewer_notes=review.reviewer_notes,
    )


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


__all__ = [
    "EvidenceSelectionReviewInput",
    "EvidenceSelectionReviewReport",
    "compare_evidence_selection_review",
]
