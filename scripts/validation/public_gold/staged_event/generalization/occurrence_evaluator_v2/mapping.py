"""Occurrence-aware event and participant reference mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.matching import (
    mention_matches_any,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        StagedGeneralizationOutput,
    )
    from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
        FrozenCasePolicy,
        FrozenContextParticipant,
    )
    from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.bindings import (
        ValidatedBindings,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )


@dataclass(frozen=True, slots=True)
class ParticipantMapping:
    core: dict[str, str]
    context: dict[str, FrozenContextParticipant]
    unsupported: int
    permitted_nodes: int
    ambiguous_nodes: int


def map_events(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    validated: ValidatedBindings,
    reasons: list[str],
) -> tuple[dict[str, str], int]:
    mapping: dict[str, str] = {}
    unsupported = 0
    for actual in output.inventory:
        identity = validated.events[actual.event_id]
        matches = [
            expected
            for expected in case.reference.events
            if actual.event_type == expected.event_type
            and mention_matches_any(
                source=case.source,
                evidence=identity.evidence,
                mention=identity.mention,
                acceptable_texts=expected.acceptable_triggers,
            )
        ]
        if len(matches) != 1 or matches[0].event_key in mapping.values():
            unsupported += 1
            reasons.append(
                f"unsupported or duplicate event: {actual.event_type}/{actual.trigger_text}"
            )
            continue
        mapping[actual.event_id] = matches[0].event_key
    missing = {item.event_key for item in case.reference.events} - set(mapping.values())
    if missing:
        reasons.append(f"missing events: {sorted(missing)}")
    return mapping, unsupported


def map_participants(
    case: GeneralizationCase,
    output: StagedGeneralizationOutput,
    policy: FrozenCasePolicy,
    validated: ValidatedBindings,
    reasons: list[str],
) -> ParticipantMapping:
    core: dict[str, str] = {}
    context: dict[str, FrozenContextParticipant] = {}
    used_context: set[str] = set()
    unsupported = 0
    permitted_nodes = 0
    ambiguous_nodes = 0
    for actual in output.participants:
        identity = validated.participants[actual.participant_id]
        core_matches = [
            expected
            for expected in case.reference.participants
            if actual.entity_type == expected.entity_type
            and mention_matches_any(
                source=case.source,
                evidence=identity.evidence,
                mention=identity.mention,
                acceptable_texts=expected.acceptable_texts,
            )
        ]
        if (
            len(core_matches) == 1
            and core_matches[0].participant_key not in core.values()
        ):
            core[actual.participant_id] = core_matches[0].participant_key
            continue
        context_matches = [
            expected
            for expected in policy.contextual_participants
            if actual.entity_type == expected.entity_type
            and mention_matches_any(
                source=case.source,
                evidence=identity.evidence,
                mention=identity.mention,
                acceptable_texts=expected.acceptable_texts,
            )
        ]
        if len(context_matches) != 1:
            unsupported += 1
            reasons.append(
                "unsupported or duplicate participant: "
                f"{actual.entity_type}/{actual.exact_text}"
            )
            continue
        matched = context_matches[0]
        if matched.judgment_id in used_context:
            unsupported += 1
            reasons.append(f"duplicate contextual participant: {matched.judgment_id}")
            continue
        used_context.add(matched.judgment_id)
        context[actual.participant_id] = matched
        if matched.classification == "PERMITTED_CONTEXT":
            permitted_nodes += 1
        elif matched.classification == "AMBIGUOUS_REVIEW_ONLY":
            ambiguous_nodes += 1
            reasons.append(f"ambiguous contextual participant: {matched.judgment_id}")
        else:
            unsupported += 1
            reasons.append(f"forbidden contextual participant: {matched.judgment_id}")
    missing = {item.participant_key for item in case.reference.participants} - set(
        core.values()
    )
    if missing:
        reasons.append(f"missing required core participants: {sorted(missing)}")
    return ParticipantMapping(
        core,
        context,
        unsupported,
        permitted_nodes,
        ambiguous_nodes,
    )


__all__ = ["ParticipantMapping", "map_events", "map_participants"]
