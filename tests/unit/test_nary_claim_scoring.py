"""Regression tests for deterministic TG-04 n-ary claim scoring."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from scripts.validation.claim_events.scoring import CountRate, score_fixture


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
    valuable: object
    supported_projections: object
    eligibility: object = True


@dataclass(frozen=True)
class Case:
    case_id: str
    events: tuple[Event, ...]
    control_status: str = "EVENT_GOLD"


@dataclass(frozen=True)
class Fixture:
    cases: tuple[Case, ...]


def _event(
    *,
    event_id: str = "event-1",
    polarity: str = "SUPPORT",
    valuable: object = True,
    projections: object = ("drug->disease",),
    eligibility: object = True,
    epistemic_status: str = "OBSERVED",
) -> Event:
    return Event(
        event_id=event_id,
        trigger_span="inhibited",
        trigger_source_start=8,
        event_type="INHIBITION",
        polarity=polarity,
        epistemic_status=epistemic_status,
        arguments=(
            Argument("subject", "AGENT", "aspirin", 0),
            Argument("object", "TARGET", "platelet aggregation", 17),
        ),
        valuable=valuable,
        supported_projections=projections,
        eligibility=eligibility,
    )


def _prediction(
    *,
    polarity: str = "SUPPORT",
    event_role: str = "AGENT",
    projections: tuple[str, ...] = ("drug->disease",),
    epistemic_status: str = "OBSERVED",
) -> dict[str, object]:
    return {
        "event_id": "event-1",
        "trigger_span": "inhibited",
        "trigger_source_start": 8,
        "event_type": "INHIBITION",
        "polarity": polarity,
        "epistemic_status": epistemic_status,
        "arguments": [
            {
                "role": "subject",
                "event_role": event_role,
                "exact_span": "aspirin",
                "source_start": 0,
            },
            {
                "role": "object",
                "event_role": "TARGET",
                "exact_span": "platelet aggregation",
                "source_start": 17,
            },
        ],
        "supported_projections": list(projections),
    }


def test_perfect_event_reports_explicit_counts_denominators_and_rates() -> None:
    fixture = Fixture((Case("positive", (_event(valuable="VALUABLE"),)),))

    score = score_fixture(fixture, {"positive": [_prediction()]})
    metrics = score.metrics

    assert metrics.whole_event_precision == CountRate.of(1, 1)
    assert metrics.whole_event_recall == CountRate.of(1, 1)
    assert metrics.trigger_precision == CountRate.of(1, 1)
    assert metrics.trigger_recall == CountRate.of(1, 1)
    assert metrics.valuable_recall == CountRate.of(1, 1)
    assert metrics.trigger_fidelity == CountRate.of(1, 1)
    assert metrics.event_type_fidelity == CountRate.of(1, 1)
    assert metrics.event_type_precision_by_category == {
        "INHIBITION": CountRate.of(1, 1),
    }
    assert metrics.event_type_recall_by_category == {
        "INHIBITION": CountRate.of(1, 1),
    }
    assert metrics.argument_fidelity == CountRate.of(2, 2)
    assert metrics.argument_precision == CountRate.of(2, 2)
    assert metrics.argument_recall == CountRate.of(2, 2)
    assert metrics.argument_set_fidelity == CountRate.of(1, 1)
    assert metrics.polarity_fidelity == CountRate.of(1, 1)
    assert metrics.epistemic_fidelity == CountRate.of(1, 1)
    assert metrics.projection_precision == CountRate.of(1, 1)
    assert metrics.projection_recall == CountRate.of(1, 1)
    assert metrics.projection_unsupported_rate == CountRate.of(0, 1)
    assert score.cases[0].correct is True


def test_scoring_separates_whole_event_role_loss_and_unsupported_projection() -> None:
    fixture = Fixture((Case("positive", (_event(),)),))
    prediction = _prediction(
        event_role="GENERIC",
        projections=("drug->disease", "unsupported"),
    )

    metrics = score_fixture(fixture, {"positive": [prediction]}).metrics

    assert metrics.whole_event_precision == CountRate.of(0, 1)
    assert metrics.whole_event_recall == CountRate.of(0, 1)
    assert metrics.argument_fidelity == CountRate.of(1, 2)
    assert metrics.role_loss_generic_rate == CountRate.of(1, 2)
    assert metrics.projection_precision == CountRate.of(1, 2)
    assert metrics.projection_recall == CountRate.of(1, 1)
    assert metrics.projection_unsupported_rate == CountRate.of(1, 2)


def test_unadjudicated_value_and_projections_are_excluded_not_passed() -> None:
    fixture = Fixture(
        (
            Case(
                "unknown-labels",
                (_event(valuable="UNADJUDICATED", projections="UNADJUDICATED"),),
            ),
        ),
    )
    prediction = _prediction(projections=("anything",))

    score = score_fixture(fixture, {"unknown-labels": [prediction]})

    assert score.metrics.valuable_recall == CountRate.of(0, 0)
    assert score.metrics.projection_precision == CountRate.of(0, 0)
    assert score.metrics.projection_recall == CountRate.of(0, 0)
    assert score.metrics.projection_unsupported_rate == CountRate.of(0, 0)
    assert score.cases[0].correct is True


def test_projection_recall_keeps_adjudicated_gold_from_unmatched_events() -> None:
    fixture = Fixture((Case("missed", (_event(),)),))

    metrics = score_fixture(fixture, {"missed": []}).metrics

    assert metrics.projection_precision == CountRate.of(0, 0)
    assert metrics.projection_recall == CountRate.of(0, 1)


def test_negative_null_leakage_is_event_based_and_abstention_is_case_based() -> None:
    fixture = Fixture(
        (
            Case("negative", (_event(polarity="NULL_RESULT", valuable=False),)),
            Case("positive", (_event(event_id="event-2"),)),
            Case("empty-control", (), "TRUE_NO_EVENT_CONTROL"),
        ),
    )
    predictions = {
        "negative": [_prediction(polarity="SUPPORT")],
        "positive": [],
        "empty-control": [_prediction()],
    }

    metrics = score_fixture(fixture, predictions).metrics

    assert metrics.negative_null_leakage == CountRate.of(2, 3)
    assert metrics.empty_control_false_positive == CountRate.of(1, 1)
    assert metrics.abstention_error == CountRate.of(2, 3)


def test_unmatched_positive_event_is_leakage_in_positive_only_case() -> None:
    fixture = Fixture((Case("positive", (_event(),)),))
    hallucination = _prediction()
    hallucination["event_id"] = "hallucinated"
    hallucination["trigger_span"] = "invented"
    hallucination["arguments"] = []

    score = score_fixture(fixture, {"positive": [_prediction(), hallucination]})

    assert score.metrics.negative_null_leakage == CountRate.of(1, 1)


def test_representability_stress_output_is_descriptive_not_qualification_error() -> (
    None
):
    fixture = Fixture((Case("stress", (), "REPRESENTABILITY_STRESS"),))

    metrics = score_fixture(fixture, {"stress": [_prediction()]}).metrics

    assert metrics.representability_stress_output == CountRate.of(1, 1)
    assert metrics.negative_null_leakage == CountRate.of(0, 0)
    assert metrics.empty_control_false_positive == CountRate.of(0, 0)
    assert metrics.whole_event_precision == CountRate.of(0, 0)


def test_unmatched_positive_in_negative_case_is_zero_tolerance_leakage() -> None:
    fixture = Fixture((Case("negative", (_event(polarity="REFUTE"),)),))
    hallucination = _prediction()
    hallucination["trigger_span"] = "invented"
    hallucination["arguments"] = []

    metrics = score_fixture(
        fixture,
        {"negative": [_prediction(polarity="REFUTE"), hallucination]},
    ).metrics

    assert metrics.negative_null_leakage == CountRate.of(1, 2)


def test_uncertain_to_asserted_is_epistemic_escalation() -> None:
    fixture = Fixture(
        (Case("uncertain", (_event(epistemic_status="UNCERTAIN"),)),),
    )

    metrics = score_fixture(
        fixture,
        {"uncertain": [_prediction(epistemic_status="ASSERTED")]},
    ).metrics

    assert metrics.epistemic_escalation == CountRate.of(1, 1)


def test_provisional_to_asserted_is_epistemic_escalation() -> None:
    fixture = Fixture(
        (Case("provisional", (_event(epistemic_status="PROVISIONAL"),)),),
    )

    metrics = score_fixture(
        fixture,
        {"provisional": [_prediction(epistemic_status="ASSERTED")]},
    ).metrics

    assert metrics.epistemic_escalation == CountRate.of(1, 1)


def test_argument_scoring_distinguishes_repeated_text_mentions() -> None:
    event = _event()
    repeated = Event(
        event_id=event.event_id,
        trigger_span=event.trigger_span,
        trigger_source_start=event.trigger_source_start,
        event_type=event.event_type,
        polarity=event.polarity,
        epistemic_status=event.epistemic_status,
        arguments=(
            Argument("subject", "AGENT", "aspirin", 0),
            Argument("subject", "AGENT", "aspirin", 50),
        ),
        valuable=event.valuable,
        supported_projections=event.supported_projections,
    )
    prediction = _prediction()
    prediction["arguments"] = [
        {
            "role": "subject",
            "event_role": "AGENT",
            "exact_span": "aspirin",
            "source_start": 0,
        },
        {
            "role": "subject",
            "event_role": "AGENT",
            "exact_span": "aspirin",
            "source_start": 0,
        },
    ]

    metrics = score_fixture(
        Fixture((Case("repeated", (repeated,)),)),
        {"repeated": [prediction]},
    ).metrics

    assert metrics.argument_fidelity == CountRate.of(1, 2)
    assert metrics.argument_set_fidelity == CountRate.of(0, 1)


def test_zero_denominators_return_none_and_ineligible_gold_is_not_scored() -> None:
    fixture = Fixture((Case("excluded", (_event(eligibility=False),)),))

    score = score_fixture(fixture, {"excluded": []})

    assert score.metrics.whole_event_precision == CountRate.of(0, 0)
    assert score.metrics.whole_event_recall == CountRate.of(0, 0)
    assert score.metrics.trigger_fidelity == CountRate.of(0, 0)
    assert score.metrics.argument_fidelity == CountRate.of(0, 0)
    assert score.cases[0].correct is True


def test_payload_validation_fails_closed_for_duplicates_and_contradictions() -> None:
    fixture = Fixture((Case("positive", (_event(),)),))

    with pytest.raises(ValueError, match="duplicate prediction case id"):
        score_fixture(
            fixture,
            [
                {"case_id": "positive", "events": []},
                {"case_id": "positive", "events": []},
            ],
        )

    with pytest.raises(ValueError, match="cannot abstain and emit events"):
        score_fixture(
            fixture,
            {
                "positive": {
                    "events": [_prediction()],
                    "abstained": True,
                },
            },
        )
