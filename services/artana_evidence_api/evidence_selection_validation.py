"""Validation helpers for evidence-selection shadow and expert review."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from artana_evidence_api.evidence_selection.provenance import (
    EvidenceSelectionExpertStudySourceArtifact,
    EvidenceSelectionExpertStudySourceManifest,
    build_evidence_selection_provenance_summary,
    source_manifest_blocking_reasons,
)
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
EvidenceSelectionExpertStudySchemaVersion = Literal[
    "evidence_selection_expert_study.v1"
]
EvidenceSelectionExpertStudyEvidenceKind = Literal[
    "real_shadow_review",
    "synthetic_fixture",
]

_SOURCE_KINDS: tuple[ReviewRankingSourceKind, ...] = ("proposal", "review_item")
_OUTCOMES: tuple[ReviewRankingOutcome, ...] = ("negative", "positive")


def _normalize_non_blank_study_id(value: str) -> str:
    normalized = value.strip()
    if normalized == "":
        msg = "study_id must not be blank"
        raise ValueError(msg)
    return normalized


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
    explanation_quality_score: int | None = Field(default=None, ge=1, le=5)
    high_severity_overclaim_count: int | None = Field(default=None, ge=0)
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
    high_severity_overclaim_count: int | None
    overclaim_gate_passed: bool
    reviewer_id: str | None
    reviewer_notes: str | None
    false_positive_notes: dict[str, str] | None
    false_negative_notes: dict[str, str] | None


class ReviewRankingCalibrationDecision(BaseModel):
    """One expert/shadow decision for a scored review queue item."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_kind: ReviewRankingSourceKind
    item_id: str = Field(min_length=1)
    ranking_score: float = Field(ge=0.0, le=1.0)
    outcome: ReviewRankingOutcome
    reviewer_id: str | None = None
    goal: str | None = None
    evidence_shape: str | None = None

    @field_validator("item_id")
    @classmethod
    def _normalize_item_id(cls, value: str) -> str:
        normalized = value.strip()
        if normalized == "":
            msg = "item_id must not be blank"
            raise ValueError(msg)
        return normalized


class ReviewRankingCalibrationGateThresholds(BaseModel):
    """Fail-closed thresholds for expert/shadow review-ranking calibration."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    min_sample_count: int = Field(default=10, ge=1)
    max_expected_calibration_error: float = Field(default=0.05, ge=0.0, le=1.0)
    min_roc_auc: float = Field(default=0.7, ge=0.0, le=1.0)
    min_mean_score_separation: float = Field(default=0.1, ge=0.0, le=1.0)
    min_distinct_goals: int = Field(default=3, ge=0)
    min_distinct_evidence_shapes: int = Field(default=3, ge=0)
    require_reviewer_ids: bool = True
    require_adjudication_note: bool = True
    require_positive_and_negative_outcomes: bool = True
    require_proposal_and_review_item_sources: bool = True
    require_positive_and_negative_per_source: bool = True
    bin_count: int = Field(default=10, ge=1)


class ReviewRankingCalibrationStudyInput(BaseModel):
    """Strict JSON envelope for expert/shadow review-ranking calibration."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: ReviewRankingCalibrationSchemaVersion
    study_id: str
    decisions: tuple[ReviewRankingCalibrationDecision, ...]
    adjudication_note: str | None = None
    description: str | None = Field(default=None, min_length=1)

    @field_validator("decisions", mode="before")
    @classmethod
    def _accept_json_decision_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("study_id")
    @classmethod
    def _normalize_study_id(cls, value: str) -> str:
        return _normalize_non_blank_study_id(value)


class EvidenceSelectionExpertStudyGateThresholds(BaseModel):
    """Fail-closed thresholds for a complete expert/shadow study."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    min_selection_review_count: int = Field(default=3, ge=1)
    min_distinct_selection_goals: int = Field(default=3, ge=1)
    min_selection_reviewer_count: int = Field(default=1, ge=1)
    min_mean_precision: float = Field(default=0.8, ge=0.0, le=1.0)
    min_mean_recall: float = Field(default=0.8, ge=0.0, le=1.0)
    min_mean_explanation_quality: float = Field(default=3.0, ge=1.0, le=5.0)
    require_zero_high_severity_overclaims: bool = True
    require_source_manifest: bool = True
    min_source_artifact_count: int = Field(default=2, ge=1)


class EvidenceSelectionExpertStudyInput(BaseModel):
    """Strict JSON envelope for a full evidence-selection expert study."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: EvidenceSelectionExpertStudySchemaVersion
    study_id: str
    study_evidence_kind: EvidenceSelectionExpertStudyEvidenceKind
    selection_reviews: tuple[EvidenceSelectionReviewInput, ...]
    review_ranking: ReviewRankingCalibrationStudyInput
    source_manifest: EvidenceSelectionExpertStudySourceManifest | None = None
    description: str | None = Field(default=None, min_length=1)

    @field_validator("selection_reviews", mode="before")
    @classmethod
    def _accept_json_selection_review_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("study_id")
    @classmethod
    def _normalize_study_id(cls, value: str) -> str:
        return _normalize_non_blank_study_id(value)

    @model_validator(mode="after")
    def _ranking_study_must_match_outer_study(
        self,
    ) -> EvidenceSelectionExpertStudyInput:
        if self.study_id != self.review_ranking.study_id:
            msg = "review_ranking study_id must match the expert study_id"
            raise ValueError(msg)
        return self


@dataclass(frozen=True, slots=True)
class ReviewRankingCalibrationGateReport:
    """Gate decision and evidence for review-ranking calibration."""

    passed: bool
    status: ReviewRankingGateStatus
    calibration: ReviewRankingCalibrationSummary
    thresholds: ReviewRankingCalibrationGateThresholds
    source_counts: dict[str, int]
    outcome_counts: dict[str, int]
    source_outcome_counts: dict[str, dict[str, int]]
    mean_positive_score: float
    mean_negative_score: float
    mean_score_separation: float
    roc_auc: float
    study_design: JSONObject
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
                "min_distinct_goals": self.thresholds.min_distinct_goals,
                "min_distinct_evidence_shapes": (
                    self.thresholds.min_distinct_evidence_shapes
                ),
                "require_reviewer_ids": self.thresholds.require_reviewer_ids,
                "require_adjudication_note": (
                    self.thresholds.require_adjudication_note
                ),
                "require_positive_and_negative_outcomes": (
                    self.thresholds.require_positive_and_negative_outcomes
                ),
                "require_proposal_and_review_item_sources": (
                    self.thresholds.require_proposal_and_review_item_sources
                ),
                "require_positive_and_negative_per_source": (
                    self.thresholds.require_positive_and_negative_per_source
                ),
                "bin_count": self.thresholds.bin_count,
            },
            "source_counts": dict(self.source_counts),
            "outcome_counts": dict(self.outcome_counts),
            "source_outcome_counts": {
                source_kind: dict(counts)
                for source_kind, counts in self.source_outcome_counts.items()
            },
            "discrimination": {
                "mean_positive_score": self.mean_positive_score,
                "mean_negative_score": self.mean_negative_score,
                "mean_score_separation": self.mean_score_separation,
                "roc_auc": self.roc_auc,
            },
            "study_design": dict(self.study_design),
            "duplicate_decision_keys": list(self.duplicate_decision_keys),
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True, slots=True)
class EvidenceSelectionExpertStudyGateReport:
    """Gate decision and evidence for a complete expert/shadow study."""

    passed: bool
    status: ReviewRankingGateStatus
    thresholds: EvidenceSelectionExpertStudyGateThresholds
    selection_summary: JSONObject
    provenance_summary: JSONObject
    selection_reports: tuple[EvidenceSelectionReviewReport, ...]
    review_ranking_gate: ReviewRankingCalibrationGateReport
    blocking_reasons: tuple[str, ...]

    def to_json(self) -> JSONObject:
        """Return a stable JSON payload for artifacts."""
        return {
            "passed": self.passed,
            "status": self.status,
            "thresholds": {
                "min_selection_review_count": (
                    self.thresholds.min_selection_review_count
                ),
                "min_distinct_selection_goals": (
                    self.thresholds.min_distinct_selection_goals
                ),
                "min_selection_reviewer_count": (
                    self.thresholds.min_selection_reviewer_count
                ),
                "min_mean_precision": self.thresholds.min_mean_precision,
                "min_mean_recall": self.thresholds.min_mean_recall,
                "min_mean_explanation_quality": (
                    self.thresholds.min_mean_explanation_quality
                ),
                "require_zero_high_severity_overclaims": (
                    self.thresholds.require_zero_high_severity_overclaims
                ),
                "require_source_manifest": (
                    self.thresholds.require_source_manifest
                ),
                "min_source_artifact_count": (
                    self.thresholds.min_source_artifact_count
                ),
            },
            "selection_summary": dict(self.selection_summary),
            "provenance_summary": dict(self.provenance_summary),
            "selection_reports": [
                _selection_report_to_json(report)
                for report in self.selection_reports
            ],
            "review_ranking_gate": self.review_ranking_gate.to_json(),
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
        overclaim_gate_passed=(
            review.high_severity_overclaim_count is not None
            and review.high_severity_overclaim_count == 0
        ),
        reviewer_id=review.reviewer_id,
        reviewer_notes=review.reviewer_notes,
        false_positive_notes=review.false_positive_notes,
        false_negative_notes=review.false_negative_notes,
    )


def evaluate_review_ranking_calibration_gate(
    *,
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
    adjudication_note: str | None = None,
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
    source_outcome_counts = _source_outcome_counts(decisions)
    mean_positive_score = _mean_outcome_score(decisions=decisions, outcome="positive")
    mean_negative_score = _mean_outcome_score(decisions=decisions, outcome="negative")
    mean_score_separation = _round_gate_metric(
        mean_positive_score - mean_negative_score,
    )
    roc_auc = _roc_auc(decisions)
    study_design = _study_design(
        decisions=decisions,
        adjudication_note=adjudication_note,
    )
    duplicate_decision_keys = _duplicate_decision_keys(decisions)
    blocking_reasons = _blocking_reasons(
        calibration=calibration,
        thresholds=active_thresholds,
        source_counts=source_counts,
        outcome_counts=outcome_counts,
        source_outcome_counts=source_outcome_counts,
        mean_score_separation=mean_score_separation,
        roc_auc=roc_auc,
        study_design=study_design,
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
        source_outcome_counts=source_outcome_counts,
        mean_positive_score=mean_positive_score,
        mean_negative_score=mean_negative_score,
        mean_score_separation=mean_score_separation,
        roc_auc=roc_auc,
        study_design=study_design,
        duplicate_decision_keys=duplicate_decision_keys,
        blocking_reasons=blocking_reasons,
    )


def evaluate_evidence_selection_expert_study_gate(
    study: EvidenceSelectionExpertStudyInput,
    *,
    thresholds: EvidenceSelectionExpertStudyGateThresholds | None = None,
    review_ranking_thresholds: ReviewRankingCalibrationGateThresholds | None = None,
) -> EvidenceSelectionExpertStudyGateReport:
    """Evaluate whether a full expert/shadow study is production-usable."""

    active_thresholds = thresholds or EvidenceSelectionExpertStudyGateThresholds()
    selection_reports = tuple(
        compare_evidence_selection_review(review)
        for review in study.selection_reviews
    )
    selection_summary = _selection_study_summary(
        reports=selection_reports,
        study_evidence_kind=study.study_evidence_kind,
    )
    provenance_summary = build_evidence_selection_provenance_summary(
        source_manifest=study.source_manifest,
        selection_run_ids=tuple(report.run_id for report in selection_reports),
        review_ranking_decision_keys=tuple(
            _review_ranking_decision_key(decision)
            for decision in study.review_ranking.decisions
        ),
        reviewer_ids=_expert_study_reviewer_ids(
            study=study,
            reports=selection_reports,
        ),
    )
    review_ranking_gate = evaluate_review_ranking_calibration_gate(
        decisions=study.review_ranking.decisions,
        adjudication_note=study.review_ranking.adjudication_note,
        thresholds=review_ranking_thresholds,
    )
    blocking_reasons = _expert_study_blocking_reasons(
        selection_summary=selection_summary,
        provenance_summary=provenance_summary,
        thresholds=active_thresholds,
        review_ranking_gate=review_ranking_gate,
    )
    passed = not blocking_reasons
    return EvidenceSelectionExpertStudyGateReport(
        passed=passed,
        status="passed" if passed else "failed",
        thresholds=active_thresholds,
        selection_summary=selection_summary,
        provenance_summary=provenance_summary,
        selection_reports=selection_reports,
        review_ranking_gate=review_ranking_gate,
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


def _source_outcome_counts(
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
) -> dict[str, dict[str, int]]:
    return {
        source_kind: {
            outcome: sum(
                1
                for decision in decisions
                if decision.source_kind == source_kind and decision.outcome == outcome
            )
            for outcome in _OUTCOMES
        }
        for source_kind in _SOURCE_KINDS
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


def _study_design(
    *,
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
    adjudication_note: str | None,
) -> JSONObject:
    goals = {
        normalized_goal
        for decision in decisions
        if (normalized_goal := _normalized_study_label(decision.goal))
    }
    evidence_shapes = {
        normalized_shape
        for decision in decisions
        if (normalized_shape := _normalized_study_label(decision.evidence_shape))
    }
    reviewer_ids = {
        reviewer_id.strip()
        for decision in decisions
        if (reviewer_id := decision.reviewer_id) and reviewer_id.strip()
    }
    return {
        "distinct_goal_count": len(goals),
        "distinct_evidence_shape_count": len(evidence_shapes),
        "reviewer_count": len(reviewer_ids),
        "missing_goal_count": sum(
            1 for decision in decisions if not _normalized_study_label(decision.goal)
        ),
        "missing_evidence_shape_count": sum(
            1
            for decision in decisions
            if not _normalized_study_label(decision.evidence_shape)
        ),
        "missing_reviewer_id_count": sum(
            1
            for decision in decisions
            if not (decision.reviewer_id and decision.reviewer_id.strip())
        ),
        "adjudication_note_present": bool(
            adjudication_note and adjudication_note.strip()
        ),
    }


def _blocking_reasons(
    *,
    calibration: ReviewRankingCalibrationSummary,
    thresholds: ReviewRankingCalibrationGateThresholds,
    source_counts: dict[str, int],
    outcome_counts: dict[str, int],
    source_outcome_counts: dict[str, dict[str, int]],
    mean_score_separation: float,
    roc_auc: float,
    study_design: JSONObject,
    duplicate_decision_keys: tuple[str, ...],
) -> tuple[str, ...]:
    reasons = [
        *_coverage_blocking_reasons(
            calibration=calibration,
            thresholds=thresholds,
            source_counts=source_counts,
            outcome_counts=outcome_counts,
            source_outcome_counts=source_outcome_counts,
        ),
        *_study_design_blocking_reasons(
            study_design=study_design,
            thresholds=thresholds,
        ),
        *_ranking_quality_blocking_reasons(
            calibration=calibration,
            thresholds=thresholds,
            mean_score_separation=mean_score_separation,
            roc_auc=roc_auc,
            duplicate_decision_keys=duplicate_decision_keys,
        ),
    ]
    return tuple(reasons)


def _coverage_blocking_reasons(
    *,
    calibration: ReviewRankingCalibrationSummary,
    thresholds: ReviewRankingCalibrationGateThresholds,
    source_counts: dict[str, int],
    outcome_counts: dict[str, int],
    source_outcome_counts: dict[str, dict[str, int]],
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
    if thresholds.require_positive_and_negative_per_source:
        reasons.extend(
            f"At least one {outcome} reviewer outcome is required for "
            f"source kind {source_kind}."
            for source_kind in _SOURCE_KINDS
            if source_counts[source_kind] > 0
            for outcome in _OUTCOMES
            if source_outcome_counts[source_kind][outcome] == 0
        )
    return tuple(reasons)


def _study_design_blocking_reasons(
    *,
    study_design: JSONObject,
    thresholds: ReviewRankingCalibrationGateThresholds,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if (
        _int_from_json(study_design, "distinct_goal_count")
        < thresholds.min_distinct_goals
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_distinct_goals} distinct research goals are "
            "required for production review-ranking calibration.",
        )
    if (
        _int_from_json(study_design, "distinct_evidence_shape_count")
        < thresholds.min_distinct_evidence_shapes
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_distinct_evidence_shapes} distinct evidence "
            "shapes are required for production review-ranking calibration.",
        )
    if (
        thresholds.require_reviewer_ids
        and _int_from_json(study_design, "missing_reviewer_id_count") > 0
    ):
        reasons.append("Every review-ranking decision must include a reviewer ID.")
    if (
        thresholds.min_distinct_goals > 0
        and _int_from_json(study_design, "missing_goal_count") > 0
    ):
        reasons.append("Every review-ranking decision must include a research goal.")
    if (
        thresholds.min_distinct_evidence_shapes > 0
        and _int_from_json(study_design, "missing_evidence_shape_count") > 0
    ):
        reasons.append("Every review-ranking decision must include an evidence shape.")
    if (
        thresholds.require_adjudication_note
        and study_design.get("adjudication_note_present") is not True
    ):
        reasons.append("A study-level adjudication note is required.")
    return tuple(reasons)


def _ranking_quality_blocking_reasons(
    *,
    calibration: ReviewRankingCalibrationSummary,
    thresholds: ReviewRankingCalibrationGateThresholds,
    mean_score_separation: float,
    roc_auc: float,
    duplicate_decision_keys: tuple[str, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
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


def _int_from_json(payload: JSONObject, key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _normalized_study_label(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _selection_study_summary(
    *,
    reports: tuple[EvidenceSelectionReviewReport, ...],
    study_evidence_kind: EvidenceSelectionExpertStudyEvidenceKind,
) -> JSONObject:
    precision_values = tuple(
        report.precision for report in reports if report.precision is not None
    )
    recall_values = tuple(
        report.recall for report in reports if report.recall is not None
    )
    explanation_values = tuple(
        report.explanation_quality_score
        for report in reports
        if report.explanation_quality_score is not None
    )
    reviewer_ids = {
        reviewer_id.strip()
        for report in reports
        if (reviewer_id := report.reviewer_id) and reviewer_id.strip()
    }
    goals = {
        normalized_goal
        for report in reports
        if (normalized_goal := _normalized_study_label(report.goal))
    }
    duplicate_run_ids = _duplicate_selection_run_ids(reports)
    return {
        "study_evidence_kind": study_evidence_kind,
        "review_count": len(reports),
        "distinct_goal_count": len(goals),
        "reviewer_count": len(reviewer_ids),
        "missing_reviewer_id_count": sum(
            1
            for report in reports
            if not (report.reviewer_id and report.reviewer_id.strip())
        ),
        "missing_goal_count": sum(
            1 for report in reports if not _normalized_study_label(report.goal)
        ),
        "unmeasurable_precision_count": sum(
            1 for report in reports if report.precision is None
        ),
        "unmeasurable_recall_count": sum(
            1 for report in reports if report.recall is None
        ),
        "missing_explanation_quality_count": sum(
            1 for report in reports if report.explanation_quality_score is None
        ),
        "missing_high_severity_overclaim_count": sum(
            1
            for report in reports
            if report.high_severity_overclaim_count is None
        ),
        "duplicate_run_id_count": len(duplicate_run_ids),
        "duplicate_run_ids": list(duplicate_run_ids),
        "mean_precision": _round_gate_metric(_mean(precision_values)),
        "mean_recall": _round_gate_metric(_mean(recall_values)),
        "mean_explanation_quality": _round_gate_metric(_mean(explanation_values)),
        "high_severity_overclaim_count": sum(
            report.high_severity_overclaim_count
            for report in reports
            if report.high_severity_overclaim_count is not None
        ),
        "duplicate_suggestion_count": sum(
            report.duplicate_suggestion_count for report in reports
        ),
    }


def _selection_report_to_json(report: EvidenceSelectionReviewReport) -> JSONObject:
    return {
        "run_id": str(report.run_id),
        "goal": report.goal,
        "reviewer_id": report.reviewer_id,
        "true_positive_ids": list(report.true_positive_ids),
        "false_positive_ids": list(report.false_positive_ids),
        "false_negative_ids": list(report.false_negative_ids),
        "confirmed_skip_ids": list(report.confirmed_skip_ids),
        "duplicate_suggestion_ids": list(report.duplicate_suggestion_ids),
        "precision": report.precision,
        "recall": report.recall,
        "duplicate_suggestion_count": report.duplicate_suggestion_count,
        "explanation_quality_score": report.explanation_quality_score,
        "high_severity_overclaim_count": report.high_severity_overclaim_count,
        "overclaim_gate_passed": report.overclaim_gate_passed,
        "reviewer_notes": report.reviewer_notes,
        "false_positive_notes": report.false_positive_notes,
        "false_negative_notes": report.false_negative_notes,
    }


def _duplicate_selection_run_ids(
    reports: tuple[EvidenceSelectionReviewReport, ...],
) -> tuple[str, ...]:
    seen: set[UUID] = set()
    duplicates: list[str] = []
    for report in reports:
        if report.run_id in seen:
            duplicates.append(str(report.run_id))
            continue
        seen.add(report.run_id)
    return tuple(dict.fromkeys(duplicates))


def _review_ranking_decision_key(decision: ReviewRankingCalibrationDecision) -> str:
    return f"{decision.source_kind}:{decision.item_id}"


def _expert_study_reviewer_ids(
    *,
    study: EvidenceSelectionExpertStudyInput,
    reports: tuple[EvidenceSelectionReviewReport, ...],
) -> set[str]:
    selection_reviewer_ids = {
        reviewer_id.strip()
        for report in reports
        if (reviewer_id := report.reviewer_id) and reviewer_id.strip()
    }
    ranking_reviewer_ids = {
        reviewer_id.strip()
        for decision in study.review_ranking.decisions
        if (reviewer_id := decision.reviewer_id) and reviewer_id.strip()
    }
    return selection_reviewer_ids | ranking_reviewer_ids


def _mean(values: tuple[float | int, ...]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _expert_study_blocking_reasons(
    *,
    selection_summary: JSONObject,
    provenance_summary: JSONObject,
    thresholds: EvidenceSelectionExpertStudyGateThresholds,
    review_ranking_gate: ReviewRankingCalibrationGateReport,
) -> tuple[str, ...]:
    return (
        *_expert_study_provenance_blocking_reasons(selection_summary),
        *source_manifest_blocking_reasons(
            provenance_summary=provenance_summary,
            require_source_manifest=thresholds.require_source_manifest,
            min_source_artifact_count=thresholds.min_source_artifact_count,
        ),
        *_expert_study_coverage_blocking_reasons(
            selection_summary=selection_summary,
            thresholds=thresholds,
        ),
        *_expert_study_quality_blocking_reasons(
            selection_summary=selection_summary,
            thresholds=thresholds,
        ),
        *_expert_study_ranking_blocking_reasons(review_ranking_gate),
    )


def _expert_study_provenance_blocking_reasons(
    selection_summary: JSONObject,
) -> tuple[str, ...]:
    if selection_summary.get("study_evidence_kind") == "real_shadow_review":
        return ()
    return (
        "The expert study must be real shadow-review evidence before it can "
        "support production readiness.",
    )


def _expert_study_coverage_blocking_reasons(
    *,
    selection_summary: JSONObject,
    thresholds: EvidenceSelectionExpertStudyGateThresholds,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if (
        _int_from_json(selection_summary, "review_count")
        < thresholds.min_selection_review_count
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_selection_review_count} selection review runs are "
            "required for production study evidence.",
        )
    if (
        _int_from_json(selection_summary, "distinct_goal_count")
        < thresholds.min_distinct_selection_goals
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_distinct_selection_goals} distinct selection goals "
            "are required for production study evidence.",
        )
    if (
        _int_from_json(selection_summary, "reviewer_count")
        < thresholds.min_selection_reviewer_count
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_selection_reviewer_count} selection reviewer is "
            "required for production study evidence.",
        )
    if _int_from_json(selection_summary, "missing_reviewer_id_count") > 0:
        reasons.append("Every selection review must include a reviewer ID.")
    if _int_from_json(selection_summary, "missing_goal_count") > 0:
        reasons.append("Every selection review must include a research goal.")
    if _int_from_json(selection_summary, "duplicate_run_id_count") > 0:
        reasons.append("Selection review run IDs must be unique.")
    if _int_from_json(selection_summary, "unmeasurable_precision_count") > 0:
        reasons.append("Every selection review must have measurable precision.")
    if _int_from_json(selection_summary, "unmeasurable_recall_count") > 0:
        reasons.append("Every selection review must have measurable recall.")
    if _int_from_json(selection_summary, "missing_explanation_quality_count") > 0:
        reasons.append(
            "Every selection review must include an explanation-quality score.",
        )
    return tuple(reasons)


def _expert_study_quality_blocking_reasons(
    *,
    selection_summary: JSONObject,
    thresholds: EvidenceSelectionExpertStudyGateThresholds,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if _float_from_json(selection_summary, "mean_precision") < thresholds.min_mean_precision:
        reasons.append(
            "Expert/shadow mean selection precision is below target: "
            f"{_float_from_json(selection_summary, 'mean_precision'):.6f} < "
            f"{thresholds.min_mean_precision:.6f}.",
        )
    if _float_from_json(selection_summary, "mean_recall") < thresholds.min_mean_recall:
        reasons.append(
            "Expert/shadow mean selection recall is below target: "
            f"{_float_from_json(selection_summary, 'mean_recall'):.6f} < "
            f"{thresholds.min_mean_recall:.6f}.",
        )
    if (
        _float_from_json(selection_summary, "mean_explanation_quality")
        < thresholds.min_mean_explanation_quality
    ):
        reasons.append(
            "Expert/shadow mean explanation quality is below target: "
            f"{_float_from_json(selection_summary, 'mean_explanation_quality'):.6f} < "
            f"{thresholds.min_mean_explanation_quality:.6f}.",
        )
    if (
        thresholds.require_zero_high_severity_overclaims
        and _int_from_json(
            selection_summary,
            "missing_high_severity_overclaim_count",
        )
        > 0
    ):
        reasons.append(
            "Every selection review must include a high-severity overclaim count.",
        )
    if (
        thresholds.require_zero_high_severity_overclaims
        and _int_from_json(selection_summary, "high_severity_overclaim_count") > 0
    ):
        reasons.append("High-severity overclaim count must be zero.")
    return tuple(reasons)


def _expert_study_ranking_blocking_reasons(
    review_ranking_gate: ReviewRankingCalibrationGateReport,
) -> tuple[str, ...]:
    if review_ranking_gate.passed:
        return ()
    return (
        "Review-ranking gate failed: "
        f"{'; '.join(review_ranking_gate.blocking_reasons)}",
    )


def _float_from_json(payload: JSONObject, key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


__all__ = [
    "EvidenceSelectionExpertStudyGateReport",
    "EvidenceSelectionExpertStudyGateThresholds",
    "EvidenceSelectionExpertStudyInput",
    "EvidenceSelectionExpertStudySourceArtifact",
    "EvidenceSelectionExpertStudySourceManifest",
    "EvidenceSelectionReviewInput",
    "EvidenceSelectionReviewReport",
    "ReviewRankingCalibrationDecision",
    "ReviewRankingCalibrationGateReport",
    "ReviewRankingCalibrationStudyInput",
    "ReviewRankingCalibrationGateThresholds",
    "compare_evidence_selection_review",
    "evaluate_evidence_selection_expert_study_gate",
    "evaluate_review_ranking_calibration_gate",
]
