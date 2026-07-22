"""Validate agent-selected participant spans without inferring scientific meaning."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.contracts import (
    EventParticipantInventory,
    ParticipantCandidate,
    ParticipantInventoryOutput,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.context_experiment.contracts import (
        SourceBoundParticipantOutput,
    )
    from scripts.validation.public_gold.staged_event.context_experiment.panel import (
        ContextPanel,
    )


class ParticipantGroundingError(ValueError):
    """A participant span violates source or event-local custody."""


def validate_participant_grounding(
    output: SourceBoundParticipantOutput, *, panel: ContextPanel
) -> None:
    packets = {str(item["event_id"]): item for item in panel.packets}
    source = str(panel.shared_context["source_text"])
    seen: set[tuple[str, str]] = set()
    for inventory in output.inventories:
        packet = packets[inventory.event_id]
        scope = packet["permitted_evidence_offsets"]
        if not isinstance(scope, dict):
            raise ParticipantGroundingError("event scope is malformed")
        scope_start = scope.get("start")
        scope_end = scope.get("end")
        if not isinstance(scope_start, int) or not isinstance(scope_end, int):
            raise ParticipantGroundingError("event scope offsets are malformed")
        for participant in inventory.participants:
            if source[participant.start : participant.end] != participant.exact_text:
                raise ParticipantGroundingError(
                    "participant text does not resolve exactly"
                )
            if participant.start < scope_start or participant.end > scope_end:
                raise ParticipantGroundingError(
                    "participant lies outside event-local scope"
                )
            identity = (inventory.event_id, participant.occurrence_id)
            if identity in seen:
                raise ParticipantGroundingError(
                    "participant occurrence identity is duplicated"
                )
            seen.add(identity)


def ground_participants(
    output: SourceBoundParticipantOutput, *, panel: ContextPanel
) -> ParticipantInventoryOutput:
    validate_participant_grounding(output, panel=panel)
    source = str(panel.shared_context["source_text"])
    return ParticipantInventoryOutput(
        inventories=tuple(
            EventParticipantInventory(
                event_id=item.event_id,
                decision=item.decision,
                participants=tuple(
                    ParticipantCandidate(
                        participant_key=participant.participant_key,
                        exact_text=participant.exact_text,
                        occurrence_id=participant.occurrence_id,
                        occurrence_index=_document_occurrence_index(
                            source, participant.exact_text, participant.start
                        ),
                        candidate_target_kind=participant.candidate_target_kind,
                        source_entity_type=participant.source_entity_type,
                        explanation=participant.explanation,
                    )
                    for participant in item.participants
                ),
                abstention_reason=item.abstention_reason,
            )
            for item in output.inventories
        )
    )


def _document_occurrence_index(source: str, exact_text: str, start: int) -> int:
    cursor = 0
    occurrence = 0
    while True:
        found = source.find(exact_text, cursor)
        if found < 0:
            raise ParticipantGroundingError("participant occurrence cannot be indexed")
        if found == start:
            return occurrence
        occurrence += 1
        cursor = found + 1


__all__ = [
    "ground_participants",
    "ParticipantGroundingError",
    "validate_participant_grounding",
]
