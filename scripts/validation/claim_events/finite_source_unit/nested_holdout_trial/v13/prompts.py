"""V13-only prompt policy for orthogonal scientific semantic axes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.prompts import (
    V10_EXTRACTION_PROMPT_VERSION,
    V10_VERIFICATION_PROMPT_VERSION,
    v10_source_unit_extraction_prompt,
    v10_source_unit_verification_prompt,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    SourceUnitPromptPolicy,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimInventoryItem,
    )

    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

V13_EXTRACTION_PROMPT_VERSION: Final = "tg04.finite_source_unit.extraction.v22"
V13_VERIFICATION_PROMPT_VERSION: Final = V10_VERIFICATION_PROMPT_VERSION

_ORTHOGONAL_AXIS_POLICY: Final = """V13 ORTHOGONAL SEMANTIC-AXIS POLICY:
- event_type alone records source-explicit biological effect direction.
  POSITIVE_REGULATION and INCREASE are positive; NEGATIVE_REGULATION and
  DECREASE are negative; REGULATION is direction-neutral. Never use polarity to
  record whether biological direction is positive, negative, or unspecified.
- polarity is the legacy wire name for claim outcome only. Use SUPPORT whenever
  the source asserts an event or relationship, including direction-neutral
  REGULATION. Use REFUTE only for an explicit refutation and NULL_RESULT only
  for a tested no-effect, no-association, or threshold-failing result.
- epistemic_status alone records how strongly the source presents the claim.
  A positive-direction hypothesis is polarity SUPPORT plus epistemic_status
  HYPOTHESIS. Never put hypothesis or uncertainty into polarity.
- assertion_scope alone records standalone assertion status. Use UNSCOPED
  polarity and UNASSERTED epistemic_status only for CONTROLLED_TARGET. A
  SOURCE_ASSERTED event must never use either structural non-assertion value.
- Keep all four axes categorical and independent. Do not return numeric scores.

Canonical examples:
- "X regulates Y" -> event_type REGULATION, polarity SUPPORT,
  epistemic_status ASSERTED, assertion_scope SOURCE_ASSERTED.
- "X may increase Y" -> event_type INCREASE, polarity SUPPORT,
  epistemic_status HYPOTHESIS or UNCERTAIN according to the source,
  assertion_scope SOURCE_ASSERTED.
- a named inner process that exists only as the target of an outer controller ->
  its source-explicit event_type, polarity UNSCOPED, epistemic_status UNASSERTED,
  assertion_scope CONTROLLED_TARGET."""


def v13_source_unit_extraction_prompt(unit: FrozenSourceUnit) -> str:
    """Return V10 semantics plus the non-ambiguous V13 axis contract."""

    prompt = v10_source_unit_extraction_prompt(unit)
    marker = f"prompt_version: {V10_EXTRACTION_PROMPT_VERSION}"
    if prompt.count(marker) != 1:
        raise RuntimeError("historical V10 extraction prompt identity changed")
    return prompt.replace(
        marker,
        f"{_ORTHOGONAL_AXIS_POLICY}\n\nprompt_version: "
        f"{V13_EXTRACTION_PROMPT_VERSION}",
    )


def v13_source_unit_verification_prompt(
    *,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
) -> str:
    """Reuse the frozen verifier until a visible extraction canary passes."""

    return v10_source_unit_verification_prompt(unit=unit, candidates=candidates)


V13_PROMPT_POLICY: Final = SourceUnitPromptPolicy(
    extraction_version=V13_EXTRACTION_PROMPT_VERSION,
    verification_version=V13_VERIFICATION_PROMPT_VERSION,
    extraction_prompt=v13_source_unit_extraction_prompt,
    verification_prompt=v13_source_unit_verification_prompt,
)


__all__ = [
    "V13_EXTRACTION_PROMPT_VERSION",
    "V13_PROMPT_POLICY",
    "V13_VERIFICATION_PROMPT_VERSION",
    "v13_source_unit_extraction_prompt",
    "v13_source_unit_verification_prompt",
]
