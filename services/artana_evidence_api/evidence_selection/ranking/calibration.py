"""Abstention-aware calibration metrics for governed ranking probabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.evidence_selection.ranking.contracts import (
    ReviewRankingCalibrationDecision,
)
from artana_evidence_api.types.common import JSONObject

CalibrationAvailability = Literal[
    "unavailable",
    "incomplete",
    "diagnostic",
]


@dataclass(frozen=True, slots=True)
class CalibrationReliabilityBin:
    """One populated calibrated-probability reliability bin."""

    lower_bound: float
    upper_bound: float
    sample_count: int
    mean_probability: float
    observed_positive_rate: float
    absolute_error: float

    def to_json(self) -> JSONObject:
        """Return a stable artifact representation."""
        return {
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "sample_count": self.sample_count,
            "mean_probability": self.mean_probability,
            "observed_positive_rate": self.observed_positive_rate,
            "absolute_error": self.absolute_error,
        }


@dataclass(frozen=True, slots=True)
class RankingProbabilityCalibrationSummary:
    """Calibration summary that never treats an operational weight as probability."""

    availability: CalibrationAvailability
    sample_count: int
    probability_count: int
    decided_probability_count: int
    abstention_count: int
    abstention_rate: float
    mean_probability: float | None
    observed_positive_rate: float | None
    expected_calibration_error: float | None
    reliability_bins: tuple[CalibrationReliabilityBin, ...]

    def to_json(self) -> JSONObject:
        """Return a stable artifact representation."""
        return {
            "availability": self.availability,
            "sample_count": self.sample_count,
            "probability_count": self.probability_count,
            "decided_probability_count": self.decided_probability_count,
            "abstention_count": self.abstention_count,
            "abstention_rate": self.abstention_rate,
            "mean_probability": self.mean_probability,
            "observed_positive_rate": self.observed_positive_rate,
            "expected_calibration_error": self.expected_calibration_error,
            "reliability_bins": [item.to_json() for item in self.reliability_bins],
        }


def build_ranking_probability_calibration_summary(
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
    *,
    bin_count: int = 10,
) -> RankingProbabilityCalibrationSummary:
    """Measure only explicit calibrated probabilities against reviewer outcomes."""

    if bin_count < 1:
        msg = "bin_count must be at least 1"
        raise ValueError(msg)
    sample_count = len(decisions)
    abstention_count = sum(
        1 for decision in decisions if decision.outcome == "abstained"
    )
    probability_decisions = tuple(
        decision
        for decision in decisions
        if decision.calibrated_probability is not None
    )
    decided_probability_decisions = tuple(
        decision
        for decision in probability_decisions
        if decision.has_decided_outcome
    )
    availability = _calibration_availability(
        decisions=decisions,
        probability_decisions=probability_decisions,
    )
    reliability_bins = _reliability_bins(
        decisions=decided_probability_decisions,
        bin_count=bin_count,
    )
    decided_probability_count = len(decided_probability_decisions)
    if decided_probability_count == 0:
        mean_probability = None
        observed_positive_rate = None
        expected_calibration_error = None
    else:
        probabilities = tuple(
            _probability_value(decision) for decision in decided_probability_decisions
        )
        mean_probability = _round_metric(
            sum(probabilities) / decided_probability_count,
        )
        observed_positive_rate = _round_metric(
            sum(
                1.0 if decision.outcome == "positive" else 0.0
                for decision in decided_probability_decisions
            )
            / decided_probability_count,
        )
        expected_calibration_error = _round_metric(
            sum(
                (item.sample_count / decided_probability_count) * item.absolute_error
                for item in reliability_bins
            ),
        )
    return RankingProbabilityCalibrationSummary(
        availability=availability,
        sample_count=sample_count,
        probability_count=len(probability_decisions),
        decided_probability_count=decided_probability_count,
        abstention_count=abstention_count,
        abstention_rate=(
            _round_metric(abstention_count / sample_count) if sample_count else 0.0
        ),
        mean_probability=mean_probability,
        observed_positive_rate=observed_positive_rate,
        expected_calibration_error=expected_calibration_error,
        reliability_bins=reliability_bins,
    )


def _calibration_availability(
    *,
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
    probability_decisions: tuple[ReviewRankingCalibrationDecision, ...],
) -> CalibrationAvailability:
    if not probability_decisions:
        return "unavailable"
    if len(probability_decisions) != len(decisions):
        return "incomplete"
    return "diagnostic"


def _reliability_bins(
    *,
    decisions: tuple[ReviewRankingCalibrationDecision, ...],
    bin_count: int,
) -> tuple[CalibrationReliabilityBin, ...]:
    bins: list[CalibrationReliabilityBin] = []
    for bin_index in range(bin_count):
        bin_decisions = tuple(
            decision
            for decision in decisions
            if _calibration_bin_index(
                probability=_probability_value(decision),
                bin_count=bin_count,
            )
            == bin_index
        )
        if not bin_decisions:
            continue
        mean_probability = sum(
            _probability_value(decision) for decision in bin_decisions
        ) / len(bin_decisions)
        observed_positive_rate = sum(
            1.0 if decision.outcome == "positive" else 0.0
            for decision in bin_decisions
        ) / len(bin_decisions)
        bins.append(
            CalibrationReliabilityBin(
                lower_bound=_round_metric(bin_index / bin_count),
                upper_bound=_round_metric((bin_index + 1) / bin_count),
                sample_count=len(bin_decisions),
                mean_probability=_round_metric(mean_probability),
                observed_positive_rate=_round_metric(observed_positive_rate),
                absolute_error=_round_metric(
                    abs(mean_probability - observed_positive_rate),
                ),
            ),
        )
    return tuple(bins)


def _probability_value(decision: ReviewRankingCalibrationDecision) -> float:
    probability = decision.calibrated_probability
    if probability is None:
        msg = "calibration metrics require an explicit calibrated probability"
        raise ValueError(msg)
    return probability.value


def _calibration_bin_index(*, probability: float, bin_count: int) -> int:
    if probability == 1.0:
        return bin_count - 1
    return int(probability * bin_count)


def _round_metric(value: float) -> float:
    return round(value, 6)


__all__ = [
    "CalibrationAvailability",
    "CalibrationReliabilityBin",
    "RankingProbabilityCalibrationSummary",
    "build_ranking_probability_calibration_summary",
]
