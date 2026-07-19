"""V10-only prompt policy without mutating finalized V9 evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from scripts.validation.claim_events.finite_source_unit.service import (
    SourceUnitPromptPolicy,
    canonical_source_unit_extraction_prompt,
    canonical_source_unit_verification_prompt,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimInventoryItem,
    )

    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

V10_EXTRACTION_PROMPT_VERSION: Final = "tg04.finite_source_unit.extraction.v21"
V10_VERIFICATION_PROMPT_VERSION: Final = "tg04.finite_source_unit.verification.v20"

_V9_EXTRACTION_VERSION: Final = "tg04.finite_source_unit.extraction.v20"
_V9_VERIFICATION_VERSION: Final = "tg04.finite_source_unit.verification.v19"

_EXTRACTION_POLICY: Final = """V10 SCIENTIFIC REPRESENTATION POLICY:
- Every controlled target preserves each population, treatment, variant,
  anatomical, and other context that the source scopes to that target. Context
  on the outer controller is not a substitute.
- Scope context event by event. Do not copy an outer exposure or timeframe onto
  a controlled target merely because both appear in one clause. A state modifier
  that defines the population remains part of that population identity unless
  the source independently asserts it as a separate temporal condition.
- When one compound phrase carries several material context types, return
  separate typed arguments even when their verbatim spans overlap. One bundled
  POPULATION or CONTEXT argument is lossy.
- Source-explicit production of named gene or protein products is EXPRESSION
  unless the source explicitly names a different closed event type. Do not use
  OTHER_EXPLICIT merely because the source says "production" instead of
  "expression".
- relation_cue_span is the shortest exact verb or phrase that states the event
  and its material negation. Keep participant lists, populations, and outcome
  thresholds in typed arguments rather than expanding the cue around them."""

_VERIFICATION_POLICY: Final = """V10 SCIENTIFIC REPRESENTATION REVIEW:
- A compound source phrase that carries treatment, variant, population, or
  another material context requires separate typed arguments for each role even
  when the spans overlap. Mark the candidate LOSSY and the inventory
  MISSING_EVENT when those roles survive only inside one bundled argument.
- Source-explicit production of named gene or protein products is EXPRESSION
  unless another closed event type is explicit. Mark OTHER_EXPLICIT invalid for
  that wording.
- A controlled target is incomplete when source-scoped treatment, variant,
  population, anatomical, or other material context appears only on its outer
  event.
- Do not require outer-only exposure or timeframe context on a controlled target.
  Do not split a population-defining state modifier into an invented temporal
  argument unless the source independently gives it that role."""


def v10_source_unit_extraction_prompt(unit: FrozenSourceUnit) -> str:
    """Return the immutable V9 base plus the pre-registered V10 policy."""

    return _upgrade_prompt(
        canonical_source_unit_extraction_prompt(unit),
        previous_version=_V9_EXTRACTION_VERSION,
        next_version=V10_EXTRACTION_PROMPT_VERSION,
        policy=_EXTRACTION_POLICY,
    )


def v10_source_unit_verification_prompt(
    *,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
) -> str:
    """Return the immutable V9 verifier plus V10 categorical hard questions."""

    return _upgrade_prompt(
        canonical_source_unit_verification_prompt(
            unit=unit,
            candidates=candidates,
        ),
        previous_version=_V9_VERIFICATION_VERSION,
        next_version=V10_VERIFICATION_PROMPT_VERSION,
        policy=_VERIFICATION_POLICY,
    )


def _upgrade_prompt(
    prompt: str,
    *,
    previous_version: str,
    next_version: str,
    policy: str,
) -> str:
    marker = f"prompt_version: {previous_version}"
    if prompt.count(marker) != 1:
        raise RuntimeError("historical finite-source prompt identity changed")
    return prompt.replace(marker, f"{policy}\n\nprompt_version: {next_version}")


V10_PROMPT_POLICY: Final = SourceUnitPromptPolicy(
    extraction_version=V10_EXTRACTION_PROMPT_VERSION,
    verification_version=V10_VERIFICATION_PROMPT_VERSION,
    extraction_prompt=v10_source_unit_extraction_prompt,
    verification_prompt=v10_source_unit_verification_prompt,
)


__all__ = [
    "V10_EXTRACTION_PROMPT_VERSION",
    "V10_PROMPT_POLICY",
    "V10_VERIFICATION_PROMPT_VERSION",
    "v10_source_unit_extraction_prompt",
    "v10_source_unit_verification_prompt",
]
