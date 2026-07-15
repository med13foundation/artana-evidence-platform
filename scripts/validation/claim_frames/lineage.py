"""Provider-to-candidate lineage validation for claim-frame reports."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import cast

from scripts.validation.claim_frames.evidence import (
    accepted_raw_relations,
    validate_model_attempt_records,
)
from scripts.validation.claim_frames.fixture import QUALIFIER_FIELDS

JsonObject = dict[str, object]


def validate_candidate_lineage(
    *,
    candidate_frames: Sequence[Mapping[str, object]],
    attempts: Sequence[Mapping[str, object]],
    case_id: str,
    allow_partial_failure: bool,
) -> None:
    """Require every scored candidate to match accepted provider output."""

    framing_attempts = _accepted_framing_attempts(attempts)
    provider_framing_frames = Counter(
        _sha256_json(frame)
        for frame in _provider_framing_frames(
            attempts=attempts,
            framing_attempts=framing_attempts,
        )
    )
    scored_frames = Counter(_sha256_json(frame) for frame in candidate_frames)
    if scored_frames == provider_framing_frames:
        return
    if scored_frames - provider_framing_frames:
        raise ValueError(
            f"case {case_id} contains a candidate not derived from an accepted "
            "raw agent relation",
        )
    if allow_partial_failure:
        return
    raise ValueError(
        f"case {case_id} omits an accepted provider-bound framing output from "
        "postprocessing or scoring",
    )


def omitted_accepted_framing_output_count(
    case_result: Mapping[str, object],
    *,
    expected_model_id: str,
) -> int:
    """Count accepted provider frames absent from the scored candidate multiset."""

    attempts = validate_model_attempt_records(
        case_result.get("raw_agent_output"),
        expected_model_id=expected_model_id,
    )
    provider_frames = Counter(
        _sha256_json(frame)
        for frame in _provider_framing_frames(
            attempts=attempts,
            framing_attempts=_accepted_framing_attempts(attempts),
        )
    )
    scored_frames = Counter(
        _sha256_json(frame) for frame in _frames_from_case_result(case_result)
    )
    return sum((provider_frames - scored_frames).values())


def _accepted_framing_attempts(
    attempts: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    return tuple(
        attempt
        for attempt in attempts
        if attempt.get("validation_outcome") == "accepted"
        and attempt.get("pass_role") == "claim_framing"
    )


def _provider_framing_frames(
    *,
    attempts: Sequence[Mapping[str, object]],
    framing_attempts: Sequence[Mapping[str, object]],
) -> tuple[JsonObject, ...]:
    inventory_items = _accepted_inventory_items(attempts)
    frames: list[JsonObject] = []
    for attempt in framing_attempts:
        inventory_item = _inventory_item_for_framing_attempt(
            attempt=attempt,
            inventory_items=inventory_items,
        )
        for relation in accepted_raw_relations((attempt,)):
            frame = _raw_relation_frame(relation)
            raw_arguments = (
                inventory_item.get("arguments")
                if inventory_item is not None
                else None
            )
            if raw_arguments is not None:
                frame["assertion_arguments"] = _object_list(
                    raw_arguments,
                    label="typed inventory arguments",
                )
            frames.append(frame)
    return tuple(frames)


def _accepted_inventory_items(
    attempts: Sequence[Mapping[str, object]],
) -> tuple[JsonObject, ...]:
    items_by_hash: dict[str, JsonObject] = {}
    for attempt in attempts:
        if (
            attempt.get("validation_outcome") != "accepted"
            or attempt.get("pass_role")
            not in {"claim_inventory", "claim_inventory_recovery"}
        ):
            continue
        payload = _object(attempt.get("raw_model_payload"))
        for item in _object_list(
            payload.get("claims"),
            label="accepted inventory claims",
        ):
            items_by_hash.setdefault(_sha256_json(item), item)
    return tuple(items_by_hash.values())


def _inventory_item_for_framing_attempt(
    *,
    attempt: Mapping[str, object],
    inventory_items: Sequence[Mapping[str, object]],
) -> Mapping[str, object] | None:
    semantic_unit_id = _required_nonempty_string(attempt, "semantic_unit_id")
    input_sha256 = _required_nonempty_string(attempt, "input_sha256")
    matches = tuple(
        item
        for item in inventory_items
        if _sha256_json({"inventory_id": semantic_unit_id, "item": item})
        == input_sha256
    )
    if len(matches) == 1:
        return matches[0]
    if not any("arguments" in item for item in inventory_items):
        return None
    raise ValueError(
        "accepted framing output does not bind to exactly one inventory item",
    )


def _raw_relation_frame(relation: Mapping[str, object]) -> JsonObject:
    required = (
        "subject",
        "relation_type",
        "object",
        "sentence",
        "polarity",
        "epistemic_status",
        *QUALIFIER_FIELDS,
        "source_measurements",
        "extraction_rationale",
    )
    missing = [key for key in required if key not in relation]
    if missing:
        raise ValueError(f"accepted raw relation lacks ClaimFrame fields: {missing}")
    frame: JsonObject = {
        "subject": _required_nonempty_string(relation, "subject").strip(),
        "predicate": _required_nonempty_string(relation, "relation_type"),
        "object": _required_nonempty_string(relation, "object").strip(),
        "source_evidence": {
            "exact_span": _required_nonempty_string(relation, "sentence").strip(),
            "locator": "normalized_extraction_text",
        },
        "polarity": _required_nonempty_string(relation, "polarity"),
        "epistemic_status": _required_nonempty_string(
            relation,
            "epistemic_status",
        ),
        **{field: _object(relation.get(field)) for field in QUALIFIER_FIELDS},
        "source_measurements": _object_list(
            relation.get("source_measurements"),
            label="accepted raw source_measurements",
        ),
        "extraction_rationale": _required_nonempty_string(
            relation,
            "extraction_rationale",
        ),
    }
    if "condition" in relation:
        frame["condition"] = _object(relation.get("condition"))
    return frame


def _frames_from_case_result(
    case_result: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    raw_frames = case_result.get("frames", [])
    if not isinstance(raw_frames, list):
        raise TypeError("report case frames must be a list")
    return tuple(_object(frame) for frame in raw_frames)


def _object_list(value: object, *, label: str) -> list[JsonObject]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    return [_object(item) for item in value]


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError("value must be an object")
    return cast("JsonObject", value)


def _required_nonempty_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


__all__ = [
    "omitted_accepted_framing_output_count",
    "validate_candidate_lineage",
]
