"""Deterministic comparison of trusted source-bound events to sealed structure."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
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


@dataclass(frozen=True, slots=True)
class NestedEventMatchResult:
    """Per-event identities and complete one-to-one graph assignments."""

    event_inventory_ids: tuple[tuple[str, tuple[str, ...]], ...]
    expected_event_count: int
    expected_link_count: int
    inner_inventory_ids: tuple[str, ...]
    outer_inventory_ids: tuple[str, ...]
    expert_link_match_count: int
    complete_graph_match_count: int

    @property
    def completely_recovered_once(self) -> bool:
        return (
            len(self.event_inventory_ids) == self.expected_event_count
            and all(
                len(inventory_ids) == 1
                for _, inventory_ids in self.event_inventory_ids
            )
            and self.expert_link_match_count == self.expected_link_count
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
    """Match a complete finite projection while allowing unrelated valid claims."""

    if not expert_graph.events:
        raise ValueError("holdout matcher requires at least one projected event")
    semantics_by_id = {
        semantics.event_id: semantics for semantics in (event_semantics or ())
    }
    reference_count_by_event = {
        event.event_id: sum(
            link.controller_event_id == event.event_id for link in expert_graph.links
        )
        for event in expert_graph.events
    }
    candidates_by_event = {
        event.event_id: tuple(
            candidate
            for candidate in trusted
            if _event_matches(
                event,
                candidate,
                semantics_by_id.get(event.event_id),
                expected_reference_argument_count=reference_count_by_event[event.event_id],
            )
        )
        for event in expert_graph.events
    }
    event_ids = tuple(event.event_id for event in expert_graph.events)
    assignments = _candidate_assignments(
        event_ids=event_ids,
        candidates_by_event=candidates_by_event,
    )
    complete_assignments = tuple(
        assignment
        for assignment in assignments
        if _matched_link_count(
            assignment=assignment,
            graph=expert_graph,
            links=links,
        )
        == len(expert_graph.links)
    )
    first_link = expert_graph.links[0] if expert_graph.links else None
    return NestedEventMatchResult(
        event_inventory_ids=tuple(
            (
                event_id,
                tuple(
                    sorted(
                        candidate.inventory_id
                        for candidate in candidates_by_event[event_id]
                    ),
                ),
            )
            for event_id in event_ids
        ),
        expected_event_count=len(expert_graph.events),
        expected_link_count=len(expert_graph.links),
        inner_inventory_ids=(
            ()
            if first_link is None
            else tuple(
                sorted(
                    candidate.inventory_id
                    for candidate in candidates_by_event[
                        first_link.controlled_event_id
                    ]
                ),
            )
        ),
        outer_inventory_ids=(
            ()
            if first_link is None
            else tuple(
                sorted(
                    candidate.inventory_id
                    for candidate in candidates_by_event[
                        first_link.controller_event_id
                    ]
                ),
            )
        ),
        expert_link_match_count=max(
            (
                _matched_link_count(
                    assignment=assignment,
                    graph=expert_graph,
                    links=links,
                )
                for assignment in assignments
            ),
            default=0,
        ),
        complete_graph_match_count=len(complete_assignments),
    )


def _candidate_assignments(
    *,
    event_ids: tuple[str, ...],
    candidates_by_event: dict[str, tuple[BoundClaimInventoryItem, ...]],
) -> tuple[dict[str, BoundClaimInventoryItem], ...]:
    candidate_groups = tuple(candidates_by_event[event_id] for event_id in event_ids)
    if any(not group for group in candidate_groups):
        return ()
    assignments: list[dict[str, BoundClaimInventoryItem]] = []
    for combination in product(*candidate_groups):
        inventory_ids = tuple(candidate.inventory_id for candidate in combination)
        if len(set(inventory_ids)) != len(inventory_ids):
            continue
        assignments.append(dict(zip(event_ids, combination, strict=True)))
    return tuple(assignments)


def _matched_link_count(
    *,
    assignment: dict[str, BoundClaimInventoryItem],
    graph: SealedNestedEventGraph,
    links: tuple[BoundControlledEventLink, ...],
) -> int:
    events_by_id = {event.event_id: event for event in graph.events}
    matched_count = 0
    for expected in graph.links:
        controller = assignment[expected.controller_event_id]
        controlled = assignment[expected.controlled_event_id]
        matching_links = tuple(
            link
            for link in links
            if link.controller_inventory_id == controller.inventory_id
            and link.controlled_inventory_id == controlled.inventory_id
            and link.controller_event_role.value == expected.event_role
            and _link_uses_reference_argument(
                link=link,
                expert=events_by_id[expected.controller_event_id],
                candidate=controller,
                expected_reference_argument_count=sum(
                    item.controller_event_id == expected.controller_event_id
                    for item in graph.links
                ),
            )
        )
        if len(matching_links) != 1:
            continue
        matched_count += 1
    return matched_count


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
    actual_reference_argument_count = len(candidate.bound_arguments) - len(
        expert.arguments,
    )
    if (
        actual_reference_argument_count < 0
        or (
            expected_reference_argument_count == 0
            and actual_reference_argument_count != 0
        )
        or (
            expected_reference_argument_count > 0
            and not 1
            <= actual_reference_argument_count
            <= expected_reference_argument_count
        )
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
    expected_reference_argument_count: int,
) -> bool:
    direct_indices = _direct_argument_match_indices(
        expert,
        candidate,
        expected_reference_argument_count=expected_reference_argument_count,
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
