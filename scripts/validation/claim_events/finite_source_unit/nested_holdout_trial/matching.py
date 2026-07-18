"""Deterministic comparison of trusted source-bound events to sealed structure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimArgument,
        BoundClaimInventoryItem,
        BoundControlledEventLink,
    )

    from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
        SealedArgument,
        SealedEvent,
        SealedNestedEventGraph,
    )

_EXPECTED_EVENT_COUNT = 2
_EXPECTED_LINK_COUNT = 1


@dataclass(frozen=True, slots=True)
class NestedEventMatchResult:
    """Unique event identities and complete expert-link matches."""

    inner_inventory_ids: tuple[str, ...]
    outer_inventory_ids: tuple[str, ...]
    expert_link_match_count: int
    complete_graph_match_count: int


def match_nested_event_graph(
    *,
    expert_graph: SealedNestedEventGraph,
    trusted: tuple[BoundClaimInventoryItem, ...],
    links: tuple[BoundControlledEventLink, ...],
) -> NestedEventMatchResult:
    """Match exact source identities while allowing source-valid extra claims."""

    if (
        len(expert_graph.events) != _EXPECTED_EVENT_COUNT
        or len(expert_graph.links) != _EXPECTED_LINK_COUNT
    ):
        raise ValueError("nested holdout matcher requires two events and one link")
    expert_link = expert_graph.links[0]
    events_by_id = {event.event_id: event for event in expert_graph.events}
    inner = events_by_id[expert_link.controlled_event_id]
    outer = events_by_id[expert_link.controller_event_id]
    inner_ids = tuple(
        candidate.inventory_id
        for candidate in trusted
        if _event_matches(inner, candidate)
    )
    outer_ids = tuple(
        candidate.inventory_id
        for candidate in trusted
        if _event_matches(outer, candidate)
    )
    matched_links = tuple(
        link
        for link in links
        if link.controlled_inventory_id in inner_ids
        and link.controller_inventory_id in outer_ids
    )
    complete_pairs = {
        (link.controller_inventory_id, link.controlled_inventory_id)
        for link in matched_links
    }
    return NestedEventMatchResult(
        inner_inventory_ids=tuple(sorted(inner_ids)),
        outer_inventory_ids=tuple(sorted(outer_ids)),
        expert_link_match_count=len(matched_links),
        complete_graph_match_count=len(complete_pairs),
    )


def _event_matches(
    expert: SealedEvent,
    candidate: BoundClaimInventoryItem,
) -> bool:
    expected_arguments = tuple(expert.arguments)
    return (
        candidate.item.event_type.value == expert.event_type
        and candidate.trigger_mention.exact_span == expert.trigger.exact_span
        and candidate.trigger_mention.source_start == expert.trigger.source_start
        and candidate.trigger_mention.source_end == expert.trigger.source_end
        and all(
            any(_argument_matches(expected, actual) for actual in candidate.bound_arguments)
            for expected in expected_arguments
        )
    )


def _argument_matches(
    expected: SealedArgument,
    actual: BoundClaimArgument,
) -> bool:
    return (
        actual.argument.event_role.value == expected.event_role
        and actual.argument.role.value == expected.participant_type
        and actual.argument.exact_span == expected.exact_span
        and actual.primary_mention.source_start == expected.source_start
        and actual.primary_mention.source_end == expected.source_end
    )


__all__ = ["NestedEventMatchResult", "match_nested_event_graph"]
