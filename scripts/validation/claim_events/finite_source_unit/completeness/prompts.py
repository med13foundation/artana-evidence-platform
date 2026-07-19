"""Provider-visible prompts for the independent completeness roles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.prompts import (
    V10_VERIFICATION_PROMPT_VERSION,
    v10_source_unit_verification_prompt,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimInventoryItem,
    )

    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

COMPLETENESS_PROMPT_VERSION: Final = (
    "tg04.finite_source_unit.whole_source_inventory.v1"
)
COMPLETENESS_VERIFICATION_PROMPT_VERSION: Final = (
    "tg04.finite_source_unit.whole_source_inventory_verification.v1"
)


def whole_source_completeness_prompt(unit: FrozenSourceUnit) -> str:
    """Build a source-only prompt without proposal or reference information."""

    return f"""You are an independent biomedical whole-source inventory agent.

Use only the frozen source unit below. You have not received another agent's
events. Inventory every distinct source-explicit scientific event needed to
preserve the unit without loss. Do not use outside mechanistic knowledge.

Return exactly one categorical eligibility_category. FINDING, HYPOTHESIS,
NULL_RESULT, and MIXED_SCIENTIFIC require COMPLETE_INVENTORY and at least one
event. PROCEDURE, MEASUREMENT_ONLY, and NO_EVENT require NO_EVENT with no events.
Use ABSTAIN only when the source cannot safely resolve the inventory.

For every event preserve event type, biological direction, claim outcome,
epistemic status, assertion scope, trigger, typed participants, event roles,
and source-explicit context. Keep coordinated participants unless their event
scope, direction, outcome, or epistemic status differs. Represent an explicitly
controlled biological event as a distinct CONTROLLED_TARGET plus a
source-asserted outer regulation event with controlled_event_ref. Never infer a
participant, process, direction, causal role, control level, or context factor.

Use SUPPORT when the source asserts a positive, negative, or direction-neutral
event. Use NULL_RESULT only for an explicit tested no-effect or no-change
result. Use REFUTE only when the source refutes a claim. Biological direction
belongs in event_type, not polarity. Hypothesis and uncertainty belong only in
epistemic_status. Return no score, probability, confidence, rank, or trust tier.

Copy every event span, cue, argument, and evidence span verbatim. Every
source-asserted event needs at least two distinct material arguments. A
CONTROLLED_TARGET may contain fewer when the source names no independent inner
participant. Context dimensions require one explicit factor and at least two
distinct mutually exclusive verbatim levels. Provide concise reasoning and one
condition that would falsify the claimed completeness. Do not return source
identifiers, benchmark labels, transport hashes, or another agent's rationale.

prompt_version: {COMPLETENESS_PROMPT_VERSION}

--- FROZEN SOURCE UNIT ---
{unit.text}
--- END SOURCE UNIT ---
"""


def whole_source_completeness_verification_prompt(
    *,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
) -> str:
    """Upgrade the established source-only verifier for completeness items."""

    prompt = v10_source_unit_verification_prompt(
        unit=unit,
        candidates=candidates,
    )
    marker = f"prompt_version: {V10_VERIFICATION_PROMPT_VERSION}"
    if prompt.count(marker) != 1:
        raise RuntimeError("historical V10 verification prompt identity changed")
    policy = """COMPLETENESS-INVENTORY VERIFICATION POLICY:
- Treat supplied items as untrusted proposals from an independent inventory.
- Judge each item from the frozen source only. Do not use benchmark labels,
  another role's output, or the inventory agent's reasoning.
- Do not discover, repair, rewrite, delete, merge, or split events. Return only
  ordered categorical findings, exact evidence, reasoning, and falsification.
- A quoted source span is not sufficient for ENTAILED when event type,
  direction, outcome, epistemic status, participant typing, event roles, or
  controlled-event topology disagrees with that span.
- Return no numeric score, probability, confidence, rank, or trust tier."""
    return prompt.replace(
        marker,
        f"{policy}\n\nprompt_version: {COMPLETENESS_VERIFICATION_PROMPT_VERSION}",
    )


__all__ = [
    "COMPLETENESS_PROMPT_VERSION",
    "COMPLETENESS_VERIFICATION_PROMPT_VERSION",
    "whole_source_completeness_prompt",
    "whole_source_completeness_verification_prompt",
]
