"""Unchanged dual-lane link and nested-structure rules for evaluator V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        EventArgument,
        StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.mapping import (
        ParticipantMapping,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )


@dataclass(frozen=True, slots=True)
class LinkMetrics:
    core_complete: bool
    nested_exact: bool
    roles_valid: bool
    unsupported: int
    permitted_context_links: int
    ambiguous_context_links: int


def evaluate_links(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    *,
    event_map: dict[str, str],
    participants: ParticipantMapping,
    reasons: list[str],
) -> LinkMetrics:
    actual_items = _actual_link_items(output, event_map, participants)
    actual = set(actual_items)
    duplicate_links = len(actual_items) - len(actual)
    expected_core = {
        (item.event_key, item.role, item.target_kind, item.target_key)
        for item in case.reference.arguments
    }
    allowed_context = {
        (
            argument.event_key,
            argument.role,
            "PARTICIPANT",
            f"CONTEXT:{participant.judgment_id}",
        )
        for participant in participants.context.values()
        for argument in participant.allowed_arguments
        if participant.classification != "FORBIDDEN"
    }
    missing_core = expected_core - actual
    if missing_core:
        reasons.append("required core event arguments are missing")
    unsupported_items = actual - expected_core - allowed_context
    unsupported = len(unsupported_items) + duplicate_links
    if unsupported_items:
        reasons.append("typed event arguments exceed core-plus-context policy")
    if duplicate_links:
        reasons.append("duplicate typed event arguments are unsupported")
    permitted_context_links = 0
    ambiguous_context_links = 0
    orphaned_context = 0
    for participant_id, participant in participants.context.items():
        context_target = f"CONTEXT:{participant.judgment_id}"
        matching = {item for item in actual if item[3] == context_target}
        if not matching:
            orphaned_context += 1
            reasons.append(f"context participant is unlinked: {participant_id}")
        elif participant.classification == "PERMITTED_CONTEXT":
            permitted_context_links += len(matching & allowed_context)
        elif participant.classification == "AMBIGUOUS_REVIEW_ONLY":
            ambiguous_context_links += len(matching & allowed_context)
    unsupported += orphaned_context
    actual_event_edges = {item for item in actual if item[2] == "EVENT"}
    expected_event_edges = {item for item in expected_core if item[2] == "EVENT"}
    nested_exact = actual_event_edges == expected_event_edges
    if not nested_exact:
        reasons.append("nested event structure differs from required core")
    return LinkMetrics(
        core_complete=not missing_core,
        nested_exact=nested_exact,
        roles_valid=not missing_core and unsupported == 0,
        unsupported=unsupported,
        permitted_context_links=permitted_context_links,
        ambiguous_context_links=ambiguous_context_links,
    )


def _actual_link_items(
    output: StagedGeneralizationOutput,
    event_map: dict[str, str],
    participants: ParticipantMapping,
) -> list[tuple[str, str, str, str]]:
    return [
        (
            event_map.get(link.event_id, f"UNKNOWN:{link.event_id}"),
            argument.role,
            argument.target_kind,
            _target_key(argument, event_map, participants),
        )
        for link in output.links
        for argument in link.arguments
    ]


def _target_key(
    argument: EventArgument,
    event_map: dict[str, str],
    participants: ParticipantMapping,
) -> str:
    if argument.target_kind == "EVENT":
        return event_map.get(argument.target_id, f"UNKNOWN:{argument.target_id}")
    if argument.target_id in participants.core:
        return participants.core[argument.target_id]
    if argument.target_id in participants.context:
        judgment = participants.context[argument.target_id]
        return f"CONTEXT:{judgment.judgment_id}"
    return f"UNKNOWN:{argument.target_id}"


__all__ = ["LinkMetrics", "evaluate_links"]
