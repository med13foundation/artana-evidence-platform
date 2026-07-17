"""Replay item-binding rejections against raw provider inventory attempts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from artana_evidence_api.document_extraction_prompting import (
    build_claim_inventory_output_schema,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryBindingRejection,
    bind_claim_inventory_items,
    merge_claim_inventory_binding_rejections,
)
from pydantic import ValidationError

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.full_text_chunking import (
        RelationExtractionTextChunk,
    )

_MAX_INVENTORY_CLAIMS_PER_CHUNK = 64


def validate_binding_rejection_events(
    *,
    attempts: Sequence[Mapping[str, object]],
    reported_events: Sequence[Mapping[str, object]],
    chunks: Sequence[RelationExtractionTextChunk],
    source_sha256: str,
) -> tuple[
    dict[int, tuple[ClaimInventoryBindingRejection, ...]],
    tuple[Mapping[str, object], ...],
]:
    """Replay every inventory rejection and bind it to one provider attempt."""

    attempts_by_invocation = {
        _text(attempt.get("invocation_id"), "attempt invocation_id"): attempt
        for attempt in attempts
        if attempt.get("validation_outcome") != "intentionally_skipped"
    }
    events_by_invocation: dict[str, list[Mapping[str, object]]] = {}
    seen_event_ids: set[str] = set()
    completeness_events: list[Mapping[str, object]] = []
    for event in reported_events:
        event_id = _text(event.get("event_id"), "binding rejection event_id")
        if event_id in seen_event_ids:
            raise ValueError("TG-04 binding rejection event is duplicated")
        seen_event_ids.add(event_id)
        phase = _text(event.get("phase"), "binding rejection phase")
        lineage = _object(event.get("attempt_lineage"), "attempt lineage")
        invocation_id = _text(lineage.get("invocation_id"), "attempt invocation_id")
        if invocation_id not in attempts_by_invocation:
            raise ValueError("TG-04 binding rejection has no provider attempt")
        if phase == "COMPLETENESS_REVIEW":
            completeness_events.append(event)
        elif phase != "CLAIM_INVENTORY":
            raise ValueError("TG-04 binding rejection has an invalid phase")
        events_by_invocation.setdefault(invocation_id, []).append(event)

    chunks_by_input = {chunk.sha256: chunk for chunk in chunks}
    aggregate: dict[int, tuple[ClaimInventoryBindingRejection, ...]] = {}
    for invocation_id, attempt in attempts_by_invocation.items():
        if attempt.get("pass_role") != "claim_inventory":
            continue
        input_sha256 = _text(attempt.get("input_sha256"), "inventory input_sha256")
        chunk = chunks_by_input.get(input_sha256)
        if chunk is None:
            raise ValueError("TG-04 inventory attempt targets an unknown source chunk")
        expected_rejections = _replay_inventory_attempt_binding(
            attempt=attempt,
            chunk=chunk,
            source_sha256=source_sha256,
        )
        actual_events = tuple(events_by_invocation.pop(invocation_id, ()))
        require_exact_rejection_events(
            attempt=attempt,
            phase="CLAIM_INVENTORY",
            expected_rejections=expected_rejections,
            reported_events=actual_events,
        )
        aggregate[chunk.index] = merge_claim_inventory_binding_rejections(
            aggregate.get(chunk.index, ()),
            expected_rejections,
        )

    remaining_inventory_events = tuple(
        event
        for events in events_by_invocation.values()
        for event in events
        if event.get("phase") == "CLAIM_INVENTORY"
    )
    if remaining_inventory_events:
        raise ValueError("TG-04 binding rejection targets a non-inventory attempt")
    return aggregate, tuple(completeness_events)


def require_exact_rejection_events(
    *,
    attempt: Mapping[str, object],
    phase: str,
    expected_rejections: Sequence[ClaimInventoryBindingRejection],
    reported_events: Sequence[Mapping[str, object]],
) -> None:
    """Require an exact provider-bound event for every replayed rejection."""

    expected = {
        rejection.rejection_id: expected_rejection_event(
            attempt=attempt,
            phase=phase,
            rejection=rejection,
        )
        for rejection in expected_rejections
    }
    actual: dict[str, Mapping[str, object]] = {}
    for event in reported_events:
        rejection = _object(event.get("rejection"), "binding rejection")
        rejection_id = _text(rejection.get("rejection_id"), "rejection_id")
        if rejection_id in actual:
            raise ValueError("TG-04 attempt repeats a binding rejection")
        actual[rejection_id] = event
    if set(actual) != set(expected):
        raise ValueError("TG-04 binding rejection set differs from replay")
    for rejection_id, expected_event in expected.items():
        if dict(actual[rejection_id]) != expected_event:
            raise ValueError("TG-04 binding rejection evidence differs from replay")


def expected_rejection_event(
    *,
    attempt: Mapping[str, object],
    phase: str,
    rejection: ClaimInventoryBindingRejection,
) -> dict[str, object]:
    """Build the canonical immutable event for one provider rejection."""

    invocation_id = _text(attempt.get("invocation_id"), "attempt invocation_id")
    event_id = hashlib.sha256(
        f"{phase}:{invocation_id}:{rejection.rejection_id}".encode(),
    ).hexdigest()
    return {
        "event_id": event_id,
        "phase": phase,
        "rejection": rejection.as_json(),
        "attempt_lineage": {
            "invocation_id": invocation_id,
            "provider_response_id": attempt.get("provider_response_id"),
            "provider_output_sha256": attempt.get("provider_output_sha256"),
            "payload_sha256": attempt.get("payload_sha256"),
            "source_sha256": attempt.get("source_sha256"),
            "input_sha256": attempt.get("input_sha256"),
        },
    }


def _replay_inventory_attempt_binding(
    *,
    attempt: Mapping[str, object],
    chunk: RelationExtractionTextChunk,
    source_sha256: str,
) -> tuple[ClaimInventoryBindingRejection, ...]:
    outcome = attempt.get("validation_outcome")
    payload = _object(attempt.get("raw_model_payload"), "raw model payload")
    schema = build_claim_inventory_output_schema(_MAX_INVENTORY_CLAIMS_PER_CHUNK)
    try:
        parsed = schema.model_validate(payload)
    except ValidationError as exc:
        if outcome != "schema_invalid":
            raise ValueError(
                "TG-04 inventory schema outcome differs from replay"
            ) from exc
        return ()
    result = bind_claim_inventory_items(
        tuple(parsed.claims),
        source_text=chunk.text,
        source_sha256=source_sha256,
        chunk_index=chunk.index,
        source_start_offset=chunk.start_char,
    )
    derived_outcome = (
        "semantic_invalid" if not result.accepted and result.rejected else "accepted"
    )
    if outcome != derived_outcome:
        raise ValueError("TG-04 inventory binding outcome differs from replay")
    return result.rejected


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return cast("Mapping[str, object]", value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be nonempty text")
    return value


__all__ = [
    "expected_rejection_event",
    "require_exact_rejection_events",
    "validate_binding_rejection_events",
]
