"""Fail-closed dependency quarantine for preserved staged-event outputs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeVar

from scripts.validation.public_gold.staged_event.contracts import (
    ModifierDecision,
    ModifierOutput,
    ParticipantInventoryOutput,
    ParticipantTargetKind,
    RoleAssignmentOutput,
    VerificationOutput,
    VerificationVerdict,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.assembly import ResolvedCandidate

_EventBoundT = TypeVar("_EventBoundT", bound="_EventBound")


class _EventBound(Protocol):
    event_id: str


class DiagnosticProjectionError(ValueError):
    """The preserved stage bundle cannot be projected without guessing."""


@dataclass(frozen=True, slots=True)
class QuarantinedEvent:
    event_id: str
    terminal_reason: str
    dependency_path: tuple[str, ...]

    @property
    def is_dependency_exclusion(self) -> bool:
        return len(self.dependency_path) > 1


@dataclass(frozen=True, slots=True)
class DiagnosticProjection:
    retained_event_ids: tuple[str, ...]
    quarantined_events: tuple[QuarantinedEvent, ...]

    @property
    def direct_exclusion_count(self) -> int:
        return sum(
            not event.is_dependency_exclusion for event in self.quarantined_events
        )

    @property
    def dependency_exclusion_count(self) -> int:
        return sum(event.is_dependency_exclusion for event in self.quarantined_events)


def project_dependency_closed_subgraph(
    *,
    candidates: tuple[ResolvedCandidate, ...],
    participants: ParticipantInventoryOutput,
    roles: RoleAssignmentOutput,
    modifiers: ModifierOutput,
    verifications: VerificationOutput,
) -> DiagnosticProjection:
    """Quarantine rejected events and every event that depends on them."""

    candidate_ids = _unique_ids((item.event_id for item in candidates), "discovery")
    participant_index = _exact_index(
        participants.inventories, candidate_ids, "participant"
    )
    role_index = _exact_index(roles.events, candidate_ids, "role")
    modifier_index = _exact_index(modifiers.events, candidate_ids, "modifier")
    verification_index = _exact_index(
        verifications.events, candidate_ids, "verification"
    )

    dependencies: dict[str, tuple[str, ...]] = {}
    for event_id, role_event in role_index.items():
        references = tuple(
            sorted(
                assignment.target_event_id
                for assignment in role_event.assignments
                if assignment.target_kind is ParticipantTargetKind.EVENT
                and assignment.target_event_id is not None
            )
        )
        unknown = set(references) - candidate_ids
        if unknown:
            raise DiagnosticProjectionError(
                f"{event_id}: unknown event references {sorted(unknown)}"
            )
        dependencies[event_id] = references
    _reject_cycles(dependencies)

    quarantined: dict[str, QuarantinedEvent] = {}
    for event_id in sorted(candidate_ids):
        reasons: list[str] = []
        participant = participant_index[event_id]
        role = role_index[event_id]
        modifier = modifier_index[event_id]
        verification = verification_index[event_id]
        if participant.decision != "INVENTORIED":
            reasons.append(f"participant:{participant.decision}")
        if role.decision != "ASSIGNED":
            reasons.append(f"role:{role.decision}")
        if modifier.decision is ModifierDecision.ABSTAIN:
            reasons.append("modifier:ABSTAIN")
        if verification.verdict is not VerificationVerdict.ENTAILED:
            reasons.append(f"verification:{verification.verdict.value}")
        if reasons:
            quarantined[event_id] = QuarantinedEvent(
                event_id=event_id,
                terminal_reason=";".join(reasons),
                dependency_path=(event_id,),
            )

    changed = True
    while changed:
        changed = False
        for event_id in sorted(candidate_ids - set(quarantined)):
            rejected_targets = [
                target for target in dependencies[event_id] if target in quarantined
            ]
            if not rejected_targets:
                continue
            target = min(
                rejected_targets,
                key=lambda item: (len(quarantined[item].dependency_path), item),
            )
            child = quarantined[target]
            quarantined[event_id] = QuarantinedEvent(
                event_id=event_id,
                terminal_reason=f"depends_on_rejected_event:{target}",
                dependency_path=(event_id, *child.dependency_path),
            )
            changed = True

    retained = tuple(sorted(candidate_ids - set(quarantined)))
    return DiagnosticProjection(
        retained_event_ids=retained,
        quarantined_events=tuple(quarantined[key] for key in sorted(quarantined)),
    )


def _unique_ids(values: Iterable[str], label: str) -> set[str]:
    sequence = tuple(values)
    result = set(sequence)
    if len(result) != len(sequence):
        raise DiagnosticProjectionError(f"{label} contains duplicate event identities")
    return result


def _exact_index(
    items: tuple[_EventBoundT, ...], expected: set[str], label: str
) -> dict[str, _EventBoundT]:
    index: dict[str, _EventBoundT] = {}
    for item in items:
        event_id = item.event_id
        if event_id in index:
            raise DiagnosticProjectionError(f"{label} contains invalid event identities")
        index[event_id] = item
    if set(index) != expected:
        raise DiagnosticProjectionError(f"{label} event identities differ from discovery")
    return index


def _reject_cycles(dependencies: dict[str, tuple[str, ...]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(event_id: str) -> None:
        if event_id in visiting:
            raise DiagnosticProjectionError(f"event dependency cycle at {event_id}")
        if event_id in visited:
            return
        visiting.add(event_id)
        for target in dependencies[event_id]:
            visit(target)
        visiting.remove(event_id)
        visited.add(event_id)

    for event_id in sorted(dependencies):
        visit(event_id)


__all__ = [
    "DiagnosticProjection",
    "DiagnosticProjectionError",
    "QuarantinedEvent",
    "project_dependency_closed_subgraph",
]
