"""Regression tests for TG-04 three-run arm comparison."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from scripts.validation.claim_events.comparison import compare_three_run_arms
from scripts.validation.claim_events.scoring import CountRate


@dataclass(frozen=True)
class Argument:
    role: str
    event_role: str
    exact_span: str
    source_start: int


@dataclass(frozen=True)
class Event:
    event_id: str
    trigger_span: str
    trigger_source_start: int
    event_type: str
    polarity: str
    epistemic_status: str
    arguments: tuple[Argument, ...]
    valuable: object = False
    supported_projections: object = ()
    eligibility: object = True


@dataclass(frozen=True)
class Case:
    case_id: str
    events: tuple[Event, ...]


@dataclass(frozen=True)
class Fixture:
    cases: tuple[Case, ...]


def _gold(case_id: str) -> Event:
    return Event(
        event_id=f"{case_id}-event",
        trigger_span=f"trigger-{case_id}",
        trigger_source_start=15,
        event_type="ASSOCIATION",
        polarity="SUPPORT",
        epistemic_status="OBSERVED",
        arguments=(Argument("subject", "AGENT", f"entity-{case_id}", 0),),
    )


def _prediction(case_id: str, *, correct: bool, rationale: str = "same") -> dict[str, object]:
    return {
        "event_id": f"{case_id}-event",
        "trigger_span": f"trigger-{case_id}",
        "trigger_source_start": 15,
        "event_type": "ASSOCIATION" if correct else "GENERIC_RELATION",
        "polarity": "SUPPORT",
        "epistemic_status": "OBSERVED",
        "arguments": [
            {
                "role": "subject",
                "event_role": "AGENT",
                "exact_span": f"entity-{case_id}",
                "source_start": 0,
            },
        ],
        "supported_projections": [],
        "rationale": rationale,
    }


def _run(states: dict[str, bool], *, rationale: str = "same") -> dict[str, object]:
    return {
        case_id: [_prediction(case_id, correct=correct, rationale=rationale)]
        for case_id, correct in states.items()
    }


def _fixture() -> Fixture:
    case_ids = ("improved", "stable-wrong", "stable-correct", "regressed")
    return Fixture(tuple(Case(case_id, (_gold(case_id),)) for case_id in case_ids))


def test_comparison_requires_exactly_three_runs_per_arm() -> None:
    fixture = _fixture()
    run = _run(
        {
            "improved": False,
            "stable-wrong": False,
            "stable-correct": True,
            "regressed": True,
        },
    )

    with pytest.raises(ValueError, match="baseline arm must contain exactly three"):
        compare_three_run_arms(fixture, [run, run], [run, run, run])

    with pytest.raises(ValueError, match="candidate arm must contain exactly three"):
        compare_three_run_arms(fixture, [run, run, run], [run, run])


def test_comparison_separates_exact_canonical_and_paired_quality() -> None:
    fixture = _fixture()
    baseline_state = {
        "improved": False,
        "stable-wrong": False,
        "stable-correct": True,
        "regressed": True,
    }
    candidate_state = {
        "improved": True,
        "stable-wrong": False,
        "stable-correct": True,
        "regressed": False,
    }
    baseline = [_run(baseline_state) for _ in range(3)]
    candidate = [
        _run(candidate_state, rationale=f"run-{run_number}")
        for run_number in range(3)
    ]

    result = compare_three_run_arms(fixture, baseline, candidate)

    assert result.baseline_repeatability.exact == CountRate.of(4, 4)
    assert result.baseline_repeatability.canonical == CountRate.of(4, 4)
    assert result.candidate_repeatability.exact == CountRate.of(0, 4)
    assert result.candidate_repeatability.canonical == CountRate.of(4, 4)
    assert result.transitions.improved == CountRate.of(3, 12)
    assert result.transitions.unchanged_correct == CountRate.of(3, 12)
    assert result.transitions.unchanged_incorrect == CountRate.of(3, 12)
    assert result.transitions.regressed == CountRate.of(3, 12)
    assert result.transitions.event_quality_credit == CountRate.of(6, 12)


def test_stable_but_wrong_receives_repeatability_not_quality_credit() -> None:
    fixture = Fixture((Case("wrong", (_gold("wrong"),)),))
    wrong_run = _run({"wrong": False})

    result = compare_three_run_arms(
        fixture,
        [wrong_run, wrong_run, wrong_run],
        [wrong_run, wrong_run, wrong_run],
    )

    assert result.candidate_repeatability.canonical == CountRate.of(1, 1)
    assert result.transitions.unchanged_incorrect == CountRate.of(3, 3)
    assert result.transitions.event_quality_credit == CountRate.of(0, 3)


def test_unadjudicated_value_does_not_erase_exact_event_quality() -> None:
    event = Event(
        event_id="unknown-event",
        trigger_span="trigger-unknown",
        trigger_source_start=15,
        event_type="ASSOCIATION",
        polarity="SUPPORT",
        epistemic_status="OBSERVED",
        arguments=(Argument("subject", "AGENT", "entity-unknown", 0),),
        valuable="UNADJUDICATED",
        supported_projections="UNADJUDICATED",
    )
    fixture = Fixture((Case("unknown", (event,)),))
    run = _run({"unknown": True})

    result = compare_three_run_arms(
        fixture,
        [run, run, run],
        [run, run, run],
    )

    assert result.transitions.unchanged_correct == CountRate.of(3, 3)
    assert result.transitions.unchanged_incorrect == CountRate.of(0, 3)
    assert result.transitions.event_quality_credit == CountRate.of(3, 3)
