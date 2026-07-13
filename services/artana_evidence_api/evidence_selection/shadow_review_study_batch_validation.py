"""Validation policy for shadow-review study batch thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from artana_evidence_api.types.common import JSONObject


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewStudyBatchSuiteThresholds:
    """Thresholds for claiming a completed-packet batch is study evidence."""

    min_entry_count: int = 3
    min_passed_entry_count: int = 3
    max_failed_entry_count: int = 0
    min_passed_entry_rate: float = 1.0
    min_suite_mean_precision: float = 0.8
    min_suite_mean_recall: float = 0.8
    min_suite_explanation_adequacy_rate: float = 0.8
    max_suite_expected_calibration_error: float = 0.05
    min_total_selection_review_count: int = 3
    min_total_review_ranking_decision_count: int = 10
    min_distinct_source_run_ids: int = 3
    min_distinct_study_ids: int = 3
    min_distinct_selection_goals: int = 3
    min_distinct_review_ranking_goals: int = 3
    min_distinct_review_ranking_research_questions: int = 8
    min_distinct_evidence_shapes: int = 3


def validate_shadow_review_study_batch_suite_thresholds(
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> None:
    """Reject invalid or non-finite suite thresholds before floors are applied."""

    float_thresholds = {
        "min_passed_entry_rate": thresholds.min_passed_entry_rate,
        "min_suite_mean_precision": thresholds.min_suite_mean_precision,
        "min_suite_mean_recall": thresholds.min_suite_mean_recall,
        "min_suite_explanation_adequacy_rate": (
            thresholds.min_suite_explanation_adequacy_rate
        ),
        "max_suite_expected_calibration_error": (
            thresholds.max_suite_expected_calibration_error
        ),
    }
    for float_name, float_value in float_thresholds.items():
        if not isfinite(float_value):
            msg = f"{float_name} must be finite."
            raise ValueError(msg)

    count_thresholds = {
        "min_entry_count": thresholds.min_entry_count,
        "min_passed_entry_count": thresholds.min_passed_entry_count,
        "max_failed_entry_count": thresholds.max_failed_entry_count,
        "min_total_selection_review_count": thresholds.min_total_selection_review_count,
        "min_total_review_ranking_decision_count": (
            thresholds.min_total_review_ranking_decision_count
        ),
        "min_distinct_source_run_ids": thresholds.min_distinct_source_run_ids,
        "min_distinct_study_ids": thresholds.min_distinct_study_ids,
        "min_distinct_selection_goals": thresholds.min_distinct_selection_goals,
        "min_distinct_review_ranking_goals": (
            thresholds.min_distinct_review_ranking_goals
        ),
        "min_distinct_review_ranking_research_questions": (
            thresholds.min_distinct_review_ranking_research_questions
        ),
        "min_distinct_evidence_shapes": thresholds.min_distinct_evidence_shapes,
    }
    for count_name, count_value in count_thresholds.items():
        if count_value < 0:
            msg = f"{count_name} must be non-negative."
            raise ValueError(msg)

    if thresholds.min_passed_entry_rate < 0 or thresholds.min_passed_entry_rate > 1:
        msg = "min_passed_entry_rate must be between 0 and 1."
        raise ValueError(msg)
    bounded_float_thresholds = {
        "min_suite_mean_precision": thresholds.min_suite_mean_precision,
        "min_suite_mean_recall": thresholds.min_suite_mean_recall,
        "min_suite_explanation_adequacy_rate": (
            thresholds.min_suite_explanation_adequacy_rate
        ),
        "max_suite_expected_calibration_error": (
            thresholds.max_suite_expected_calibration_error
        ),
    }
    for float_name, float_value in bounded_float_thresholds.items():
        if float_value < 0 or float_value > 1:
            msg = f"{float_name} must be between 0 and 1."
            raise ValueError(msg)


def shadow_review_study_batch_suite_thresholds_to_json(
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> JSONObject:
    """Serialize suite policy thresholds for immutable gate reports."""

    return {
        "min_entry_count": thresholds.min_entry_count,
        "min_passed_entry_count": thresholds.min_passed_entry_count,
        "max_failed_entry_count": thresholds.max_failed_entry_count,
        "min_passed_entry_rate": thresholds.min_passed_entry_rate,
        "min_suite_mean_precision": thresholds.min_suite_mean_precision,
        "min_suite_mean_recall": thresholds.min_suite_mean_recall,
        "min_suite_explanation_adequacy_rate": (
            thresholds.min_suite_explanation_adequacy_rate
        ),
        "max_suite_expected_calibration_error": (
            thresholds.max_suite_expected_calibration_error
        ),
        "min_total_selection_review_count": (
            thresholds.min_total_selection_review_count
        ),
        "min_total_review_ranking_decision_count": (
            thresholds.min_total_review_ranking_decision_count
        ),
        "min_distinct_source_run_ids": thresholds.min_distinct_source_run_ids,
        "min_distinct_study_ids": thresholds.min_distinct_study_ids,
        "min_distinct_selection_goals": thresholds.min_distinct_selection_goals,
        "min_distinct_review_ranking_goals": (
            thresholds.min_distinct_review_ranking_goals
        ),
        "min_distinct_review_ranking_research_questions": (
            thresholds.min_distinct_review_ranking_research_questions
        ),
        "min_distinct_evidence_shapes": thresholds.min_distinct_evidence_shapes,
    }


__all__ = [
    "EvidenceSelectionShadowReviewStudyBatchSuiteThresholds",
    "shadow_review_study_batch_suite_thresholds_to_json",
    "validate_shadow_review_study_batch_suite_thresholds",
]
