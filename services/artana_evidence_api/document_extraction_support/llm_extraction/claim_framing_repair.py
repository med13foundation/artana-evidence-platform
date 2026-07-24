"""Bounded one-shot repair contract for participant-completeness failures.

This module is the repair half of the V16 mechanism change. It is deliberately
pure: it builds the repair prompt and decides whether a repaired inventory item
may replace the original, but it never issues a provider call itself. The caller
owns the single bounded provider invocation and its receipt/custody logging.

Repair policy (matches the V16 preregistration):

- Exactly one repair call per incomplete claim.
- The repair prompt carries no answer-shaped hint: it names only the missing
  mandatory roles and points the model back at the frozen source region.
- A repaired item replaces the original only when it passes the same
  deterministic completeness validator and preserves every role that was already
  bound, the event type, and the exact claim span.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from artana_evidence_api.document_extraction_support.claim_frames.event_types import (
    ClaimEventRole,
)
from artana_evidence_api.document_extraction_support.claim_frames.inventory import (
    ClaimInventoryItem,
)
from artana_evidence_api.document_extraction_support.claim_frames.participant_completeness import (
    ParticipantCompletenessDecision,
    ParticipantCompletenessFinding,
    shortest_role_snippet,
    validate_claim_participant_completeness,
)

__all__ = [
    "PARTICIPANT_REPAIR_PROMPT_SUFFIX",
    "ParticipantRepairAcceptance",
    "ParticipantRepairTelemetry",
    "accept_repaired_inventory_item",
    "build_participant_repair_prompt",
]

PARTICIPANT_REPAIR_PROMPT_SUFFIX: Final = "participant_repair.v1"

_REPAIR_INSTRUCTION_HEADER: Final = (
    "PARTICIPANT-COMPLETENESS REPAIR:\n"
    "Your previous inventory of this claim omitted one or more mandatory "
    "participants. Re-read the frozen source region once and re-inventory the "
    "same claim. Bind a source-anchored participant to every missing role listed "
    "below, copying each exact_span verbatim from the source. Preserve every "
    "participant you already bound, and keep the same claim exact_span, "
    "event_type, polarity, and epistemic_status. Do not add a participant that "
    "the source does not state, and do not invent a span."
)


@dataclass(frozen=True, slots=True)
class ParticipantRepairAcceptance:
    """Deterministic decision on whether a repaired item may replace the original."""

    accepted: bool
    reason: str
    still_missing_roles: tuple[ClaimEventRole, ...] = ()


@dataclass(frozen=True, slots=True)
class ParticipantRepairTelemetry:
    """Non-lossy record of one bounded repair attempt for the attempt audit."""

    repair_attempted: bool
    repair_succeeded: bool
    missing_roles_before: tuple[ClaimEventRole, ...]
    missing_roles_after: tuple[ClaimEventRole, ...]
    acceptance_reason: str

    def as_json(self) -> dict[str, object]:
        """Return a JSON-safe telemetry record."""
        return {
            "repair_attempted": self.repair_attempted,
            "repair_succeeded": self.repair_succeeded,
            "missing_roles_before": tuple(
                role.value for role in self.missing_roles_before
            ),
            "missing_roles_after": tuple(
                role.value for role in self.missing_roles_after
            ),
            "acceptance_reason": self.acceptance_reason,
        }


def build_participant_repair_prompt(
    *,
    base_prompt: str,
    finding: ParticipantCompletenessFinding,
    source_text: str,
) -> str:
    """Append a bounded, answer-shape-free repair instruction to a base prompt.

    The instruction names only the missing mandatory roles and reprints a bounded
    verbatim excerpt of the frozen source region. It never names the expected
    participant, its span, or any reference graph shape.
    """

    if finding.decision is ParticipantCompletenessDecision.COMPLETE:
        raise ValueError("a complete finding does not authorize a repair prompt")
    missing = ", ".join(role.value for role in finding.missing_roles)
    snippet = shortest_role_snippet(source_text)
    return (
        f"{base_prompt}\n\n"
        f"{_REPAIR_INSTRUCTION_HEADER}\n"
        f"- missing_mandatory_roles: {missing}\n"
        "---\nFROZEN SOURCE REGION (re-read once)\n---\n"
        f"{snippet}\n"
        "---\n"
    )


def accept_repaired_inventory_item(
    *,
    original: ClaimInventoryItem,
    repaired: ClaimInventoryItem,
    finding: ParticipantCompletenessFinding,
) -> ParticipantRepairAcceptance:
    """Decide whether a repaired inventory item may replace the original.

    Acceptance requires all of:

    - the repaired item is COMPLETE under the same deterministic validator;
    - the repaired item preserves the original claim exact_span and event_type;
    - the repaired item preserves every role the original already bound.

    Any violation fails closed: the original frame is retained and the failure is
    recorded. This guarantees a repair can only add missing mandatory
    participants, never silently rewrite the claim.
    """

    if finding.decision is ParticipantCompletenessDecision.COMPLETE:
        return ParticipantRepairAcceptance(
            accepted=False,
            reason="original_already_complete",
        )
    if repaired.exact_span != original.exact_span:
        return ParticipantRepairAcceptance(
            accepted=False,
            reason="repaired_claim_span_changed",
        )
    if repaired.event_type is not original.event_type:
        return ParticipantRepairAcceptance(
            accepted=False,
            reason="repaired_event_type_changed",
        )
    original_roles = {argument.event_role for argument in original.arguments}
    repaired_roles = {argument.event_role for argument in repaired.arguments}
    dropped = original_roles - repaired_roles
    if dropped:
        return ParticipantRepairAcceptance(
            accepted=False,
            reason="repaired_dropped_bound_role",
        )
    repaired_finding = validate_claim_participant_completeness(repaired)
    if repaired_finding.decision is ParticipantCompletenessDecision.INCOMPLETE:
        return ParticipantRepairAcceptance(
            accepted=False,
            reason="repaired_still_incomplete",
            still_missing_roles=repaired_finding.missing_roles,
        )
    return ParticipantRepairAcceptance(
        accepted=True,
        reason="repaired_complete_and_preserved",
    )
