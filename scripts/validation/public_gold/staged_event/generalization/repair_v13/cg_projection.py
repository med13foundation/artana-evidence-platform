"""Project actual Artana output onto the exact CG root dependency chain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    ExactSpan,
    SpanIdentityError,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        EventArgument,
        ParticipantNode,
        StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
        CgEntityTarget,
        CgEventKey,
        CgEventRule,
        V13NestedTwoLaneContract,
    )

_RESPONSIBLE_CORE_ARGUMENT_COUNT = 2


class FocusOccurrenceResolver(Protocol):
    def __call__(
        self,
        case: GeneralizationCase,
        *,
        exact_evidence: str,
        exact_text: str,
    ) -> ExactSpan: ...


@dataclass(frozen=True, slots=True)
class _ProjectionContext:
    case: GeneralizationCase
    output: StagedGeneralizationOutput
    contract: V13NestedTwoLaneContract
    resolve_occurrence: FocusOccurrenceResolver


def project_actual_root_dependency_chain(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    contract: V13NestedTwoLaneContract,
    *,
    resolve_occurrence: FocusOccurrenceResolver,
) -> dict[str, object] | None:
    """Return a chain only when it is transformable from the actual output."""
    context = _ProjectionContext(
        case=case,
        output=output,
        contract=contract,
        resolve_occurrence=resolve_occurrence,
    )
    if output.completeness != "COMPLETE":
        return None
    lane = contract.cg_root_dependency_chain
    events = _map_events(context)
    if events is None or output.root_event_id != events[lane.root_event_key]:
        return None
    linked = _map_links(context, events)
    if linked is None:
        return None
    cause_id, theme_id, context_ids = linked
    cause_target = next(
        item.target
        for item in lane.arguments
        if item.event_key == "responsible"
        and item.role == "Cause"
        and item.target is not None
    )
    theme_target = next(
        item.target
        for item in lane.arguments
        if item.event_key == "levels"
        and item.role == "Theme"
        and item.target is not None
    )
    participants = {item.participant_id: item for item in output.participants}
    cause = participants.get(cause_id)
    theme = participants.get(theme_id)
    if (
        cause is None
        or theme is None
        or not _participant_projects_to_target(
            context,
            cause,
            cause_target,
        )
        or not _participant_projects_to_target(
            context,
            theme,
            theme_target,
        )
    ):
        return None
    mapped_participants = {cause_id, theme_id} | context_ids
    if set(participants) != mapped_participants:
        return None
    if not _projection_offsets_resolve(context):
        return None
    return {
        "scope": lane.scope,
        "root_event_key": lane.root_event_key,
        "events": [event.model_dump(mode="json") for event in lane.events],
        "arguments": [
            argument.model_dump(mode="json", exclude_none=True)
            for argument in lane.arguments
        ],
        "artana_mapping": {
            "events": dict(events),
            "participants": {
                "cause": cause_id,
                "theme": theme_id,
                "dropped_source_context": sorted(context_ids),
            },
        },
        "review_only": True,
        "qualification_blocking": False,
        "qualification_credit": False,
        "graph_promotion_allowed": False,
    }


def _map_events(
    context: _ProjectionContext,
) -> dict[CgEventKey, str] | None:
    lane = context.contract.cg_root_dependency_chain
    if len(context.output.inventory) != len(lane.events):
        return None
    mapped: dict[CgEventKey, str] = {}
    for rule in lane.events:
        matches = tuple(
            event
            for event in context.output.inventory
            if event.event_type == rule.event_type
            and _event_projects_to_occurrence(
                context,
                event.exact_evidence,
                event.trigger_text,
                rule,
            )
        )
        if len(matches) != 1:
            return None
        mapped[rule.event_key] = matches[0].event_id
    if len(set(mapped.values())) != len(lane.events):
        return None
    return mapped


def _event_projects_to_occurrence(
    context: _ProjectionContext,
    event_evidence: str,
    event_trigger: str,
    target: CgEventRule,
) -> bool:
    if event_evidence != context.contract.source_lane.exact_evidence:
        return False
    source_rule = next(
        (
            item
            for item in context.contract.source_lane.events
            if item.event_key == target.event_key
        ),
        None,
    )
    allowed_triggers = (
        source_rule.acceptable_triggers
        if source_rule is not None
        else (target.exact_text,)
    )
    if event_trigger not in allowed_triggers:
        return False
    try:
        actual = context.resolve_occurrence(
            context.case,
            exact_evidence=event_evidence,
            exact_text=event_trigger,
        )
    except SpanIdentityError:
        return False
    expected = ExactSpan(
        start=target.start,
        end=target.end,
        exact_text=target.exact_text,
    )
    if context.case.source[expected.start : expected.end] != expected.exact_text:
        return False
    if event_trigger == target.exact_text:
        return actual == expected
    return actual.contains(expected)


def _map_links(
    context: _ProjectionContext,
    events: dict[CgEventKey, str],
) -> tuple[str, str, set[str]] | None:
    event_ids = tuple(item.event_id for item in context.output.inventory)
    link_ids = tuple(item.event_id for item in context.output.links)
    if not (
        len(link_ids) == len(event_ids)
        and len(set(link_ids)) == len(link_ids)
        and set(link_ids) == set(event_ids)
    ):
        return None
    by_event = {item.event_id: item.arguments for item in context.output.links}
    responsible = by_event.get(events["responsible"])
    elevating = by_event.get(events["elevating"])
    levels = by_event.get(events["levels"])
    if responsible is None or elevating is None or levels is None:
        return None

    context_ids: set[str] = set()
    responsible_core = _drop_source_context(
        context,
        responsible,
        context_ids,
    )
    elevating_core = _drop_source_context(
        context,
        elevating,
        context_ids,
    )
    levels_core = _drop_source_context(
        context,
        levels,
        context_ids,
    )
    if responsible_core is None or elevating_core is None or levels_core is None:
        return None
    cause = tuple(
        item.target_id
        for item in responsible_core
        if item.role == "CAUSAL_AGENT" and item.target_kind == "PARTICIPANT"
    )
    responsible_effect = tuple(
        item.target_id
        for item in responsible_core
        if item.role == "EFFECT_EVENT" and item.target_kind == "EVENT"
    )
    elevating_effect = tuple(
        item.target_id
        for item in elevating_core
        if item.role == "EFFECT_EVENT" and item.target_kind == "EVENT"
    )
    theme = tuple(
        item.target_id
        for item in levels_core
        if item.role == "AFFECTED_ENTITY" and item.target_kind == "PARTICIPANT"
    )
    if (
        len(responsible_core) != _RESPONSIBLE_CORE_ARGUMENT_COUNT
        or len(elevating_core) != 1
        or len(levels_core) != 1
        or len(cause) != 1
        or responsible_effect != (events["elevating"],)
        or elevating_effect != (events["levels"],)
        or len(theme) != 1
    ):
        return None
    return cause[0], theme[0], context_ids


def _drop_source_context(
    context: _ProjectionContext,
    arguments: tuple[EventArgument, ...],
    context_ids: set[str],
) -> tuple[EventArgument, ...] | None:
    participants = {item.participant_id: item for item in context.output.participants}
    core: list[EventArgument] = []
    context_rule = next(
        item
        for item in context.contract.source_lane.participants
        if item.participant_key == "infected_fibroblasts"
    )
    for argument in arguments:
        if (
            argument.role == "CONTEXTUAL_PARTICIPANT"
            and argument.target_kind == "PARTICIPANT"
        ):
            participant = participants.get(argument.target_id)
            if participant is None:
                return None
            span = _participant_span(
                context,
                participant,
            )
            if not (
                participant.entity_type == context_rule.entity_type
                and participant.exact_text == context_rule.exact_text
                and span is not None
                and span.start == context_rule.start
                and span.end == context_rule.end
            ):
                return None
            context_ids.add(participant.participant_id)
            continue
        core.append(argument)
    return tuple(core)


def _participant_projects_to_target(
    context: _ProjectionContext,
    participant: ParticipantNode,
    target: CgEntityTarget,
) -> bool:
    if (
        participant.entity_type != "GENE_OR_PROTEIN"
        or participant.exact_evidence != context.contract.source_lane.exact_evidence
    ):
        return False
    source_rules = tuple(
        item
        for item in context.contract.source_lane.participants
        if item.start <= target.start and target.end <= item.end
    )
    if len(source_rules) != 1:
        return False
    source_rule = source_rules[0]
    if participant.exact_text not in {
        source_rule.exact_text,
        target.exact_text,
    }:
        return False
    actual = _participant_span(
        context,
        participant,
    )
    expected = ExactSpan(
        start=target.start,
        end=target.end,
        exact_text=target.exact_text,
    )
    if (
        actual is None
        or context.case.source[expected.start : expected.end] != expected.exact_text
    ):
        return False
    if participant.exact_text == target.exact_text:
        return actual == expected
    source_occurrence = ExactSpan(
        start=source_rule.start,
        end=source_rule.end,
        exact_text=source_rule.exact_text,
    )
    return actual == source_occurrence and source_occurrence.contains(expected)


def _participant_span(
    context: _ProjectionContext,
    participant: ParticipantNode,
) -> ExactSpan | None:
    try:
        return context.resolve_occurrence(
            context.case,
            exact_evidence=participant.exact_evidence,
            exact_text=participant.exact_text,
        )
    except SpanIdentityError:
        return None


def _projection_offsets_resolve(
    context: _ProjectionContext,
) -> bool:
    lane = context.contract.cg_root_dependency_chain
    if any(
        context.case.source[event.start : event.end] != event.exact_text
        for event in lane.events
    ):
        return False
    return all(
        argument.target is None
        or context.case.source[argument.target.start : argument.target.end]
        == argument.target.exact_text
        for argument in lane.arguments
    )


__all__ = [
    "FocusOccurrenceResolver",
    "project_actual_root_dependency_chain",
]
