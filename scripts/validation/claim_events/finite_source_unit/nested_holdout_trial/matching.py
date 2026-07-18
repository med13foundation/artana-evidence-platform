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
        SealedEventSemantics,
        SealedGraphProjection,
        SealedNestedEventGraph,
        SealedProjectionSet,
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

    @property
    def completely_recovered_once(self) -> bool:
        return (
            len(self.inner_inventory_ids) == 1
            and len(self.outer_inventory_ids) == 1
            and self.expert_link_match_count == 1
            and self.complete_graph_match_count == 1
        )


@dataclass(frozen=True, slots=True)
class ProjectionMatchResult:
    """Independent match result for one frozen projection."""

    projection_id: str
    provenance: str
    match: NestedEventMatchResult
    completely_recovered_once: bool


@dataclass(frozen=True, slots=True)
class ProjectionSetMatchResult:
    """Per-projection results that never combine partial alternative matches."""

    projections: tuple[ProjectionMatchResult, ...]
    fully_recovered_projection_ids: tuple[str, ...]


def match_nested_event_graph(
    *,
    expert_graph: SealedNestedEventGraph,
    trusted: tuple[BoundClaimInventoryItem, ...],
    links: tuple[BoundControlledEventLink, ...],
    event_semantics: tuple[SealedEventSemantics, ...] | None = None,
) -> NestedEventMatchResult:
    """Match exact source identities while allowing source-valid extra claims."""

    if (
        len(expert_graph.events) != _EXPECTED_EVENT_COUNT
        or len(expert_graph.links) != _EXPECTED_LINK_COUNT
    ):
        raise ValueError("nested holdout matcher requires two events and one link")
    expert_link = expert_graph.links[0]
    events_by_id = {event.event_id: event for event in expert_graph.events}
    semantics_by_id = {
        semantics.event_id: semantics for semantics in (event_semantics or ())
    }
    inner = events_by_id[expert_link.controlled_event_id]
    outer = events_by_id[expert_link.controller_event_id]
    trusted_by_id = {candidate.inventory_id: candidate for candidate in trusted}
    inner_ids = tuple(
        candidate.inventory_id
        for candidate in trusted
        if _event_matches(
            inner,
            candidate,
            semantics_by_id.get(inner.event_id),
            expected_reference_argument_count=0,
        )
    )
    outer_ids = tuple(
        candidate.inventory_id
        for candidate in trusted
        if _event_matches(
            outer,
            candidate,
            semantics_by_id.get(outer.event_id),
            expected_reference_argument_count=1,
        )
    )
    matched_links = tuple(
        link
        for link in links
        if link.controlled_inventory_id in inner_ids
        and link.controller_inventory_id in outer_ids
        and link.controller_event_role.value == expert_link.event_role
        and _link_uses_reference_argument(
            link=link,
            expert=outer,
            candidate=trusted_by_id[link.controller_inventory_id],
        )
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


def match_projection_set(
    *,
    projection_set: SealedProjectionSet,
    trusted: tuple[BoundClaimInventoryItem, ...],
    links: tuple[BoundControlledEventLink, ...],
) -> ProjectionSetMatchResult:
    """Award credit only to a complete match inside one frozen projection."""

    matches = tuple(
        _match_projection(projection=projection, trusted=trusted, links=links)
        for projection in projection_set.projections
    )
    return ProjectionSetMatchResult(
        projections=matches,
        fully_recovered_projection_ids=tuple(
            match.projection_id
            for match in matches
            if match.completely_recovered_once
        ),
    )


def _match_projection(
    *,
    projection: SealedGraphProjection,
    trusted: tuple[BoundClaimInventoryItem, ...],
    links: tuple[BoundControlledEventLink, ...],
) -> ProjectionMatchResult:
    result = match_nested_event_graph(
        expert_graph=projection.graph,
        trusted=trusted,
        links=links,
        event_semantics=projection.event_semantics,
    )
    return ProjectionMatchResult(
        projection_id=projection.projection_id,
        provenance=projection.provenance.value,
        match=result,
        completely_recovered_once=result.completely_recovered_once,
    )


def _event_matches(
    expert: SealedEvent,
    candidate: BoundClaimInventoryItem,
    semantics: SealedEventSemantics | None,
    *,
    expected_reference_argument_count: int,
) -> bool:
    return (
        (semantics is None or _event_semantics_match(semantics, candidate))
        and candidate.item.event_type.value == expert.event_type
        and candidate.trigger_mention.exact_span == expert.trigger.exact_span
        and candidate.trigger_mention.source_start == expert.trigger.source_start
        and candidate.trigger_mention.source_end == expert.trigger.source_end
        and _direct_argument_match_indices(
            expert,
            candidate,
            expected_reference_argument_count=expected_reference_argument_count,
        )
        is not None
    )


def _direct_argument_match_indices(
    expert: SealedEvent,
    candidate: BoundClaimInventoryItem,
    *,
    expected_reference_argument_count: int,
) -> tuple[int, ...] | None:
    if len(candidate.bound_arguments) != (
        len(expert.arguments) + expected_reference_argument_count
    ):
        return None
    matched_indices: list[int] = []
    for expected in expert.arguments:
        indices = tuple(
            index
            for index, actual in enumerate(candidate.bound_arguments)
            if _argument_matches(expected, actual)
        )
        if len(indices) != 1:
            return None
        matched_indices.append(indices[0])
    if len(set(matched_indices)) != len(matched_indices):
        return None
    return tuple(matched_indices)


def _link_uses_reference_argument(
    *,
    link: BoundControlledEventLink,
    expert: SealedEvent,
    candidate: BoundClaimInventoryItem,
) -> bool:
    direct_indices = _direct_argument_match_indices(
        expert,
        candidate,
        expected_reference_argument_count=1,
    )
    return (
        direct_indices is not None
        and link.controller_argument_index not in direct_indices
    )


def _event_semantics_match(
    expected: SealedEventSemantics,
    candidate: BoundClaimInventoryItem,
) -> bool:
    return (
        candidate.item.claim_kind is expected.claim_kind
        and candidate.item.polarity is expected.polarity
        and candidate.item.epistemic_status is expected.epistemic_status
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


__all__ = [
    "NestedEventMatchResult",
    "ProjectionMatchResult",
    "ProjectionSetMatchResult",
    "match_nested_event_graph",
    "match_projection_set",
]
