"""Deterministic scoring for TG-04 n-ary claim events."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from scripts.validation.claim_events.matching import maximum_weight_pairs

JsonObject = dict[str, object]
_UNADJUDICATED = "UNADJUDICATED"
_NEGATIVE_OR_NULL = frozenset({"NEGATIVE", "REFUTE", "NULL", "NULL_RESULT"})
_EPISTEMICALLY_QUALIFIED = frozenset({"HYPOTHESIS", "PROVISIONAL", "UNCERTAIN"})
_EPISTEMICALLY_ASSERTED = frozenset({"ASSERTED", "OBSERVED"})
_GENERIC_ROLES = frozenset(
    {"", "ARGUMENT", "ENTITY", "GENERIC", "OTHER", "PARTICIPANT"}
)


class ArgumentContract(Protocol):
    role: str
    event_role: str
    exact_span: str
    source_start: int


class EventContract(Protocol):
    event_id: str
    trigger_span: str
    trigger_source_start: int
    event_type: str
    polarity: str
    epistemic_status: str
    arguments: Sequence[ArgumentContract]
    valuable: object
    supported_projections: object
    eligibility: object


class CaseContract(Protocol):
    case_id: str
    events: Sequence[EventContract]


class BenchmarkFixtureContract(Protocol):
    cases: Sequence[CaseContract]


class StatusContract(Protocol):
    status: object


class ProjectionAnnotationContract(StatusContract, Protocol):
    supported: Sequence[object]


class ProjectionContract(Protocol):
    subject_argument_id: str
    relation_type: str
    object_argument_id: str


@dataclass(frozen=True, slots=True)
class CountRate:
    """A transparent count, denominator, and derived optional rate."""

    count: int
    denominator: int
    rate: float | None

    @classmethod
    def of(cls, count: int, denominator: int) -> CountRate:
        if count < 0 or denominator < 0 or count > denominator:
            raise ValueError(
                "count and denominator must satisfy 0 <= count <= denominator"
            )
        return cls(
            count=count,
            denominator=denominator,
            rate=None if denominator == 0 else count / denominator,
        )


@dataclass(frozen=True, slots=True)
class EventMetrics:
    whole_event_precision: CountRate
    whole_event_recall: CountRate
    trigger_precision: CountRate
    trigger_recall: CountRate
    valuable_recall: CountRate
    trigger_fidelity: CountRate
    event_type_fidelity: CountRate
    event_type_precision_by_category: dict[str, CountRate]
    event_type_recall_by_category: dict[str, CountRate]
    argument_fidelity: CountRate
    argument_precision: CountRate
    argument_recall: CountRate
    argument_set_fidelity: CountRate
    polarity_fidelity: CountRate
    epistemic_fidelity: CountRate
    projection_precision: CountRate
    projection_recall: CountRate
    projection_unsupported_rate: CountRate
    role_loss_generic_rate: CountRate
    negative_null_leakage: CountRate
    epistemic_escalation: CountRate
    empty_control_false_positive: CountRate
    representability_stress_output: CountRate
    abstention_error: CountRate


@dataclass(frozen=True, slots=True)
class CaseScore:
    case_id: str
    metrics: EventMetrics
    correct: bool
    raw_prediction: object
    canonical_prediction: str
    qualification_eligible: bool


@dataclass(frozen=True, slots=True)
class FixtureScore:
    metrics: EventMetrics
    cases: tuple[CaseScore, ...]


@dataclass(frozen=True, slots=True)
class _Counts:
    whole_matches: int = 0
    expected_events: int = 0
    predicted_events: int = 0
    valuable_matches: int = 0
    valuable_events: int = 0
    trigger_matches: int = 0
    predicted_triggers: int = 0
    event_type_matches: int = 0
    matched_event_types: tuple[str, ...] = ()
    expected_event_types: tuple[str, ...] = ()
    predicted_event_types: tuple[str, ...] = ()
    argument_matches: int = 0
    expected_arguments: int = 0
    predicted_arguments: int = 0
    argument_set_matches: int = 0
    polarity_matches: int = 0
    epistemic_matches: int = 0
    projection_matches: int = 0
    expected_projections: int = 0
    adjudicated_predicted_projections: int = 0
    unsupported_projections: int = 0
    generic_role_losses: int = 0
    comparable_roles: int = 0
    leakage_cases: int = 0
    negative_null_cases: int = 0
    epistemic_escalations: int = 0
    epistemically_qualified_cases: int = 0
    empty_control_false_positives: int = 0
    empty_control_cases: int = 0
    representability_stress_outputs: int = 0
    representability_stress_cases: int = 0
    abstention_errors: int = 0
    cases: int = 0

    def __add__(self, other: _Counts) -> _Counts:
        return _Counts(
            **{
                field: getattr(self, field) + getattr(other, field)
                for field in self.__dataclass_fields__
            },
        )


@dataclass(frozen=True, slots=True)
class _PredictionCase:
    raw: object
    events: tuple[JsonObject, ...]
    abstained: bool


def score_fixture(
    fixture: BenchmarkFixtureContract,
    predictions: object,
) -> FixtureScore:
    """Score one prediction payload against an immutable benchmark fixture."""

    case_predictions = _prediction_cases(predictions)
    expected_ids = {case.case_id for case in fixture.cases}
    unexpected = set(case_predictions) - expected_ids
    if unexpected:
        raise ValueError(f"predictions contain unknown case ids: {sorted(unexpected)}")

    scored: list[CaseScore] = []
    totals = _Counts()
    for case in fixture.cases:
        prediction = case_predictions.get(
            case.case_id,
            _PredictionCase(raw=None, events=(), abstained=True),
        )
        case_score, counts = _score_case(case, prediction)
        scored.append(case_score)
        totals += counts
    return FixtureScore(metrics=_metrics(totals), cases=tuple(scored))


def _score_case(
    case: CaseContract,
    prediction: _PredictionCase,
) -> tuple[CaseScore, _Counts]:
    expected = tuple(event for event in case.events if _eligible(event.eligibility))
    raw_actual = prediction.events
    representability_stress = (
        getattr(case, "control_status", "") == "REPRESENTABILITY_STRESS"
    )
    actual = () if representability_stress else raw_actual
    alignment = _best_alignment(expected, actual)

    expected_keys = Counter(_whole_event_key(event) for event in expected)
    actual_keys = Counter(_whole_event_key(event) for event in actual)
    whole_matches = sum((expected_keys & actual_keys).values())
    valuable_keys = Counter(
        _whole_event_key(event)
        for event in expected
        if _valuable_status(event.valuable) is True
    )
    valuable_matches = sum((valuable_keys & actual_keys).values())

    trigger_matches = event_type_matches = polarity_matches = epistemic_matches = 0
    matched_event_types: list[str] = []
    argument_matches = argument_set_matches = projection_matches = 0
    expected_projections = sum(
        len(projections)
        for event in expected
        if (projections := _adjudicated_projections(event.supported_projections))
        is not None
    )
    predicted_projections = unsupported_projections = 0
    generic_role_losses = comparable_roles = 0
    leakage_events = len(actual) - whole_matches
    epistemic_escalations = 0
    for expected_index, actual_index in alignment:
        gold = expected[expected_index]
        predicted = actual[actual_index]
        trigger_matches += (
            _string(predicted.get("trigger_span")) == gold.trigger_span
            and _nonnegative_integer(predicted.get("trigger_source_start"))
            == gold.trigger_source_start
        )
        event_type_match = _string(predicted.get("event_type")) == gold.event_type
        event_type_matches += event_type_match
        if event_type_match:
            matched_event_types.append(gold.event_type)
        polarity_matches += _string(predicted.get("polarity")) == gold.polarity
        epistemic_matches += (
            _string(predicted.get("epistemic_status")) == gold.epistemic_status
        )
        if (
            gold.epistemic_status.upper() in _EPISTEMICALLY_QUALIFIED
            and (_string(predicted.get("epistemic_status")) or "").upper()
            in _EPISTEMICALLY_ASSERTED
        ):
            epistemic_escalations += 1
        argument_matches += _argument_match_count(gold, predicted)
        argument_set_matches += int(
            Counter(_gold_argument_key(argument) for argument in gold.arguments)
            == Counter(
                _argument_key(argument) for argument in _prediction_arguments(predicted)
            )
        )
        role_losses, role_denominator = _generic_role_loss(gold, predicted)
        generic_role_losses += role_losses
        comparable_roles += role_denominator

        supported = _adjudicated_projections(gold.supported_projections)
        if supported is not None:
            projected = _prediction_projections(predicted)
            projection_matches += len(supported & projected)
            predicted_projections += len(projected)
            unsupported_projections += len(projected - supported)

    aligned_actual = {actual_index for _, actual_index in alignment}
    has_only_qualified_gold = bool(expected) and all(
        event.epistemic_status.upper() in _EPISTEMICALLY_QUALIFIED for event in expected
    )
    unmatched_asserted = sum(
        actual_index not in aligned_actual
        and has_only_qualified_gold
        and (_string(event.get("epistemic_status")) or "").upper()
        in _EPISTEMICALLY_ASSERTED
        for actual_index, event in enumerate(actual)
    )
    epistemic_escalations += unmatched_asserted
    abstention_error = (bool(expected) and prediction.abstained) or (
        not expected and not prediction.abstained
    )
    counts = _Counts(
        whole_matches=whole_matches,
        expected_events=len(expected),
        predicted_events=len(actual),
        valuable_matches=valuable_matches,
        valuable_events=sum(
            _valuable_status(event.valuable) is True for event in expected
        ),
        trigger_matches=trigger_matches,
        predicted_triggers=sum(
            _string(event.get("trigger_span")) is not None for event in actual
        ),
        event_type_matches=event_type_matches,
        matched_event_types=tuple(matched_event_types),
        expected_event_types=tuple(event.event_type for event in expected),
        predicted_event_types=tuple(
            event_type
            for event in actual
            if (event_type := _string(event.get("event_type"))) is not None
        ),
        argument_matches=argument_matches,
        expected_arguments=sum(len(event.arguments) for event in expected),
        predicted_arguments=sum(len(_prediction_arguments(event)) for event in actual),
        argument_set_matches=argument_set_matches,
        polarity_matches=polarity_matches,
        epistemic_matches=epistemic_matches,
        projection_matches=projection_matches,
        expected_projections=expected_projections,
        adjudicated_predicted_projections=predicted_projections,
        unsupported_projections=unsupported_projections,
        generic_role_losses=generic_role_losses,
        comparable_roles=comparable_roles,
        leakage_cases=leakage_events,
        negative_null_cases=sum(
            event.polarity.upper() in _NEGATIVE_OR_NULL for event in expected
        )
        + leakage_events,
        epistemic_escalations=epistemic_escalations,
        epistemically_qualified_cases=sum(
            event.epistemic_status.upper() in _EPISTEMICALLY_QUALIFIED
            for event in expected
        )
        + unmatched_asserted,
        empty_control_false_positives=int(
            getattr(case, "control_status", "") == "TRUE_NO_EVENT_CONTROL"
            and bool(actual)
        ),
        empty_control_cases=int(
            getattr(case, "control_status", "") == "TRUE_NO_EVENT_CONTROL"
        ),
        representability_stress_outputs=int(
            representability_stress and bool(raw_actual)
        ),
        representability_stress_cases=int(representability_stress),
        abstention_errors=int(abstention_error),
        cases=1,
    )
    # Event quality is evaluated only from independently available event gold.
    # Value and graph-projection lanes retain their own nullable metrics and do
    # not convert an otherwise exact event into an incorrect event.
    correct = (
        whole_matches == len(expected) == len(actual)
        and not abstention_error
        and leakage_events == 0
    )
    return (
        CaseScore(
            case_id=case.case_id,
            metrics=_metrics(counts),
            correct=correct,
            raw_prediction=prediction.raw,
            canonical_prediction=(
                "UNADJUDICATED_REPRESENTABILITY_STRESS"
                if representability_stress
                else _canonical_case(prediction)
            ),
            qualification_eligible=not representability_stress,
        ),
        counts,
    )


def _metrics(counts: _Counts) -> EventMetrics:
    return EventMetrics(
        whole_event_precision=CountRate.of(
            counts.whole_matches, counts.predicted_events
        ),
        whole_event_recall=CountRate.of(counts.whole_matches, counts.expected_events),
        trigger_precision=CountRate.of(
            counts.trigger_matches, counts.predicted_triggers
        ),
        trigger_recall=CountRate.of(counts.trigger_matches, counts.expected_events),
        valuable_recall=CountRate.of(counts.valuable_matches, counts.valuable_events),
        trigger_fidelity=CountRate.of(counts.trigger_matches, counts.expected_events),
        event_type_fidelity=CountRate.of(
            counts.event_type_matches, counts.expected_events
        ),
        event_type_precision_by_category=_category_rates(
            matches=counts.matched_event_types,
            denominators=counts.predicted_event_types,
        ),
        event_type_recall_by_category=_category_rates(
            matches=counts.matched_event_types,
            denominators=counts.expected_event_types,
        ),
        argument_fidelity=CountRate.of(
            counts.argument_matches, counts.expected_arguments
        ),
        argument_precision=CountRate.of(
            counts.argument_matches,
            counts.predicted_arguments,
        ),
        argument_recall=CountRate.of(
            counts.argument_matches, counts.expected_arguments
        ),
        argument_set_fidelity=CountRate.of(
            counts.argument_set_matches,
            counts.expected_events,
        ),
        polarity_fidelity=CountRate.of(counts.polarity_matches, counts.expected_events),
        epistemic_fidelity=CountRate.of(
            counts.epistemic_matches, counts.expected_events
        ),
        projection_precision=CountRate.of(
            counts.projection_matches,
            counts.adjudicated_predicted_projections,
        ),
        projection_recall=CountRate.of(
            counts.projection_matches,
            counts.expected_projections,
        ),
        projection_unsupported_rate=CountRate.of(
            counts.unsupported_projections,
            counts.adjudicated_predicted_projections,
        ),
        role_loss_generic_rate=CountRate.of(
            counts.generic_role_losses,
            counts.comparable_roles,
        ),
        negative_null_leakage=CountRate.of(
            counts.leakage_cases,
            counts.negative_null_cases,
        ),
        epistemic_escalation=CountRate.of(
            counts.epistemic_escalations,
            counts.epistemically_qualified_cases,
        ),
        empty_control_false_positive=CountRate.of(
            counts.empty_control_false_positives,
            counts.empty_control_cases,
        ),
        representability_stress_output=CountRate.of(
            counts.representability_stress_outputs,
            counts.representability_stress_cases,
        ),
        abstention_error=CountRate.of(counts.abstention_errors, counts.cases),
    )


def _category_rates(
    *,
    matches: Sequence[str],
    denominators: Sequence[str],
) -> dict[str, CountRate]:
    match_counts = Counter(matches)
    denominator_counts = Counter(denominators)
    return {
        category: CountRate.of(match_counts[category], denominator)
        for category, denominator in sorted(denominator_counts.items())
    }


def _best_alignment(
    expected: Sequence[EventContract],
    actual: Sequence[Mapping[str, object]],
) -> tuple[tuple[int, int], ...]:
    scores = tuple(
        tuple(_alignment_score(gold, predicted) for predicted in actual)
        for gold in expected
    )

    return maximum_weight_pairs(scores)


def _alignment_score(gold: EventContract, predicted: Mapping[str, object]) -> int:
    predicted_id = _string(predicted.get("event_id"))
    id_match = predicted_id is not None and predicted_id == gold.event_id
    trigger_match = (
        _string(predicted.get("trigger_span")) == gold.trigger_span
        and _nonnegative_integer(predicted.get("trigger_source_start"))
        == gold.trigger_source_start
    )
    gold_spans = {argument.exact_span for argument in gold.arguments}
    predicted_spans = {
        _string(argument.get("exact_span"))
        for argument in _prediction_arguments(predicted)
    }
    span_overlap = len(gold_spans & predicted_spans)
    if not (id_match or trigger_match or span_overlap):
        return 0
    return (
        20 * int(id_match)
        + 8 * int(trigger_match)
        + 4 * span_overlap
        + 2 * int(_string(predicted.get("event_type")) == gold.event_type)
        + int(_string(predicted.get("polarity")) == gold.polarity)
        + int(_string(predicted.get("epistemic_status")) == gold.epistemic_status)
    )


def _whole_event_key(event: EventContract | Mapping[str, object]) -> str:
    if isinstance(event, Mapping):
        arguments = _prediction_arguments(event)
        payload = {
            "trigger_span": _string(event.get("trigger_span")),
            "trigger_source_start": _nonnegative_integer(
                event.get("trigger_source_start")
            ),
            "event_type": _string(event.get("event_type")),
            "polarity": _string(event.get("polarity")),
            "epistemic_status": _string(event.get("epistemic_status")),
            "arguments": sorted(_argument_key(argument) for argument in arguments),
        }
    else:
        payload = {
            "trigger_span": event.trigger_span,
            "trigger_source_start": event.trigger_source_start,
            "event_type": event.event_type,
            "polarity": event.polarity,
            "epistemic_status": event.epistemic_status,
            "arguments": sorted(
                _gold_argument_key(argument) for argument in event.arguments
            ),
        }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _argument_match_count(gold: EventContract, predicted: Mapping[str, object]) -> int:
    expected = Counter(_gold_argument_key(argument) for argument in gold.arguments)
    actual = Counter(
        _argument_key(argument) for argument in _prediction_arguments(predicted)
    )
    return sum((expected & actual).values())


def _generic_role_loss(
    gold: EventContract,
    predicted: Mapping[str, object],
) -> tuple[int, int]:
    by_span: dict[tuple[str, int], list[JsonObject]] = {}
    for argument in _prediction_arguments(predicted):
        span = _string(argument.get("exact_span"))
        if span is not None:
            by_span.setdefault(
                (span, _nonnegative_integer(argument.get("source_start"))),
                [],
            ).append(argument)
    losses = denominator = 0
    for expected in gold.arguments:
        if expected.event_role.upper() in _GENERIC_ROLES:
            continue
        candidates = by_span.get((expected.exact_span, expected.source_start), [])
        if not candidates:
            continue
        denominator += 1
        predicted_role = (_string(candidates[0].get("event_role")) or "").upper()
        losses += predicted_role in _GENERIC_ROLES
    return losses, denominator


def _adjudicated_projections(value: object) -> frozenset[str] | None:
    if isinstance(value, Mapping):
        status = value.get("status")
        if isinstance(status, str):
            if status.upper() == _UNADJUDICATED:
                return None
            value = value.get("supported", ())
    elif hasattr(value, "status") and hasattr(value, "supported"):
        annotation = cast("ProjectionAnnotationContract", value)
        status = annotation.status
        if isinstance(status, str) and status.upper() == _UNADJUDICATED:
            return None
        value = annotation.supported
    if value is None or (isinstance(value, str) and value.upper() == _UNADJUDICATED):
        return None
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise TypeError("supported_projections must be a sequence or UNADJUDICATED")
    return frozenset(_projection_key(item) for item in value)


def _prediction_projections(event: Mapping[str, object]) -> frozenset[str]:
    value = event.get("supported_projections", event.get("projections", ()))
    if value is None:
        return frozenset()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise TypeError("predicted projections must be a sequence")
    return frozenset(_projection_key(item) for item in value)


def _prediction_cases(payload: object) -> dict[str, _PredictionCase]:
    if isinstance(payload, Mapping) and "cases" in payload:
        records = _mapping_sequence(payload.get("cases"), "prediction cases")
    elif isinstance(payload, Sequence) and not isinstance(payload, str | bytes):
        records = tuple(_object(item, "prediction case") for item in payload)
    elif isinstance(payload, Mapping):
        records = tuple(
            {"case_id": case_id, **_case_value(value)}
            for case_id, value in payload.items()
        )
    else:
        raise TypeError("predictions must be a mapping or sequence of case payloads")

    result: dict[str, _PredictionCase] = {}
    for record in records:
        case_id = _required_string(record.get("case_id"), "case_id")
        if case_id in result:
            raise ValueError(f"duplicate prediction case id: {case_id}")
        events = _mapping_sequence(
            record.get("events", record.get("predictions", ())),
            f"events for {case_id}",
        )
        abstained_value = record.get("abstained")
        if abstained_value is not None and not isinstance(abstained_value, bool):
            raise TypeError("abstained must be a boolean when present")
        abstained = not events if abstained_value is None else abstained_value
        if abstained and events:
            raise ValueError(f"case {case_id} cannot abstain and emit events")
        result[case_id] = _PredictionCase(
            raw=record, events=events, abstained=abstained
        )
    return result


def _case_value(value: object) -> JsonObject:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return {"events": list(value)}
    raise TypeError("case prediction must be an object or event sequence")


def _canonical_case(prediction: _PredictionCase) -> str:
    events = []
    for event in prediction.events:
        events.append(
            {
                "whole_event": _whole_event_key(event),
                "projections": sorted(_prediction_projections(event)),
            },
        )
    return json.dumps(
        {
            "abstained": prediction.abstained,
            "events": sorted(events, key=_canonical_value),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _eligible(value: object) -> bool:
    if isinstance(value, Mapping):
        value = value.get("status")
    elif hasattr(value, "status"):
        value = cast("StatusContract", value).status
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.upper() in {"ELIGIBLE", "INCLUDE", "REQUIRED", "SCORABLE"}
    return False


def _valuable_status(value: object) -> bool | None:
    if isinstance(value, Mapping):
        value = value.get("status")
    elif hasattr(value, "status"):
        value = cast("StatusContract", value).status
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.upper() == "VALUABLE":
            return True
        if value.upper() == "NOT_VALUABLE":
            return False
    return None


def _projection_key(value: object) -> str:
    if all(
        hasattr(value, field)
        for field in ("subject_argument_id", "relation_type", "object_argument_id")
    ):
        projection = cast("ProjectionContract", value)
        value = {
            "subject_argument_id": projection.subject_argument_id,
            "relation_type": projection.relation_type,
            "object_argument_id": projection.object_argument_id,
        }
    return _canonical_value(value)


def _prediction_arguments(event: Mapping[str, object]) -> tuple[JsonObject, ...]:
    return _mapping_sequence(event.get("arguments", ()), "event arguments")


def _gold_argument_key(argument: ArgumentContract) -> tuple[str, str, str, int]:
    return (
        argument.role,
        argument.event_role,
        argument.exact_span,
        argument.source_start,
    )


def _argument_key(argument: Mapping[str, object]) -> tuple[str, str, str, int]:
    return (
        _string(argument.get("role")) or "",
        _string(argument.get("event_role")) or "",
        _string(argument.get("exact_span")) or "",
        _nonnegative_integer(argument.get("source_start")),
    )


def _canonical_value(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _mapping_sequence(value: object, label: str) -> tuple[JsonObject, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise TypeError(f"{label} must be a sequence")
    return tuple(_object(item, label) for item in value)


def _object(value: object, label: str) -> JsonObject:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} entries must be objects")
    return cast("JsonObject", dict(value))


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{label} must be a non-empty string")
    return value


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _nonnegative_integer(value: object) -> int:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else -1
    )


__all__ = [
    "BenchmarkFixtureContract",
    "CaseScore",
    "CountRate",
    "EventMetrics",
    "FixtureScore",
    "score_fixture",
]
