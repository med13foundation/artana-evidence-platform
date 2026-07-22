"""Agent-owned linking contract assembled into the existing typed graph."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.context_experiment.source_first.anchors import (
    resolve_anchor,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.contracts import (
    CompleteEventOutput,
    EventArgument,
    EventNode,
    EvidenceSpan,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.contracts import (
    ParticipantNode as ResolvedParticipantNode,
)
from scripts.validation.public_gold.staged_event.contracts import (
    SourceEntityType,  # noqa: TC001 - Pydantic runtime schema
    StrictStageModel,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.context_experiment.source_first.inventory import (
        ResolvedInventoryEvent,
    )


class ParticipantNode(StrictStageModel):
    participant_id: str = Field(min_length=1, max_length=128)
    entity_type: SourceEntityType = Field(strict=False)
    exact_text: str = Field(min_length=1, max_length=512)
    exact_evidence: str = Field(min_length=1, max_length=4000)
    explanation: str = Field(min_length=1, max_length=2000)


class EventArgumentDecision(StrictStageModel):
    role: Literal["THEME", "CAUSE", "INSTRUMENT", "OTHER_EXPLICIT"]
    target_kind: Literal["PARTICIPANT", "EVENT"]
    target_id: str = Field(min_length=1, max_length=128)
    explanation: str = Field(min_length=1, max_length=2000)


class EventLinks(StrictStageModel):
    event_id: str = Field(min_length=1, max_length=128)
    arguments: tuple[EventArgumentDecision, ...] = Field(max_length=32)


class EventLinkingOutput(StrictStageModel):
    packet_id: str = Field(min_length=1, max_length=128)
    frozen_event_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    participants: tuple[ParticipantNode, ...] = Field(max_length=32)
    event_links: tuple[EventLinks, ...] = Field(min_length=1, max_length=32)
    root_event_id: str | None = Field(default=None, max_length=128)
    structure_assessment: Literal[
        "COMPLETE", "INCOMPLETE", "CONTRADICTED", "ABSTAIN"
    ]
    structure_explanation: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def unique_ids(self) -> EventLinkingOutput:
        participant_ids = [item.participant_id for item in self.participants]
        event_ids = [item.event_id for item in self.event_links]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("participant IDs must be unique")
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("linked event IDs must be unique")
        return self


def assemble_graph(
    output: EventLinkingOutput,
    *,
    inventory: tuple[ResolvedInventoryEvent, ...],
    source: str,
    scope_start: int,
    scope_end: int,
) -> CompleteEventOutput:
    frozen_ids = tuple(item.temporary_event_id for item in inventory)
    if output.frozen_event_ids != frozen_ids:
        raise ValueError("linking output changed frozen event inventory")
    links = {item.event_id: item for item in output.event_links}
    if set(links) != set(frozen_ids):
        raise ValueError("linking output added or removed event nodes")
    participants = tuple(
        _resolved_participant(
            item,
            source=source,
            scope_start=scope_start,
            scope_end=scope_end,
        )
        for item in output.participants
    )
    events = tuple(
        EventNode(
            event_id=item.temporary_event_id,
            event_type=item.event_type,
            trigger=EvidenceSpan(
                start=item.trigger.start,
                end=item.trigger.end,
                exact_text=item.trigger.exact_text,
            ),
            arguments=tuple(
                EventArgument(
                    role=argument.role,
                    target_kind=argument.target_kind,
                    target_id=argument.target_id,
                )
                for argument in links[item.temporary_event_id].arguments
            ),
            short_explanation=item.explanation,
        )
        for item in inventory
    )
    return CompleteEventOutput(
        packet_id=output.packet_id,
        participants=participants,
        events=events,
        root_event_id=output.root_event_id,
        structure_assessment=output.structure_assessment,
        structure_explanation=output.structure_explanation,
    )


def _resolved_participant(
    participant: ParticipantNode,
    *,
    source: str,
    scope_start: int,
    scope_end: int,
) -> ResolvedParticipantNode:
    anchor = resolve_anchor(
        source=source,
        scope_start=scope_start,
        scope_end=scope_end,
        exact_text=participant.exact_text,
        exact_evidence=participant.exact_evidence,
    )
    return ResolvedParticipantNode(
        participant_id=participant.participant_id,
        entity_type=participant.entity_type,
        evidence=EvidenceSpan(
            start=anchor.start,
            end=anchor.end,
            exact_text=anchor.exact_text,
        ),
    )


__all__ = [
    "EventArgumentDecision",
    "EventLinkingOutput",
    "EventLinks",
    "ParticipantNode",
    "assemble_graph",
]
