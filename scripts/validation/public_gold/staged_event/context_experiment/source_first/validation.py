"""Deterministic structure and exposed-gold checks for source-first output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.context_experiment.source_first.contracts import (
        CompleteEventOutput,
        EventNode,
        EvidenceSpan,
    )
    from scripts.validation.public_gold.staged_event.context_experiment.specialist_replay import (
        DocumentAnnotations,
    )


SCOPE_START = 0
SCOPE_END = 222


class SourceFirstValidationError(ValueError):
    """The returned event graph violates a deterministic invariant."""


@dataclass(frozen=True)
class ExposedGraphComparison:
    exact: bool
    root_correct: bool
    participant_fidelity: bool
    nesting_correct: bool
    unsupported_node_count: int
    mismatch: str | None


def validate_structure(
    output: CompleteEventOutput,
    *,
    source: str,
    scope_start: int = SCOPE_START,
    scope_end: int = SCOPE_END,
) -> None:
    participant_ids = [item.participant_id for item in output.participants]
    event_ids = [item.event_id for item in output.events]
    _require_unique(participant_ids, "participant")
    _require_unique(event_ids, "event")
    if set(participant_ids) & set(event_ids):
        raise SourceFirstValidationError("participant and event IDs overlap")
    if output.root_event_id is None or output.root_event_id not in event_ids:
        raise SourceFirstValidationError("missing or unknown root event")
    for participant in output.participants:
        _validate_span(
            participant.evidence,
            source=source,
            scope_start=scope_start,
            scope_end=scope_end,
        )
    participant_set = set(participant_ids)
    event_set = set(event_ids)
    for event in output.events:
        _validate_span(
            event.trigger,
            source=source,
            scope_start=scope_start,
            scope_end=scope_end,
        )
        for argument in event.arguments:
            expected = (
                participant_set if argument.target_kind == "PARTICIPANT" else event_set
            )
            if argument.target_id not in expected:
                raise SourceFirstValidationError(
                    f"unknown or kind-mismatched target: {argument.target_id}"
                )
    reachable_events, reachable_participants = _reachable(output)
    if reachable_events != event_set:
        raise SourceFirstValidationError("disconnected event outside root finding")
    if reachable_participants != participant_set:
        raise SourceFirstValidationError(
            "disconnected participant outside root finding"
        )
    if output.structure_assessment == "COMPLETE" and not output.events:
        raise SourceFirstValidationError("self-reported COMPLETE graph is empty")


def _require_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise SourceFirstValidationError(f"duplicate {label} ID")


def _validate_span(
    span: EvidenceSpan, *, source: str, scope_start: int, scope_end: int
) -> None:
    if span.start < scope_start or span.end > scope_end:
        raise SourceFirstValidationError("evidence crosses permitted event scope")
    if source[span.start : span.end] != span.exact_text:
        raise SourceFirstValidationError("evidence text does not match source offsets")


def _reachable(output: CompleteEventOutput) -> tuple[set[str], set[str]]:
    events = {event.event_id: event for event in output.events}
    visited_events: set[str] = set()
    visited_participants: set[str] = set()

    def visit(event_id: str, stack: frozenset[str]) -> None:
        if event_id in stack:
            raise SourceFirstValidationError("cyclic event reference")
        if event_id in visited_events:
            return
        visited_events.add(event_id)
        for argument in events[event_id].arguments:
            if argument.target_kind == "EVENT":
                visit(argument.target_id, stack | {event_id})
            else:
                visited_participants.add(argument.target_id)

    assert output.root_event_id is not None
    visit(output.root_event_id, frozenset())
    return visited_events, visited_participants


def compare_exposed_nested_graph(output: CompleteEventOutput) -> ExposedGraphComparison:
    """Compare the validated graph with the exposed public-gold event projection."""
    participants = {
        (
            item.entity_type.value,
            item.evidence.start,
            item.evidence.end,
            item.evidence.exact_text,
        ): item
        for item in output.participants
    }
    expected_participants = {
        ("Gene_or_gene_product", 12, 17, "c-Myc"),
        ("Cell", 36, 47, "cancer cell"),
        ("Simple_chemical", 63, 74, "vinblastine"),
    }
    participant_fidelity = set(participants) == expected_participants
    events_by_trigger = {
        (item.trigger.start, item.trigger.end, item.trigger.exact_text): item
        for item in output.events
    }
    expected_triggers = {
        (0, 8, "Decrease"),
        (27, 35, "enhances"),
        (48, 59, "sensitivity"),
    }
    unsupported = max(0, len(participants) - 3) + max(0, len(events_by_trigger) - 3)
    if set(events_by_trigger) != expected_triggers:
        return ExposedGraphComparison(
            exact=False,
            root_correct=False,
            participant_fidelity=participant_fidelity,
            nesting_correct=False,
            unsupported_node_count=unsupported,
            mismatch="event triggers do not reproduce the exposed complete finding",
        )
    decrease = events_by_trigger[(0, 8, "Decrease")]
    root = events_by_trigger[(27, 35, "enhances")]
    sensitivity = events_by_trigger[(48, 59, "sensitivity")]
    root_correct = output.root_event_id == root.event_id
    if not participant_fidelity:
        return ExposedGraphComparison(
            exact=False,
            root_correct=root_correct,
            participant_fidelity=False,
            nesting_correct=False,
            unsupported_node_count=unsupported,
            mismatch="participants do not reproduce the exposed complete finding",
        )
    expected_edges = {
        root.event_id: {
            ("CAUSE", "EVENT", decrease.event_id),
            ("THEME", "EVENT", sensitivity.event_id),
        },
        decrease.event_id: {
            (
                "THEME",
                "PARTICIPANT",
                participants[("Gene_or_gene_product", 12, 17, "c-Myc")].participant_id,
            )
        },
        sensitivity.event_id: {
            (
                "THEME",
                "PARTICIPANT",
                participants[("Cell", 36, 47, "cancer cell")].participant_id,
            ),
            (
                "CAUSE",
                "PARTICIPANT",
                participants[("Simple_chemical", 63, 74, "vinblastine")].participant_id,
            ),
        },
    }
    actual_edges = {
        event.event_id: {
            (argument.role, argument.target_kind, argument.target_id)
            for argument in event.arguments
        }
        for event in output.events
    }
    nesting_correct = actual_edges == expected_edges
    exact = (
        output.structure_assessment == "COMPLETE"
        and participant_fidelity
        and root_correct
        and nesting_correct
        and unsupported == 0
    )
    return ExposedGraphComparison(
        exact=exact,
        root_correct=root_correct,
        participant_fidelity=participant_fidelity,
        nesting_correct=nesting_correct,
        unsupported_node_count=unsupported,
        mismatch=None
        if exact
        else "typed event graph differs from exposed public gold",
    )


def event_by_id(output: CompleteEventOutput, event_id: str) -> EventNode:
    return next(event for event in output.events if event.event_id == event_id)


def compare_to_exposed_gold_root(
    output: CompleteEventOutput,
    *,
    gold: DocumentAnnotations,
    gold_root_id: str,
) -> ExposedGraphComparison:
    """Compare one returned graph with a dependency-closed exposed gold root."""
    gold_event_ids: set[str] = set()
    gold_participant_ids: set[str] = set()

    def collect(event_id: str) -> None:
        if event_id in gold_event_ids:
            return
        gold_event_ids.add(event_id)
        for argument in gold.events[event_id].arguments:
            if argument.target_id in gold.events:
                collect(argument.target_id)
            else:
                gold_participant_ids.add(argument.target_id)

    collect(gold_root_id)

    def gold_event_key(event_id: str) -> tuple[str, int, int, str]:
        event = gold.events[event_id]
        trigger = gold.text_bounds[event.trigger_id]
        return event.category, trigger.start, trigger.end, trigger.text

    def gold_participant_key(participant_id: str) -> tuple[str, int, int, str]:
        participant = gold.text_bounds[participant_id]
        return (
            participant.category,
            participant.start,
            participant.end,
            participant.text,
        )

    predicted_event_keys = {
        event.event_id: (
            event.event_type.value,
            event.trigger.start,
            event.trigger.end,
            event.trigger.exact_text,
        )
        for event in output.events
    }
    predicted_participant_keys = {
        participant.participant_id: (
            participant.entity_type.value,
            participant.evidence.start,
            participant.evidence.end,
            participant.evidence.exact_text,
        )
        for participant in output.participants
    }
    expected_event_keys = {
        event_id: gold_event_key(event_id) for event_id in gold_event_ids
    }
    expected_participant_keys = {
        participant_id: gold_participant_key(participant_id)
        for participant_id in gold_participant_ids
    }
    participant_fidelity = set(predicted_participant_keys.values()) == set(
        expected_participant_keys.values()
    )
    event_fidelity = set(predicted_event_keys.values()) == set(
        expected_event_keys.values()
    )
    unsupported = max(0, len(predicted_event_keys) - len(expected_event_keys)) + max(
        0, len(predicted_participant_keys) - len(expected_participant_keys)
    )
    predicted_root_key = (
        predicted_event_keys.get(output.root_event_id)
        if output.root_event_id is not None
        else None
    )
    root_correct = predicted_root_key == expected_event_keys[gold_root_id]
    if not participant_fidelity or not event_fidelity:
        return ExposedGraphComparison(
            exact=False,
            root_correct=root_correct,
            participant_fidelity=participant_fidelity,
            nesting_correct=False,
            unsupported_node_count=unsupported,
            mismatch="event or participant nodes differ from exposed public gold",
        )
    expected_edges: set[tuple[tuple[str, int, int, str], str, str, object]] = set()
    for event_id in gold_event_ids:
        source_key = expected_event_keys[event_id]
        for argument in gold.events[event_id].arguments:
            if argument.target_id in gold.events:
                target_kind = "EVENT"
                target_key: object = expected_event_keys[argument.target_id]
            else:
                target_kind = "PARTICIPANT"
                target_key = expected_participant_keys[argument.target_id]
            expected_edges.add(
                (source_key, argument.role.upper(), target_kind, target_key)
            )
    actual_edges: set[tuple[tuple[str, int, int, str], str, str, object]] = set()
    for event in output.events:
        source_key = predicted_event_keys[event.event_id]
        for predicted_argument in event.arguments:
            if predicted_argument.target_kind == "EVENT":
                target_key = predicted_event_keys[predicted_argument.target_id]
            else:
                target_key = predicted_participant_keys[predicted_argument.target_id]
            actual_edges.add(
                (
                    source_key,
                    predicted_argument.role,
                    predicted_argument.target_kind,
                    target_key,
                )
            )
    nesting_correct = actual_edges == expected_edges
    exact = (
        output.structure_assessment == "COMPLETE"
        and root_correct
        and participant_fidelity
        and event_fidelity
        and nesting_correct
        and unsupported == 0
    )
    return ExposedGraphComparison(
        exact=exact,
        root_correct=root_correct,
        participant_fidelity=participant_fidelity,
        nesting_correct=nesting_correct,
        unsupported_node_count=unsupported,
        mismatch=None
        if exact
        else "typed event graph differs from exposed public gold",
    )
