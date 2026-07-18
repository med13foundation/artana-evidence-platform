"""Non-lossy deterministic comparison against minimum expert event structure."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.validation.claim_events.contracts import NaryClaimEvent


def expert_core_event_match_count(
    expert_events: tuple[NaryClaimEvent, ...],
    predicted_events: Sequence[Mapping[str, object]],
) -> int:
    """Count expert events preserved as a core subset of trusted predictions."""

    return sum(
        any(_preserves_expert_core(expert, predicted) for predicted in predicted_events)
        for expert in expert_events
    )


def _preserves_expert_core(
    expert: NaryClaimEvent,
    predicted: Mapping[str, object],
) -> bool:
    expected_arguments = {
        (
            argument.event_role.value,
            argument.participant_role.value,
            argument.exact_span,
            argument.source_start,
        )
        for argument in expert.arguments
    }
    actual_arguments = {
        (
            argument.get("event_role"),
            argument.get("role"),
            argument.get("exact_span"),
            argument.get("source_start"),
        )
        for argument in _arguments(predicted)
    }
    return (
        predicted.get("trigger_span") == expert.trigger_span
        and predicted.get("trigger_source_start") == expert.trigger_source_start
        and predicted.get("event_type") == expert.event_type.value
        and predicted.get("polarity") == expert.polarity.value
        and predicted.get("epistemic_status") == expert.epistemic_status.value
        and expected_arguments <= actual_arguments
    )


def _arguments(event: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = event.get("arguments")
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


__all__ = ["expert_core_event_match_count"]
