"""Deterministic span resolution and assembly for staged agent findings."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, TypeVar

from artana_evidence_api.document_extraction_support.scientific_events import (
    EventArgumentTarget,
    MentionKind,
    ScientificEventDocument,
)

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    ExtractedArgument,
    ExtractedEvent,
    ExtractedMention,
    ExtractedModifier,
    ExtractionProvenance,
    ScientificEventExtraction,
    assemble_scientific_event_document,
)
from scripts.validation.public_gold.lossless_event_offset_resolution import (
    resolve_extraction_offsets,
)
from scripts.validation.public_gold.staged_event.contracts import (
    CompletionOutput,
    DiscoveryCandidate,
    EventModifierFinding,
    EventParticipantInventory,
    EventRoleAssignment,
    EventVerification,
    ModifierDecision,
    ModifierOutput,
    ParticipantCandidate,
    ParticipantInventoryOutput,
    ParticipantTargetKind,
    RoleAssignment,
    RoleAssignmentOutput,
    VerificationOutput,
    VerificationVerdict,
)

_IndexedStageT = TypeVar("_IndexedStageT", bound="_EventBoundStage")


class _EventBoundStage(Protocol):
    event_id: str


class StagedAssemblyError(ValueError):
    """Staged outputs cannot be assembled without guessing or relabeling."""


@dataclass(frozen=True, slots=True)
class ResolvedCandidate:
    event_id: str
    trigger_id: str
    trigger_start: int
    trigger_end: int
    passage_start: int
    passage_end: int
    candidate: DiscoveryCandidate

    def as_json(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "trigger_id": self.trigger_id,
            "trigger_start": self.trigger_start,
            "trigger_end": self.trigger_end,
            "passage_start": self.passage_start,
            "passage_end": self.passage_end,
            "trigger_text": self.candidate.trigger_text,
            "event_passage": self.candidate.event_passage,
            "source_event_type": self.candidate.source_event_type.value,
            "statement_kind": self.candidate.statement_kind.value,
        }


@dataclass(frozen=True, slots=True)
class DiscoveryResolution:
    candidates: tuple[ResolvedCandidate, ...]
    duplicate_candidates: int


@dataclass(frozen=True, slots=True)
class StagedAssembly:
    document: ScientificEventDocument
    extraction: ScientificEventExtraction
    included_event_ids: tuple[str, ...]
    abstentions: dict[str, int]


@dataclass(frozen=True, slots=True)
class AssemblyInputs:
    candidates: tuple[ResolvedCandidate, ...]
    participant_output: ParticipantInventoryOutput
    role_output: RoleAssignmentOutput
    modifier_output: ModifierOutput
    verification_output: VerificationOutput
    document_id: str
    source_text: str
    source_sha256: str
    producer_identity: str


def resolve_discovery_candidates(
    candidates: tuple[DiscoveryCandidate, ...],
    *,
    source_text: str,
    source_sha256: str,
) -> DiscoveryResolution:
    """Resolve exact passages and triggers, deduplicating identical semantic spans."""

    resolved: list[ResolvedCandidate] = []
    seen: set[tuple[int, int, int, int, str]] = set()
    duplicates = 0
    for candidate in candidates:
        passage_start = _unique_start(
            source_text,
            candidate.event_passage,
            label="event passage",
        )
        local_trigger_start = _unique_start(
            candidate.event_passage,
            candidate.trigger_text,
            label="event-local trigger",
        )
        trigger_start = passage_start + local_trigger_start
        trigger_end = trigger_start + len(candidate.trigger_text)
        passage_end = passage_start + len(candidate.event_passage)
        key = (
            passage_start,
            passage_end,
            trigger_start,
            trigger_end,
            candidate.source_event_type.value,
        )
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        event_id = _stable_id("E", source_sha256, *key)
        trigger_id = _stable_id(
            "T",
            source_sha256,
            trigger_start,
            trigger_end,
            candidate.source_event_type.value,
        )
        resolved.append(
            ResolvedCandidate(
                event_id=event_id,
                trigger_id=trigger_id,
                trigger_start=trigger_start,
                trigger_end=trigger_end,
                passage_start=passage_start,
                passage_end=passage_end,
                candidate=candidate,
            )
        )
    return DiscoveryResolution(tuple(resolved), duplicates)


def assemble_staged_document(  # noqa: PLR0915 - validates one atomic stage bundle.
    inputs: AssemblyInputs,
) -> StagedAssembly:
    """Assemble only fully entailed staged events without changing their semantics."""

    candidate_index = {item.event_id: item for item in inputs.candidates}
    inventories = _exact_index(
        inputs.participant_output.inventories,
        expected=set(candidate_index),
        label="participant stage",
    )
    roles = _exact_index(
        inputs.role_output.events,
        expected=set(candidate_index),
        label="role stage",
    )
    modifiers = _exact_index(
        inputs.modifier_output.events,
        expected=set(candidate_index),
        label="modifier stage",
    )
    verifications = _exact_index(
        inputs.verification_output.events,
        expected=set(candidate_index),
        label="verification stage",
    )
    included = {
        event_id
        for event_id in candidate_index
        if _is_included(
            inventories[event_id],
            roles[event_id],
            modifiers[event_id],
            verifications[event_id],
        )
    }
    mentions: dict[str, ExtractedMention] = {}
    events: list[ExtractedEvent] = []
    for event_id in sorted(included):
        candidate = candidate_index[event_id]
        inventory = inventories[event_id]
        event_roles = roles[event_id]
        modifier = modifiers[event_id]
        verification = verifications[event_id]
        trigger = ExtractedMention(
            annotation_id=candidate.trigger_id,
            source_type=candidate.candidate.source_event_type.value,
            mention_kind=MentionKind.TRIGGER,
            start=candidate.trigger_start,
            end=candidate.trigger_end,
            exact_text=candidate.candidate.trigger_text,
        )
        mentions[trigger.annotation_id] = trigger
        participant_index = _participant_index(inventory)
        assignment_index = _assignment_index(event_roles, participant_index)
        arguments: list[ExtractedArgument] = []
        direct_spans: list[tuple[int, int]] = []
        for participant_key in sorted(assignment_index):
            participant = participant_index[participant_key]
            assignment = assignment_index[participant_key]
            local_start = _unique_start(
                candidate.candidate.event_passage,
                participant.exact_text,
                label=f"{event_id} participant {participant_key}",
            )
            if assignment.target_kind is not participant.candidate_target_kind:
                raise StagedAssemblyError(
                    f"{event_id}: participant and role target kinds contradict"
                )
            if assignment.target_kind is ParticipantTargetKind.EVENT:
                target_event_id = assignment.target_event_id
                if target_event_id not in candidate_index:
                    raise StagedAssemblyError(
                        f"{event_id}: role references an unknown event"
                    )
                if target_event_id not in included:
                    raise StagedAssemblyError(
                        f"{event_id}: nested target did not pass all stages"
                    )
                target_candidate = candidate_index[target_event_id]
                if participant.exact_text != target_candidate.candidate.trigger_text:
                    raise StagedAssemblyError(
                        f"{event_id}: event target text differs from target trigger"
                    )
                arguments.append(
                    ExtractedArgument(
                        source_role=assignment.source_role.value,
                        target_kind=EventArgumentTarget.EVENT,
                        target_id=target_event_id,
                    )
                )
                continue
            start = candidate.passage_start + local_start
            end = start + len(participant.exact_text)
            direct_spans.append((start, end))
            if participant.source_entity_type is None:
                raise StagedAssemblyError(
                    f"{event_id}: direct participant lacks an entity category"
                )
            mention_id = _stable_id(
                "T",
                inputs.source_sha256,
                start,
                end,
                participant.source_entity_type.value,
            )
            mentions.setdefault(
                mention_id,
                ExtractedMention(
                    annotation_id=mention_id,
                    source_type=participant.source_entity_type.value,
                    mention_kind=MentionKind.ENTITY,
                    start=start,
                    end=end,
                    exact_text=participant.exact_text,
                ),
            )
            arguments.append(
                ExtractedArgument(
                    source_role=assignment.source_role.value,
                    target_kind=EventArgumentTarget.PARTICIPANT,
                    target_id=mention_id,
                )
            )
        _validate_verification_evidence(
            verification,
            source_text=inputs.source_text,
            trigger_span=(candidate.trigger_start, candidate.trigger_end),
            participant_spans=tuple(direct_spans),
        )
        event_modifiers = _modifiers_for_event(
            modifier,
            candidate=candidate,
            source_text=inputs.source_text,
            source_sha256=inputs.source_sha256,
        )
        events.append(
            ExtractedEvent(
                annotation_id=event_id,
                source_event_type=candidate.candidate.source_event_type,
                artana_event_family=None,
                trigger_id=candidate.trigger_id,
                arguments=tuple(arguments),
                modifiers=event_modifiers,
            )
        )
    extraction = ScientificEventExtraction(
        status="EXTRACTED",
        mentions=tuple(sorted(mentions.values(), key=lambda item: item.annotation_id)),
        events=tuple(events),
        abstention_reason=None,
    )
    offset_resolution = resolve_extraction_offsets(
        extraction, source_text=inputs.source_text
    )
    try:
        document = assemble_scientific_event_document(
            offset_resolution.extraction,
            document_id=inputs.document_id,
            source_text=inputs.source_text,
            source_sha256=inputs.source_sha256,
            provenance=ExtractionProvenance(
                producer_identity=inputs.producer_identity,
                annotation_source_sha256=(offset_resolution.original_extraction_sha256),
            ),
        )
    except ValueError as exc:
        raise StagedAssemblyError(str(exc)) from exc
    return StagedAssembly(
        document=document,
        extraction=offset_resolution.extraction,
        included_event_ids=tuple(sorted(included)),
        abstentions={
            "participant": sum(
                item.decision == "ABSTAIN" for item in inventories.values()
            ),
            "role": sum(item.decision == "ABSTAIN" for item in roles.values()),
            "modifier": sum(
                item.decision is ModifierDecision.ABSTAIN for item in modifiers.values()
            ),
            "verification": sum(
                item.verdict is VerificationVerdict.ABSTAIN
                for item in verifications.values()
            ),
            "contradicted": sum(
                item.verdict is VerificationVerdict.CONTRADICTED
                for item in verifications.values()
            ),
            "insufficient": sum(
                item.verdict is VerificationVerdict.INSUFFICIENT
                for item in verifications.values()
            ),
        },
    )


def completion_stage_outputs(
    output: CompletionOutput,
) -> tuple[
    ParticipantInventoryOutput,
    RoleAssignmentOutput,
    ModifierOutput,
    VerificationOutput,
]:
    """Convert the one allowed completion packet into the same stage boundaries."""

    return (
        ParticipantInventoryOutput(
            inventories=tuple(
                EventParticipantInventory(
                    event_id=item.event_id,
                    decision="INVENTORIED",
                    participants=item.participants,
                    abstention_reason=None,
                )
                for item in output.events
            )
        ),
        RoleAssignmentOutput(
            events=tuple(
                EventRoleAssignment(
                    event_id=item.event_id,
                    decision="ASSIGNED",
                    assignments=item.roles,
                    abstention_reason=None,
                )
                for item in output.events
            )
        ),
        ModifierOutput(events=tuple(item.modifier for item in output.events)),
        VerificationOutput(
            events=tuple(item.verification for item in output.events),
            missing_supported_events=(),
        ),
    )


def _is_included(
    inventory: EventParticipantInventory,
    roles: EventRoleAssignment,
    modifier: EventModifierFinding,
    verification: EventVerification,
) -> bool:
    return (
        inventory.decision == "INVENTORIED"
        and roles.decision == "ASSIGNED"
        and modifier.decision is not ModifierDecision.ABSTAIN
        and verification.verdict is VerificationVerdict.ENTAILED
    )


def _participant_index(
    inventory: EventParticipantInventory,
) -> dict[str, ParticipantCandidate]:
    indexed = {item.participant_key: item for item in inventory.participants}
    if len(indexed) != len(inventory.participants):
        raise StagedAssemblyError(f"{inventory.event_id}: duplicate participant keys")
    return indexed


def _assignment_index(
    event: EventRoleAssignment,
    participants: dict[str, ParticipantCandidate],
) -> dict[str, RoleAssignment]:
    indexed = {item.participant_key: item for item in event.assignments}
    if len(indexed) != len(event.assignments):
        raise StagedAssemblyError(f"{event.event_id}: duplicate role assignments")
    if set(indexed) != set(participants):
        raise StagedAssemblyError(
            f"{event.event_id}: role assignments do not cover the participant inventory"
        )
    return indexed


def _modifiers_for_event(
    finding: EventModifierFinding,
    *,
    candidate: ResolvedCandidate,
    source_text: str,
    source_sha256: str,
) -> tuple[ExtractedModifier, ...]:
    if finding.decision is ModifierDecision.NEITHER:
        return ()
    evidence = finding.exact_evidence
    if evidence is None:
        raise StagedAssemblyError(f"{finding.event_id}: modifier evidence is absent")
    _unique_start(
        candidate.candidate.event_passage, evidence, label="modifier evidence"
    )
    kinds = {
        ModifierDecision.NEGATED: ("Negation",),
        ModifierDecision.SPECULATIVE: ("Speculation",),
        ModifierDecision.BOTH: ("Negation", "Speculation"),
    }.get(finding.decision)
    if kinds is None:
        raise StagedAssemblyError(
            f"{finding.event_id}: modifier decision is not usable"
        )
    if evidence not in source_text:
        raise StagedAssemblyError(f"{finding.event_id}: modifier evidence is absent")
    return tuple(
        ExtractedModifier(
            annotation_id=_stable_id("M", source_sha256, finding.event_id, kind),
            source_modifier_type=kind,  # type: ignore[arg-type]
        )
        for kind in kinds
    )


def _validate_verification_evidence(
    finding: EventVerification,
    *,
    source_text: str,
    trigger_span: tuple[int, int],
    participant_spans: tuple[tuple[int, int], ...],
) -> None:
    evidence = finding.exact_evidence
    if evidence is None:
        raise StagedAssemblyError(f"{finding.event_id}: entailed evidence is absent")
    start = _unique_start(source_text, evidence, label="verification evidence")
    end = start + len(evidence)
    for required_start, required_end in (trigger_span, *participant_spans):
        if start > required_start or end < required_end:
            raise StagedAssemblyError(
                f"{finding.event_id}: verification evidence omits required local spans"
            )


def _exact_index(
    items: tuple[_IndexedStageT, ...], *, expected: set[str], label: str
) -> dict[str, _IndexedStageT]:
    indexed: dict[str, _IndexedStageT] = {}
    for item in items:
        event_id = item.event_id
        if event_id in indexed:
            raise StagedAssemblyError(
                f"{label} contains duplicate or invalid event IDs"
            )
        indexed[event_id] = item
    if set(indexed) != expected:
        raise StagedAssemblyError(f"{label} does not cover every discovered event")
    return indexed


def _unique_start(source: str, exact_text: str, *, label: str) -> int:
    starts: list[int] = []
    cursor = 0
    while True:
        start = source.find(exact_text, cursor)
        if start < 0:
            break
        starts.append(start)
        cursor = start + 1
    if len(starts) != 1:
        condition = "absent" if not starts else "ambiguous"
        raise StagedAssemblyError(f"{label} is {condition} in its permitted scope")
    return starts[0]


def _stable_id(prefix: str, source_sha256: str, *parts: object) -> str:
    material = "\x1f".join((source_sha256, *(str(part) for part in parts)))
    return f"{prefix}-{hashlib.sha256(material.encode()).hexdigest()[:20]}"


__all__ = [
    "AssemblyInputs",
    "DiscoveryResolution",
    "ResolvedCandidate",
    "StagedAssembly",
    "StagedAssemblyError",
    "assemble_staged_document",
    "completion_stage_outputs",
    "resolve_discovery_candidates",
]
