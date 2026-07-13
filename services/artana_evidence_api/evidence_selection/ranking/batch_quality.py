"""Ranking-quality aggregation for completed shadow-review study batches."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from artana_evidence_api.evidence_selection.shadow_review_study_batch_validation import (
    EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
)
from artana_evidence_api.types.common import JSONObject


class BatchQualityEntry(Protocol):
    """Minimal batch-entry view needed for quality aggregation."""

    @property
    def gate_report(self) -> Mapping[str, object]:
        """Return the expert-study gate report for this entry."""
        ...


@dataclass(frozen=True, slots=True)
class BatchQualityMetrics:
    """Unrounded quality observations used by the suite gate."""

    suite_mean_precision: float
    suite_mean_recall: float
    suite_explanation_adequacy_rate: float
    max_review_ranking_expected_calibration_error: float | None
    unavailable_review_ranking_calibration_count: int

    def to_json(self) -> JSONObject:
        """Return rounded report values without converting missing ECE to zero."""

        return {
            "suite_mean_precision": round(self.suite_mean_precision, 4),
            "suite_mean_recall": round(self.suite_mean_recall, 4),
            "suite_explanation_adequacy_rate": round(
                self.suite_explanation_adequacy_rate,
                4,
            ),
            "max_review_ranking_expected_calibration_error": (
                round(self.max_review_ranking_expected_calibration_error, 6)
                if self.max_review_ranking_expected_calibration_error is not None
                else None
            ),
            "unavailable_review_ranking_calibration_count": (
                self.unavailable_review_ranking_calibration_count
            ),
        }


def build_batch_quality_metrics(
    entries: Sequence[BatchQualityEntry],
) -> BatchQualityMetrics:
    """Aggregate selection quality and explicit calibrated-probability ECE."""

    total_review_count = 0
    weighted_precision = 0.0
    weighted_recall = 0.0
    weighted_explanation_adequacy = 0.0
    calibration_errors: list[float] = []
    unavailable_calibration_count = 0
    for entry in entries:
        gate = _object_value(entry.gate_report, "gate")
        selection_summary = _object_value(gate, "selection_summary")
        review_count = _int_value(selection_summary.get("review_count"))
        if review_count > 0:
            total_review_count += review_count
            weighted_precision += (
                _float_value(selection_summary.get("mean_precision")) * review_count
            )
            weighted_recall += (
                _float_value(selection_summary.get("mean_recall")) * review_count
            )
            weighted_explanation_adequacy += (
                _float_value(selection_summary.get("explanation_adequacy_rate"))
                * review_count
            )
        review_ranking_gate = gate.get("review_ranking_gate")
        if not isinstance(review_ranking_gate, dict):
            continue
        calibration = _object_value(review_ranking_gate, "calibration")
        calibration_error = _optional_float_value(
            calibration.get("expected_calibration_error"),
        )
        if calibration_error is None:
            unavailable_calibration_count += 1
        else:
            calibration_errors.append(calibration_error)
    return BatchQualityMetrics(
        suite_mean_precision=_ratio(
            numerator=weighted_precision,
            denominator=total_review_count,
        ),
        suite_mean_recall=_ratio(
            numerator=weighted_recall,
            denominator=total_review_count,
        ),
        suite_explanation_adequacy_rate=_ratio(
            numerator=weighted_explanation_adequacy,
            denominator=total_review_count,
        ),
        max_review_ranking_expected_calibration_error=(
            max(calibration_errors) if calibration_errors else None
        ),
        unavailable_review_ranking_calibration_count=unavailable_calibration_count,
    )


def batch_quality_blocking_reasons(
    *,
    raw_quality_metrics: BatchQualityMetrics,
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> tuple[str, ...]:
    """Return suite blockers from unrounded quality observations."""

    reasons: list[str] = []
    if raw_quality_metrics.suite_mean_precision < thresholds.min_suite_mean_precision:
        reasons.append(
            "Batch suite mean precision is below target: "
            f"{raw_quality_metrics.suite_mean_precision:.6f} < "
            f"{thresholds.min_suite_mean_precision:.6f}.",
        )
    if raw_quality_metrics.suite_mean_recall < thresholds.min_suite_mean_recall:
        reasons.append(
            "Batch suite mean recall is below target: "
            f"{raw_quality_metrics.suite_mean_recall:.6f} < "
            f"{thresholds.min_suite_mean_recall:.6f}.",
        )
    if (
        raw_quality_metrics.suite_explanation_adequacy_rate
        < thresholds.min_suite_explanation_adequacy_rate
    ):
        reasons.append(
            "Batch suite explanation adequacy rate is below target: "
            f"{raw_quality_metrics.suite_explanation_adequacy_rate:.6f} < "
            f"{thresholds.min_suite_explanation_adequacy_rate:.6f}.",
        )
    observed = raw_quality_metrics.max_review_ranking_expected_calibration_error
    unavailable_count = raw_quality_metrics.unavailable_review_ranking_calibration_count
    if unavailable_count > 0:
        reasons.append(
            "Batch review-ranking calibration is unavailable for "
            f"{unavailable_count} entries.",
        )
    elif observed is not None and observed > thresholds.max_suite_expected_calibration_error:
        reasons.append(
            "Batch review-ranking calibration ECE is above target: "
            f"{observed:.6f} > "
            f"{thresholds.max_suite_expected_calibration_error:.6f}.",
        )
    return tuple(reasons)


def _object_value(payload: Mapping[str, object], key: str) -> JSONObject:
    value = payload.get(key)
    if isinstance(value, dict):
        return dict(value)
    return {}


def _ratio(*, numerator: float, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _float_value(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _optional_float_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


__all__ = [
    "BatchQualityEntry",
    "BatchQualityMetrics",
    "batch_quality_blocking_reasons",
    "build_batch_quality_metrics",
]
