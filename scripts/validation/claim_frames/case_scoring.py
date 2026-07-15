"""Deterministic matching and scoring for TG-03 benchmark cases."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Final, cast

from scripts.validation.claim_frames.fixture import (
    QUALIFIER_FIELDS,
    BenchmarkCase,
    ExpectedFrame,
    ExpectedSourceMeasurement,
)

JsonObject = dict[str, object]
_NEGATIVE_POLARITIES: Final = frozenset({"REFUTE", "NULL_RESULT"})
_NEGATIVE_STATUSES: Final = frozenset({"NULL_RESULT"})


def evaluate_case(
    case: BenchmarkCase,
    frames: Sequence[Mapping[str, object]],
) -> JsonObject:
    """Evaluate one case using independent categorical and source-bound gold."""

    remaining = list(enumerate(frames))
    matched_indices: list[int | None] = []
    matches: list[JsonObject] = []
    for expected in case.frames:
        index = find_frame_index(
            expected,
            [frame for _, frame in remaining],
        )
        if index is None:
            matched_indices.append(None)
            actual = None
        else:
            original_index, actual = remaining.pop(index)
            matched_indices.append(original_index)
        matches.append(evaluate_frame(expected, actual))

    unresolved_frame_ids = set(case.unresolved_frame_ids)
    quality_indices = [
        index
        for index, expected in enumerate(case.frames)
        if expected.frame_id not in unresolved_frame_ids
    ]
    unresolved_match_indices = {
        output_index
        for expected_index, output_index in enumerate(matched_indices)
        if output_index is not None
        and case.frames[expected_index].frame_id in unresolved_frame_ids
    }
    quality_output_frames = [
        frame
        for output_index, frame in enumerate(frames)
        if output_index not in unresolved_match_indices
    ]

    positive_on_negative = sum(
        1
        for expected_index in quality_indices
        for expected, match in ((case.frames[expected_index], matches[expected_index]),)
        if _is_positive_on_negative(expected, match)
    )
    if quality_indices and all(
        _is_negative_expected(case.frames[index]) for index in quality_indices
    ):
        positive_on_negative = sum(
            _string(frame.get("polarity")) == "SUPPORT" for frame in frames
        )
    measurement_omissions = sum(
        _measurement_omissions(frame, case.source_text)
        for frame in quality_output_frames
    )
    unsafe_assertive_upgrades = sum(
        _is_unsafe_assertive_upgrade(expected, match)
        for expected_index in quality_indices
        for expected, match in ((case.frames[expected_index], matches[expected_index]),)
    )
    output_measurement_count = sum(
        _measurement_count(frame) for frame in quality_output_frames
    )
    return {
        "case_id": case.case_id,
        "title": case.title,
        "category": case.category,
        "adjudication_status": case.adjudication_status,
        "unresolved_frame_ids": list(case.unresolved_frame_ids),
        "expected_frame_count": len(quality_indices),
        "unresolved_frame_count": len(case.frames) - len(quality_indices),
        "unresolved_output_frame_count": len(unresolved_match_indices),
        "promotion_eligible_expected_count": sum(
            case.frames[index].promotion_eligible is True for index in quality_indices
        ),
        "output_frame_count": len(quality_output_frames),
        "endpoint_source_match_count": sum(
            matches[index]["matched"] is True for index in quality_indices
        ),
        "full_frame_correct_count": sum(
            matches[index]["full_frame_correct"] is True for index in quality_indices
        ),
        "polarity_correct_count": sum(
            matches[index]["polarity_correct"] is True for index in quality_indices
        ),
        "epistemic_status_correct_count": sum(
            matches[index]["epistemic_status_correct"] is True
            for index in quality_indices
        ),
        "qualifier_presence_complete_count": sum(
            matches[index]["qualifier_presence_complete"] is True
            and case.frames[index].promotion_eligible is True
            for index in quality_indices
        ),
        "qualifier_concordant_count": sum(
            matches[index]["qualifier_concordant"] is True for index in quality_indices
        ),
        "unmatched_output_count": len(remaining),
        "unsupported_positive_output_count": sum(
            _string(frame.get("polarity")) == "SUPPORT" for _, frame in remaining
        ),
        "unsafe_assertive_upgrade_count": unsafe_assertive_upgrades,
        "positive_on_negative_or_null_count": positive_on_negative,
        "expected_source_measurement_count": sum(
            len(case.frames[index].source_measurements) for index in quality_indices
        ),
        "output_source_measurement_count": output_measurement_count,
        "matched_source_measurement_count": sum(
            _integer(matches[index].get("matched_source_measurement_count"))
            for index in quality_indices
        ),
        "source_measurement_without_span_count": measurement_omissions,
        "matches": matches,
        "fallback_output_count": 0,
    }


def aggregate_case_metrics(
    case_results: Sequence[Mapping[str, object]],
) -> JsonObject:
    """Aggregate scored cases into deterministic run or comparison metrics."""

    quality_cases = [
        case for case in case_results if _integer(case.get("expected_frame_count")) > 0
    ]
    quality_fields = (
        "expected_frame_count",
        "expected_inventory_claim_count",
        "inventory_claim_count",
        "inventory_boundary_match_count",
        "inventory_full_match_count",
        "unmatched_inventory_claim_count",
        "promotion_eligible_expected_count",
        "output_frame_count",
        "endpoint_source_match_count",
        "full_frame_correct_count",
        "polarity_correct_count",
        "epistemic_status_correct_count",
        "qualifier_presence_complete_count",
        "qualifier_concordant_count",
        "unmatched_output_count",
        "unsupported_positive_output_count",
        "unsafe_assertive_upgrade_count",
        "positive_on_negative_or_null_count",
        "expected_source_measurement_count",
        "output_source_measurement_count",
        "matched_source_measurement_count",
        "source_measurement_without_span_count",
    )
    totals = {
        field: sum(_integer(case.get(field)) for case in quality_cases)
        for field in quality_fields
    }
    all_case_fields = (
        "agent_authored_numeric_value_count",
        "fallback_output_count",
    )
    totals.update(
        {
            field: sum(_integer(case.get(field)) for case in case_results)
            for field in all_case_fields
        },
    )
    expected = totals["expected_frame_count"]
    eligible = totals["promotion_eligible_expected_count"]
    output_frames = totals["output_frame_count"]
    expected_inventory = totals["expected_inventory_claim_count"]
    output_inventory = totals["inventory_claim_count"]
    output_measurements = totals["output_source_measurement_count"]
    expected_measurements = totals["expected_source_measurement_count"]
    agent_completed = sum(
        case.get("agent_invocation_completed") is True for case in case_results
    )
    strict_completed = sum(
        case.get("strict_usable_extraction_completed") is True for case in case_results
    )
    pipeline_completed = sum(
        case.get("composed_pipeline_completed") is True for case in case_results
    )
    return {
        **totals,
        "case_count": len(case_results),
        "quality_case_count": len(quality_cases),
        "quality_frame_count": expected,
        "unresolved_case_count": sum(
            _integer(case.get("unresolved_frame_count")) > 0 for case in case_results
        ),
        "unresolved_frame_count": sum(
            _integer(case.get("unresolved_frame_count")) for case in case_results
        ),
        "unresolved_output_frame_count": sum(
            _integer(case.get("unresolved_output_frame_count")) for case in case_results
        ),
        "explicit_polarity_concordance_rate": _rate(
            totals["polarity_correct_count"],
            expected,
        ),
        "inventory_boundary_precision": _rate(
            totals["inventory_boundary_match_count"],
            output_inventory,
        ),
        "inventory_boundary_recall": _rate(
            totals["inventory_boundary_match_count"],
            expected_inventory,
        ),
        "inventory_full_precision": _rate(
            totals["inventory_full_match_count"],
            output_inventory,
        ),
        "inventory_full_recall": _rate(
            totals["inventory_full_match_count"],
            expected_inventory,
        ),
        "required_qualifier_completeness_rate": _rate(
            totals["qualifier_presence_complete_count"],
            eligible,
        ),
        "qualifier_concordance_rate": _rate(
            totals["qualifier_concordant_count"],
            expected,
        ),
        "endpoint_source_match_precision": _rate(
            totals["endpoint_source_match_count"],
            output_frames,
        ),
        "endpoint_source_match_recall": _rate(
            totals["endpoint_source_match_count"],
            expected,
        ),
        "full_frame_precision": _rate(
            totals["full_frame_correct_count"],
            output_frames,
        ),
        "full_frame_recall": _rate(
            totals["full_frame_correct_count"],
            expected,
        ),
        "epistemic_status_concordance_rate": _rate(
            totals["epistemic_status_correct_count"],
            expected,
        ),
        "source_measurement_precision": _rate(
            totals["matched_source_measurement_count"],
            output_measurements,
        ),
        "source_measurement_recall": _rate(
            totals["matched_source_measurement_count"],
            expected_measurements,
        ),
        "agent_invocation_completed_case_count": agent_completed,
        "agent_invocation_completion_rate": _rate(agent_completed, len(case_results)),
        "composed_pipeline_completed_case_count": pipeline_completed,
        "composed_pipeline_completion_rate": _rate(
            pipeline_completed,
            len(case_results),
        ),
        "strict_usable_extraction_completed_case_count": strict_completed,
        "strict_usable_extraction_completion_rate": _rate(
            strict_completed,
            len(case_results),
        ),
    }


def find_frame_index(
    expected: ExpectedFrame,
    frames: Sequence[Mapping[str, object]],
) -> int | None:
    """Return the first endpoint-and-source match for an expected frame."""

    for index, actual in enumerate(frames):
        evidence = _object(actual.get("source_evidence"))
        if (
            _source_surface(_string(evidence.get("exact_span")))
            == _source_surface(expected.source_span)
            and _string(evidence.get("locator")) == expected.source_locator
            and _entity_surface(_string(actual.get("subject")))
            == _entity_surface(expected.subject)
            and _string(actual.get("predicate")) == expected.predicate
            and _entity_surface(_string(actual.get("object")))
            == _entity_surface(expected.object)
        ):
            return index
    return None


def semantic_frame_fingerprint(frame: Mapping[str, object]) -> str:
    """Hash semantic frame fields while excluding free-form rationale prose."""

    payload = dict(frame)
    payload.pop("extraction_rationale", None)
    return _sha256_json(payload)


def evaluate_frame(
    expected: ExpectedFrame,
    actual: Mapping[str, object] | None,
) -> JsonObject:
    """Score one expected frame against its endpoint-and-source match."""

    if actual is None:
        return {
            "frame_id": expected.frame_id,
            "matched": False,
            "polarity_correct": False,
            "epistemic_status_correct": False,
            "qualifier_presence_complete": False,
            "qualifier_concordant": False,
            "full_frame_correct": False,
            "expected_source_measurement_count": len(expected.source_measurements),
            "output_source_measurement_count": 0,
            "matched_source_measurement_count": 0,
            "semantic_fingerprint": None,
            "actual_polarity": None,
            "actual_epistemic_status": None,
        }
    actual_qualifiers = {
        field: _object(actual.get(field)) for field in QUALIFIER_FIELDS
    }
    polarity_correct = _string(actual.get("polarity")) == expected.polarity
    status_correct = (
        _string(actual.get("epistemic_status")) == expected.epistemic_status
    )
    qualifier_concordant = _qualifiers_concordant(expected, actual_qualifiers)
    measurement_counts = _source_measurement_counts(expected, actual)
    return {
        "frame_id": expected.frame_id,
        "matched": True,
        "polarity_correct": polarity_correct,
        "epistemic_status_correct": status_correct,
        "qualifier_presence_complete": _qualifier_presence_complete(
            expected,
            actual_qualifiers,
        ),
        "qualifier_concordant": qualifier_concordant,
        "full_frame_correct": polarity_correct
        and status_correct
        and qualifier_concordant,
        **measurement_counts,
        "semantic_fingerprint": semantic_frame_fingerprint(actual),
        "actual_polarity": _string(actual.get("polarity")),
        "actual_epistemic_status": _string(actual.get("epistemic_status")),
    }


def _qualifier_presence_complete(
    expected: ExpectedFrame,
    actual: Mapping[str, Mapping[str, object]],
) -> bool:
    if expected.promotion_eligible is not True:
        return True
    for field in QUALIFIER_FIELDS:
        expected_qualifier = expected.qualifiers[field]
        actual_qualifier = actual[field]
        state = _string(actual_qualifier.get("state"))
        if state == "UNRESOLVED":
            return False
        if expected_qualifier.state == "PRESENT" and (
            state != "PRESENT"
            or not _string(actual_qualifier.get("value"))
            or not _string(actual_qualifier.get("exact_span"))
        ):
            return False
    return True


def _qualifiers_concordant(
    expected: ExpectedFrame,
    actual: Mapping[str, Mapping[str, object]],
) -> bool:
    for field in QUALIFIER_FIELDS:
        expected_qualifier = expected.qualifiers[field]
        actual_qualifier = actual[field]
        if _string(actual_qualifier.get("state")) != expected_qualifier.state:
            return False
        if expected_qualifier.state == "PRESENT" and (
            expected_qualifier.value is None
            or expected_qualifier.exact_span is None
            or _source_surface(_string(actual_qualifier.get("value")))
            != _source_surface(expected_qualifier.value)
            or _source_surface(_string(actual_qualifier.get("exact_span")))
            != _source_surface(expected_qualifier.exact_span)
        ):
            return False
    return True


def _source_measurement_counts(
    expected: ExpectedFrame,
    actual: Mapping[str, object],
) -> JsonObject:
    raw_measurements = actual.get("source_measurements", [])
    actual_measurements = (
        [_object(item) for item in raw_measurements]
        if isinstance(raw_measurements, list)
        else []
    )
    remaining = list(actual_measurements)
    matched = 0
    for gold in expected.source_measurements:
        index = next(
            (
                index
                for index, candidate in enumerate(remaining)
                if _measurement_matches(gold, candidate)
            ),
            None,
        )
        if index is not None:
            matched += 1
            remaining.pop(index)
    return {
        "expected_source_measurement_count": len(expected.source_measurements),
        "output_source_measurement_count": len(actual_measurements),
        "matched_source_measurement_count": matched,
    }


def _measurement_matches(
    expected: ExpectedSourceMeasurement,
    actual: Mapping[str, object],
) -> bool:
    return (
        _string(actual.get("value")) == expected.value
        and _string(actual.get("source_locator")) == expected.source_locator
        and _string(actual.get("literal_span")) == expected.literal_span
        and _string(actual.get("field_name")) == expected.field_name
        and _normalized_unit(_string(actual.get("unit")))
        == _normalized_unit(expected.unit)
        and _string(actual.get("extraction_method")) == expected.extraction_method
        and actual.get("origin") == "source_measurement"
    )


def _normalized_unit(value: str) -> str:
    normalized = value.strip().casefold()
    aliases = {
        "%": "percent",
        "percentage": "percent",
        "weeks": "week",
        "months": "month",
        "dimensionless ratio": "dimensionless",
        "ratio": "dimensionless",
        "unitless": "dimensionless",
    }
    return aliases.get(normalized, normalized)


def _measurement_count(frame: Mapping[str, object]) -> int:
    measurements = frame.get("source_measurements", [])
    return len(measurements) if isinstance(measurements, list) else 0


def _is_positive_on_negative(
    expected: ExpectedFrame,
    match: Mapping[str, object],
) -> bool:
    return (
        expected.polarity in _NEGATIVE_POLARITIES
        or expected.epistemic_status in _NEGATIVE_STATUSES
    ) and match.get("actual_polarity") == "SUPPORT"


def _is_negative_expected(expected: ExpectedFrame) -> bool:
    return (
        expected.polarity in _NEGATIVE_POLARITIES
        or expected.epistemic_status in _NEGATIVE_STATUSES
    )


def _is_unsafe_assertive_upgrade(
    expected: ExpectedFrame,
    match: Mapping[str, object],
) -> bool:
    return (
        expected.epistemic_status != "ASSERTED"
        and match.get("actual_epistemic_status") == "ASSERTED"
    )


def _measurement_omissions(frame: Mapping[str, object], source_text: str) -> int:
    measurements = frame.get("source_measurements", [])
    if not isinstance(measurements, list):
        return 1
    omissions = 0
    source_evidence = _object(frame.get("source_evidence"))
    frame_locator = _string(source_evidence.get("locator"))
    frame_span = _string(source_evidence.get("exact_span"))
    for measurement in measurements:
        payload = _object(measurement)
        literal_span = _string(payload.get("literal_span"))
        if (
            not literal_span
            or _string(payload.get("source_locator")) != frame_locator
            or source_text.count(literal_span) != 1
            or frame_span.count(literal_span) != 1
        ):
            omissions += 1
    return omissions


def _entity_surface(value: str) -> str:
    return " ".join(value.casefold().split())


def _source_surface(value: str) -> str:
    return " ".join(value.casefold().strip().rstrip(". ;,").split())


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()


def _rate(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


def _object(value: object) -> JsonObject:
    return cast("JsonObject", value) if isinstance(value, dict) else {}


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


__all__ = [
    "aggregate_case_metrics",
    "evaluate_case",
    "evaluate_frame",
    "find_frame_index",
    "semantic_frame_fingerprint",
]
