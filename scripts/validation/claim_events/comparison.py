"""Three-run repeatability and paired quality comparison for TG-04."""

from __future__ import annotations

import json
from dataclasses import dataclass

from scripts.validation.claim_events.scoring import (
    BenchmarkFixtureContract,
    CaseScore,
    CountRate,
    FixtureScore,
    score_fixture,
)

_REQUIRED_RUNS = 3


@dataclass(frozen=True, slots=True)
class ArmRepeatability:
    """Case-level identity across exactly three runs of one arm."""

    exact: CountRate
    canonical: CountRate


@dataclass(frozen=True, slots=True)
class PairedTransitions:
    """Quality transitions across run- and case-matched observations."""

    improved: CountRate
    unchanged_correct: CountRate
    unchanged_incorrect: CountRate
    regressed: CountRate
    event_quality_credit: CountRate


@dataclass(frozen=True, slots=True)
class ArmComparison:
    baseline_repeatability: ArmRepeatability
    candidate_repeatability: ArmRepeatability
    transitions: PairedTransitions
    baseline_scores: tuple[FixtureScore, ...]
    candidate_scores: tuple[FixtureScore, ...]


def compare_three_run_arms(
    fixture: BenchmarkFixtureContract,
    baseline_runs: object,
    candidate_runs: object,
) -> ArmComparison:
    """Compare paired case outcomes while keeping stability separate from quality."""

    baseline = _three_runs(baseline_runs, "baseline")
    candidate = _three_runs(candidate_runs, "candidate")
    baseline_scores = tuple(score_fixture(fixture, run) for run in baseline)
    candidate_scores = tuple(score_fixture(fixture, run) for run in candidate)
    return ArmComparison(
        baseline_repeatability=_repeatability(baseline_scores),
        candidate_repeatability=_repeatability(candidate_scores),
        transitions=_transitions(baseline_scores, candidate_scores),
        baseline_scores=baseline_scores,
        candidate_scores=candidate_scores,
    )


def _three_runs(value: object, arm: str) -> tuple[object, object, object]:
    if not isinstance(value, list | tuple) or len(value) != _REQUIRED_RUNS:
        raise ValueError(f"{arm} arm must contain exactly three runs")
    return value[0], value[1], value[2]


def _repeatability(scores: tuple[FixtureScore, ...]) -> ArmRepeatability:
    case_count = len(scores[0].cases)
    exact = canonical = 0
    for case_index in range(case_count):
        cases = tuple(score.cases[case_index] for score in scores)
        _require_same_case(cases)
        exact += len({_exact_prediction(case) for case in cases}) == 1
        canonical += len({case.canonical_prediction for case in cases}) == 1
    return ArmRepeatability(
        exact=CountRate.of(exact, case_count),
        canonical=CountRate.of(canonical, case_count),
    )


def _transitions(
    baseline: tuple[FixtureScore, ...],
    candidate: tuple[FixtureScore, ...],
) -> PairedTransitions:
    counts = {
        "improved": 0,
        "unchanged_correct": 0,
        "unchanged_incorrect": 0,
        "regressed": 0,
    }
    denominator = 0
    for baseline_run, candidate_run in zip(baseline, candidate, strict=True):
        if len(baseline_run.cases) != len(candidate_run.cases):
            raise ValueError("paired runs must contain the same cases")
        for before, after in zip(
            baseline_run.cases,
            candidate_run.cases,
            strict=True,
        ):
            _require_same_case((before, after))
            denominator += 1
            if not before.correct and after.correct:
                counts["improved"] += 1
            elif before.correct and after.correct:
                counts["unchanged_correct"] += 1
            elif not before.correct and not after.correct:
                counts["unchanged_incorrect"] += 1
            else:
                counts["regressed"] += 1
    event_quality_credit = counts["improved"] + counts["unchanged_correct"]
    return PairedTransitions(
        improved=CountRate.of(counts["improved"], denominator),
        unchanged_correct=CountRate.of(counts["unchanged_correct"], denominator),
        unchanged_incorrect=CountRate.of(counts["unchanged_incorrect"], denominator),
        regressed=CountRate.of(counts["regressed"], denominator),
        event_quality_credit=CountRate.of(event_quality_credit, denominator),
    )


def _exact_prediction(case: CaseScore) -> str:
    return json.dumps(
        case.raw_prediction,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _require_same_case(cases: tuple[CaseScore, ...]) -> None:
    case_ids = {case.case_id for case in cases}
    if len(case_ids) != 1:
        raise ValueError(f"paired case ids differ: {sorted(case_ids)}")


__all__ = [
    "ArmComparison",
    "ArmRepeatability",
    "PairedTransitions",
    "compare_three_run_arms",
]
