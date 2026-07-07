"""Validation helpers for evidence-selection shadow and expert review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from artana_evidence_api.ranking import (
    ReviewRankingCalibrationObservation,
    ReviewRankingCalibrationSummary,
    build_review_ranking_calibration_summary,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ReviewRankingSourceKind = Literal["proposal", "review_item"]
ReviewRankingOutcome = Literal["positive", "negative"]
ReviewRankingGateStatus = Literal["passed", "failed"]
ReviewRankingCalibrationSchemaVersion = Literal[
    "evidence_selection_review_ranking_calibration.v1"
]

_SOURCE_KINDS: tuple[ReviewRankingSourceKind, ...] = ("proposal", "review_item")
_OUTCOMES: tuple[ReviewRankingOutcome, ...] = ("negative", "positive")


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


class ReviewRankingCalibrationDecision(BaseModel):
    """One expert/shadow decision for a scored review queue item."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_kind: ReviewRankingSourceKind
    item_id: str = Field(min_length=1)
    ranking_score: float = Field(ge=0.0, le=1.0)
    outcome: ReviewRankingOutcome
    reviewer_id: str | None = Field(default=None, min_length=1)
    goal: str | None = Field(default=None, min_length=1)


class ReviewRankingCalibrationGateThresholds(BaseModel):
    """Fail-closed thresholds for expert/shadow review-ranking calibration."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    min_sample_count: int = Field(default=10, ge=1)
    max_expected_calibration_error: float = Field(default=0.05, ge=0.0, le=1.0)
    min_roc_auc: float = Field(default=0.7, ge=0.0, le=1.0)
    min_mean_score_separation: float = Field(default=0.1, ge=0.0, le=1.0)
    require_positive_and_negative_outcomes: bool = True
    require_proposal_and_review_item_sources: bool = True
    bin_count: int = Field(default=10, ge=1)


class ReviewRankingCalibrationStudyInput(BaseModel):
    """Strict JSON envelope for expert/shadow review-ranking calibration."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: ReviewRankingCalibrationSchemaVersion
    study_id: str = Field(min_length=1)
    decisions: tuple[ReviewRankingCalibrationDecision, ...]
    description: str | None = Field(default=None, min_length=1)

    @field_validator("decisions", mode="before")
    @classmethod
    def _accept_json_decision_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


@dataclass(frozen=True, slots=True)
class ReviewRankingCalibrationGateReport:
    """Gate decision and evidence for review-ranking calibration."""

    passed: bool
    status: ReviewRankingGateStatus
    calibration: ReviewRankingCalibrationSummary
    thresholds: ReviewRankingCalibrationGateThresholds
    source_counts: dict[str, int]
    outcome_counts: dict[str, int]
    mean_positive_score: float
    mean_negative_score: float
    mean_score_separation: float
    roc_auc: float
    duplicate_decision_keys: tuple[str, ...]
    blocking_reasons: tuple[str, ...]

    def to_json(self) -> JSONObject:
        """Return a stable JSON payload for artifacts."""
        return {
            "passed": self.passed,
            "status": self.status,
            "calibration": self.calibration.to_json(),
            "thresholds": {
                "min_sample_count": self.thresholds.min_sample_count,
                "max_expected_calibration_error": (
                    self.thresholds.max_expected_calibration_error
                ),
                "min_roc_auc": self.thresholds.min_roc_auc,
                "min_mean_score_separation": (
                    self.thresholds.min_mean_score_separation
                ),
                "require_positive_and_negative_outcomes": (
                    self.thresholds.require_positive_and_negative_outcomes
                ),
                "require_proposal_and_review_item_sources": (
                    self.thresholds.require_proposal_and_review_item_sources
                ),
                "bin_count": self.thresholds.bin_count,
            },
            "source_counts": dict(self.source_counts),
            "outcome_counts": dict(self.outcome_counts),
            "discrimination": {
                "mean_positive_score": self.mean_positive_score,
                "mean_negative_score": self.mean_negative_score,
                "mean_score_separation": self.mean_score_separation,
                "roc_auc": self.roc_auc,
            },
            "duplicate_decision_keys": list(self.duplicate_decision_keys),
            "blocking_reasons": list(self.blocking_reasons),
        }


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


def evaluate_review_ranking_calibration_gate(
    *,
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
    thresholds: ReviewRankingCalibrationGateThresholds | None = None,
) -> ReviewRankingCalibrationGateReport:
    """Evaluate whether expert/shadow review-ranking calibration is mergeable."""

    active_thresholds = thresholds or ReviewRankingCalibrationGateThresholds()
    calibration = build_review_ranking_calibration_summary(
        tuple(
            ReviewRankingCalibrationObservation(
                ranking_score=decision.ranking_score,
                outcome_positive=decision.outcome == "positive",
            )
            for decision in decisions
        ),
        bin_count=active_thresholds.bin_count,
    )
    source_counts = _source_counts(decisions)
    outcome_counts = _outcome_counts(decisions)
    mean_positive_score = _mean_outcome_score(decisions=decisions, outcome="positive")
    mean_negative_score = _mean_outcome_score(decisions=decisions, outcome="negative")
    mean_score_separation = _round_gate_metric(
        mean_positive_score - mean_negative_score,
    )
    roc_auc = _roc_auc(decisions)
    duplicate_decision_keys = _duplicate_decision_keys(decisions)
    blocking_reasons = _blocking_reasons(
        calibration=calibration,
        thresholds=active_thresholds,
        source_counts=source_counts,
        outcome_counts=outcome_counts,
        mean_score_separation=mean_score_separation,
        roc_auc=roc_auc,
        duplicate_decision_keys=duplicate_decision_keys,
    )
    passed = not blocking_reasons
    return ReviewRankingCalibrationGateReport(
        passed=passed,
        status="passed" if passed else "failed",
        calibration=calibration,
        thresholds=active_thresholds,
        source_counts=source_counts,
        outcome_counts=outcome_counts,
        mean_positive_score=mean_positive_score,
        mean_negative_score=mean_negative_score,
        mean_score_separation=mean_score_separation,
        roc_auc=roc_auc,
        duplicate_decision_keys=duplicate_decision_keys,
        blocking_reasons=blocking_reasons,
    )


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _source_counts(
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
) -> dict[str, int]:
    return {
        source_kind: sum(
            1 for decision in decisions if decision.source_kind == source_kind
        )
        for source_kind in _SOURCE_KINDS
    }


def _outcome_counts(
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
) -> dict[str, int]:
    return {
        outcome: sum(1 for decision in decisions if decision.outcome == outcome)
        for outcome in _OUTCOMES
    }


def _duplicate_decision_keys(
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
) -> tuple[str, ...]:
    seen: set[tuple[ReviewRankingSourceKind, str]] = set()
    duplicates: list[str] = []
    for decision in decisions:
        key = (decision.source_kind, decision.item_id)
        if key in seen:
            duplicates.append(f"{decision.source_kind}:{decision.item_id}")
            continue
        seen.add(key)
    return tuple(dict.fromkeys(duplicates))


def _mean_outcome_score(
    *,
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
    outcome: ReviewRankingOutcome,
) -> float:
    scores = tuple(
        decision.ranking_score for decision in decisions if decision.outcome == outcome
    )
    if not scores:
        return 0.0
    return _round_gate_metric(sum(scores) / len(scores))


def _roc_auc(decisions: tuple[ReviewRankingCalibrationDecision, ...]) -> float:
    positive_scores = tuple(
        decision.ranking_score for decision in decisions if decision.outcome == "positive"
    )
    negative_scores = tuple(
        decision.ranking_score for decision in decisions if decision.outcome == "negative"
    )
    pair_count = len(positive_scores) * len(negative_scores)
    if pair_count == 0:
        return 0.0
    pair_score = 0.0
    for positive_score in positive_scores:
        for negative_score in negative_scores:
            if positive_score > negative_score:
                pair_score += 1.0
            elif positive_score == negative_score:
                pair_score += 0.5
    return _round_gate_metric(pair_score / pair_count)


def _blocking_reasons(
    *,
    calibration: ReviewRankingCalibrationSummary,
    thresholds: ReviewRankingCalibrationGateThresholds,
    source_counts: dict[str, int],
    outcome_counts: dict[str, int],
    mean_score_separation: float,
    roc_auc: float,
    duplicate_decision_keys: tuple[str, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if calibration.sample_count < thresholds.min_sample_count:
        reasons.append(
            "At least "
            f"{thresholds.min_sample_count} expert/shadow review-ranking "
            f"decisions are required; got {calibration.sample_count}.",
        )
    if thresholds.require_positive_and_negative_outcomes:
        if outcome_counts["positive"] == 0:
            reasons.append("At least one positive reviewer outcome is required.")
        if outcome_counts["negative"] == 0:
            reasons.append("At least one negative reviewer outcome is required.")
    if thresholds.require_proposal_and_review_item_sources:
        if source_counts["proposal"] == 0:
            reasons.append("At least one proposal source decision is required.")
        if source_counts["review_item"] == 0:
            reasons.append("At least one review_item source decision is required.")
    if duplicate_decision_keys:
        reasons.append(
            "Duplicate review-ranking decision keys were observed: "
            f"{', '.join(duplicate_decision_keys)}.",
        )
    if roc_auc < thresholds.min_roc_auc:
        reasons.append(
            "Review-ranking ROC AUC is below target: "
            f"{roc_auc:.6f} < {thresholds.min_roc_auc:.6f}.",
        )
    if mean_score_separation < thresholds.min_mean_score_separation:
        reasons.append(
            "Review-ranking positive-vs-negative mean score separation is "
            "below target: "
            f"{mean_score_separation:.6f} < "
            f"{thresholds.min_mean_score_separation:.6f}.",
        )
    if (
        calibration.expected_calibration_error
        > thresholds.max_expected_calibration_error
    ):
        reasons.append(
            "Review-ranking calibration ECE is above target: "
            f"{calibration.expected_calibration_error:.6f} > "
            f"{thresholds.max_expected_calibration_error:.6f}.",
        )
    return tuple(reasons)


def _round_gate_metric(value: float) -> float:
    return round(value, 6)


__all__ = [
    "EvidenceSelectionReviewInput",
    "EvidenceSelectionReviewReport",
    "ReviewRankingCalibrationDecision",
    "ReviewRankingCalibrationGateReport",
    "ReviewRankingCalibrationStudyInput",
    "ReviewRankingCalibrationGateThresholds",
    "compare_evidence_selection_review",
    "evaluate_review_ranking_calibration_gate",
]
