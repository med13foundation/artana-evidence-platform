"""Deterministic per-claim participant-completeness validation.

This module is the detection half of the V16 mechanism change
(``staged-generalization-v16-exposed-run-v1``). It is deterministic,
source-general, and inventory-only: it never invents participants, never
consults external dictionaries, and never issues a provider call. It reports
whether a source-bound claim inventory item binds every semantic role that is
mandatory for its event type.

The V15 exposed-panel uncertainty failure was classified as a missing mandatory
participant (``SLC12A3``) rather than a missing instruction: the extraction
prompt already required the participant, but the model dropped it under
constraint load. This validator turns that silent drop into an explicit,
machine-checkable ``INCOMPLETE`` decision so a bounded repair can be authorized
by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from artana_evidence_api.document_extraction_support.claim_frames.event_types import (
    ClaimEventRole,
    ClaimEventType,
)
from artana_evidence_api.document_extraction_support.claim_frames.inventory import (
    BoundClaimInventoryItem,
    ClaimInventoryItem,
)

__all__ = [
    "MANDATORY_EVENT_ROLES",
    "ParticipantCompletenessDecision",
    "ParticipantCompletenessFinding",
    "mandatory_event_roles",
    "shortest_role_snippet",
    "validate_claim_participant_completeness",
]

_SNIPPET_MAX_LENGTH: Final = 160


class ParticipantCompletenessDecision(str, Enum):
    """Closed outcome of one deterministic participant-completeness check."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


# Mandatory semantic roles per event type. A role is mandatory when a lossless
# source-local graph for that event cannot be built without at least one
# participant bound to it. The mapping is intentionally conservative: roles that
# are sometimes optional (SITE, CSITE, TOLOC, FROMLOC, ATLOC, MEASURE) are never
# mandatory here, so the validator cannot force the model to invent context that
# the source does not state.
MANDATORY_EVENT_ROLES: Final[dict[ClaimEventType, tuple[ClaimEventRole, ...]]] = {
    ClaimEventType.EXPRESSION: (ClaimEventRole.THEME,),
    ClaimEventType.TRANSCRIPTION: (ClaimEventRole.THEME,),
    ClaimEventType.DEGRADATION: (ClaimEventRole.THEME,),
    ClaimEventType.PHOSPHORYLATION: (ClaimEventRole.THEME,),
    ClaimEventType.LOCALIZATION: (ClaimEventRole.THEME,),
    ClaimEventType.BINDING: (ClaimEventRole.THEME,),
    ClaimEventType.REGULATION: (ClaimEventRole.CAUSE, ClaimEventRole.THEME),
    ClaimEventType.POSITIVE_REGULATION: (ClaimEventRole.CAUSE, ClaimEventRole.THEME),
    ClaimEventType.NEGATIVE_REGULATION: (ClaimEventRole.CAUSE, ClaimEventRole.THEME),
    ClaimEventType.INCREASE: (ClaimEventRole.THEME,),
    ClaimEventType.DECREASE: (ClaimEventRole.THEME,),
    ClaimEventType.ASSOCIATION: (ClaimEventRole.THEME,),
    ClaimEventType.TREATMENT_RESPONSE: (ClaimEventRole.CAUSE, ClaimEventRole.THEME),
    ClaimEventType.NO_EFFECT: (ClaimEventRole.CAUSE, ClaimEventRole.THEME),
    ClaimEventType.OTHER_EXPLICIT: (),
}


@dataclass(frozen=True, slots=True)
class ParticipantCompletenessFinding:
    """Deterministic completeness decision for one source-bound claim."""

    decision: ParticipantCompletenessDecision
    inventory_id: str
    event_type: ClaimEventType
    mandatory_roles: tuple[ClaimEventRole, ...]
    missing_roles: tuple[ClaimEventRole, ...]

    @property
    def is_complete(self) -> bool:
        """Return whether every mandatory role has a bound participant."""
        return self.decision is ParticipantCompletenessDecision.COMPLETE

    def as_json(self) -> dict[str, object]:
        """Return a JSON-safe, non-lossy diagnostic record."""
        return {
            "decision": self.decision.value,
            "inventory_id": self.inventory_id,
            "event_type": self.event_type.value,
            "mandatory_roles": tuple(role.value for role in self.mandatory_roles),
            "missing_roles": tuple(role.value for role in self.missing_roles),
        }


def mandatory_event_roles(event_type: ClaimEventType) -> tuple[ClaimEventRole, ...]:
    """Return the mandatory semantic roles for one event type."""
    return MANDATORY_EVENT_ROLES.get(event_type, ())


def validate_claim_participant_completeness(
    item: ClaimInventoryItem | BoundClaimInventoryItem,
) -> ParticipantCompletenessFinding:
    """Decide whether every mandatory role for the claim is source-bound.

    The check is deterministic and source-general: it compares the event type's
    mandatory roles against the ``event_role`` of each bound argument. It never
    inspects argument content beyond role presence, so it cannot bias the model
    toward any reference answer shape.
    """

    bound_item = item.item if isinstance(item, BoundClaimInventoryItem) else item
    inventory_id = (
        item.inventory_id if isinstance(item, BoundClaimInventoryItem) else ""
    )
    mandatory = mandatory_event_roles(bound_item.event_type)
    bound_roles = {argument.event_role for argument in bound_item.arguments}
    missing = tuple(role for role in mandatory if role not in bound_roles)
    decision = (
        ParticipantCompletenessDecision.COMPLETE
        if not missing
        else ParticipantCompletenessDecision.INCOMPLETE
    )
    return ParticipantCompletenessFinding(
        decision=decision,
        inventory_id=inventory_id,
        event_type=bound_item.event_type,
        mandatory_roles=mandatory,
        missing_roles=missing,
    )


def shortest_role_snippet(source_text: str, *, max_length: int = _SNIPPET_MAX_LENGTH) -> str:
    """Return a bounded source excerpt for use in a repair prompt.

    The snippet is a verbatim prefix of the claim's frozen source region, never
    a paraphrase and never an invented span. It gives the repair model the exact
    text to re-read without leaking any answer-shaped hint.
    """

    if max_length < 1:
        raise ValueError("snippet max_length must be at least 1")
    text = source_text.strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip()
