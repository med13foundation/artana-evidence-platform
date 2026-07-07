"""Score calibration metrics for relation feasibility candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.validation.relation_feasibility.models import CandidateAssessment

_DEFAULT_BIN_COUNT = 10


@dataclass(frozen=True, slots=True)
class ScoreCalibrationMetricCounts:
    """Expected calibration error summary for candidate quality scores."""

    sample_count: int
    mean_score: float
    observed_positive_rate: float
    expected_calibration_error: float


def build_score_calibration_metric_counts(
    candidates: tuple[CandidateAssessment, ...],
    *,
    trusted_only: bool = False,
    bin_count: int = _DEFAULT_BIN_COUNT,
) -> ScoreCalibrationMetricCounts:
    """Return ECE for candidate quality scores against observed value labels."""

    scored_candidates = tuple(
        candidate
        for candidate in candidates
        if not trusted_only or candidate.is_trusted_evidence_eligible
    )
    scored_pairs = tuple(
        (
            _candidate_quality_score(candidate),
            1.0 if candidate.is_supported_by_gold else 0.0,
        )
        for candidate in scored_candidates
    )
    sample_count = len(scored_pairs)
    if sample_count == 0:
        return ScoreCalibrationMetricCounts(
            sample_count=0,
            mean_score=0.0,
            observed_positive_rate=0.0,
            expected_calibration_error=0.0,
        )
    return ScoreCalibrationMetricCounts(
        sample_count=sample_count,
        mean_score=_round_metric(
            sum(score for score, _outcome in scored_pairs) / sample_count,
        ),
        observed_positive_rate=_round_metric(
            sum(outcome for _score, outcome in scored_pairs) / sample_count,
        ),
        expected_calibration_error=_expected_calibration_error(
            scored_pairs=scored_pairs,
            bin_count=bin_count,
        ),
    )


def _candidate_quality_score(candidate: CandidateAssessment) -> float:
    score = (
        (0.20 if candidate.has_grounded_sentence else 0.0)
        + (0.20 if candidate.has_both_arguments_in_sentence else 0.0)
        + (0.25 if candidate.has_entailment_support else 0.0)
        + (0.15 if candidate.is_relation_specific else 0.0)
        + (
            0.10
            if candidate.has_specific_subject and candidate.has_specific_object
            else 0.0
        )
        + (0.10 if candidate.has_known_relation_type else 0.0)
    )
    return _round_metric(score)


def _expected_calibration_error(
    *,
    scored_pairs: tuple[tuple[float, float], ...],
    bin_count: int,
) -> float:
    if bin_count <= 0:
        msg = "bin_count must be positive"
        raise ValueError(msg)
    total_count = len(scored_pairs)
    error = 0.0
    for bin_index in range(bin_count):
        bin_items = tuple(
            pair
            for pair in scored_pairs
            if _bin_index(score=pair[0], bin_count=bin_count) == bin_index
        )
        if not bin_items:
            continue
        bin_confidence = sum(score for score, _outcome in bin_items) / len(bin_items)
        bin_accuracy = sum(outcome for _score, outcome in bin_items) / len(bin_items)
        error += (len(bin_items) / total_count) * abs(bin_confidence - bin_accuracy)
    return _round_metric(error)


def _bin_index(*, score: float, bin_count: int) -> int:
    bounded_score = max(0.0, min(score, 1.0))
    if bounded_score == 1.0:
        return bin_count - 1
    return int(bounded_score * bin_count)


def _round_metric(value: float) -> float:
    return round(value, 4)


__all__ = [
    "ScoreCalibrationMetricCounts",
    "build_score_calibration_metric_counts",
]
