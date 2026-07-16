"""Deterministic scoring for the agent-authored TG-03 claim inventory."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from scripts.validation.claim_frames.fixture import BenchmarkCase, ExpectedFrame

JsonObject = dict[str, object]
_INVENTORY_PASS_ROLES = frozenset({"claim_inventory", "claim_inventory_recovery"})


def evaluate_inventory(
    case: BenchmarkCase,
    raw_agent_output: object,
) -> JsonObject:
    """Compare accepted inventory items with quality-eligible expected claims."""

    inventory_items = _accepted_inventory_items(raw_agent_output)
    remaining = list(enumerate(inventory_items))
    unresolved_frame_ids = set(case.unresolved_frame_ids)
    matched_indices: list[int | None] = []
    full_matches: list[bool] = []
    for expected in case.frames:
        match_index = _find_inventory_boundary(
            expected,
            [item for _, item in remaining],
            direction_required=expected.frame_id not in unresolved_frame_ids,
        )
        if match_index is None:
            matched_indices.append(None)
            full_matches.append(False)
            continue
        original_index, item = remaining.pop(match_index)
        matched_indices.append(original_index)
        full_matches.append(_inventory_categories_match(expected, item))

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
    quality_inventory_count = sum(
        index not in unresolved_match_indices for index in range(len(inventory_items))
    )
    return {
        "expected_inventory_claim_count": len(quality_indices),
        "inventory_claim_count": quality_inventory_count,
        "inventory_boundary_match_count": sum(
            matched_indices[index] is not None for index in quality_indices
        ),
        "inventory_full_match_count": sum(
            full_matches[index] for index in quality_indices
        ),
        "unmatched_inventory_claim_count": len(remaining),
    }


def _accepted_inventory_items(raw_agent_output: object) -> tuple[JsonObject, ...]:
    output = _object(raw_agent_output, "raw agent output")
    attempts = _object_sequence(output.get("attempts"), "model attempts")
    items: list[JsonObject] = []
    seen: set[str] = set()
    for attempt in attempts:
        if (
            attempt.get("validation_outcome") != "accepted"
            or attempt.get("pass_role") not in _INVENTORY_PASS_ROLES
        ):
            continue
        payload = _object(attempt.get("raw_model_payload"), "inventory payload")
        claims = _object_sequence(payload.get("claims"), "inventory claims")
        for claim in claims:
            identity = json.dumps(
                claim,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            if identity in seen:
                continue
            seen.add(identity)
            items.append(claim)
    return tuple(items)


def _find_inventory_boundary(
    expected: ExpectedFrame,
    items: Sequence[Mapping[str, object]],
    *,
    direction_required: bool,
) -> int | None:
    for index, item in enumerate(items):
        subject, object_ = _ordered_endpoints(item)
        endpoint_a = _string(item.get("endpoint_a_span"))
        endpoint_b = _string(item.get("endpoint_b_span"))
        endpoint_match = (
            (subject, object_) == (expected.subject, expected.object)
            if direction_required
            else {endpoint_a, endpoint_b} == {expected.subject, expected.object}
        )
        if (
            _string(item.get("exact_span")) == expected.source_span
            and endpoint_match
        ):
            return index
    return None


def _inventory_categories_match(
    expected: ExpectedFrame,
    item: Mapping[str, object],
) -> bool:
    return (
        _string(item.get("polarity")) == expected.polarity
        and _string(item.get("epistemic_status")) == expected.epistemic_status
    )


def _ordered_endpoints(item: Mapping[str, object]) -> tuple[str | None, str | None]:
    endpoint_a = _string(item.get("endpoint_a_span"))
    endpoint_b = _string(item.get("endpoint_b_span"))
    role_order = _string(item.get("endpoint_role_order"))
    if role_order == "A_SUBJECT_B_OBJECT":
        return endpoint_a, endpoint_b
    if role_order == "B_SUBJECT_A_OBJECT":
        return endpoint_b, endpoint_a
    return None, None


def _object(value: object, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return cast("JsonObject", value)


def _object_sequence(value: object, label: str) -> tuple[JsonObject, ...]:
    if not isinstance(value, list | tuple):
        raise TypeError(f"{label} must be a list")
    return tuple(_object(item, label) for item in value)


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["evaluate_inventory"]
