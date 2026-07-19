"""V14 prompts separating scientific judgments from procedural derivation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13.prompts import (
    V13_EXTRACTION_PROMPT_VERSION,
    V13_NORMALIZATION_PROMPT_VERSION_V6,
    V13_NORMALIZED_REVIEW_PROMPT_VERSION_V6,
    V13_PROMPT_POLICY,
    v13_normalization_prompt_v6,
    v13_normalized_review_prompt_v6,
    v13_source_unit_extraction_prompt,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    SourceUnitPromptPolicy,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.normalization.service import (
        SourceUnitNormalizationResult,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        SourceUnitExtractionResult,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

V14_EXTRACTION_PROMPT_VERSION: Final = "tg04.finite_source_unit.extraction.v23"
V14_NORMALIZATION_PROMPT_VERSION: Final = (
    "tg04.finite_source_unit.structure_normalization.v14.1"
)
V14_NORMALIZED_REVIEW_PROMPT_VERSION: Final = (
    "tg04.finite_source_unit.normalized_review.v14.1"
)

_OLD_MAPPING_POLICY: Final = """For each normalized event, map its zero-based normalized_event_position to every
zero-based source_event_position it represents and choose UNCHANGED, REFRAME,
SPLIT, or MERGE. Cover every original event. Repeated use of one source position
is permitted only for SPLIT. MERGE requires multiple source positions. Use
UNCHANGED only for byte-equivalent structured content. Adding or changing a
local_event_id is a REFRAME even when every scientific field is unchanged."""

_V14_MAPPING_POLICY: Final = """For each normalized event, map its zero-based normalized_event_position to every
zero-based source_event_position it represents. Cover every original event. Do
not return UNCHANGED, REFRAME, SPLIT, MERGE, or any other operation label.
Deterministic code derives that procedural label from mapping cardinality and
canonical representation equality. You still decide every scientific event and
source correspondence; code will not add, remove, merge, split, or rewrite one."""

_OLD_CORRECTION_SENTENCE: Final = (
    "return the corrected category yourself and mark that mapping REFRAME. The\n"
    "  deterministic binder will preserve provenance but will never make the change."
)
_V14_CORRECTION_SENTENCE: Final = (
    "return the corrected category yourself. Deterministic code will classify the\n"
    "  resulting representation change but will never make the scientific change."
)

_OLD_ANCHOR_POLICY: Final = (
    "- Copy all source spans verbatim and supply mention anchors for repeated spans."
)
_V14_ANCHOR_POLICY: Final = """- Copy every source span verbatim. Each event exact_span must be one contiguous
  source span containing its relation cue and every literal argument mention used
  by that event. When a later coordinated clause elides a shared participant,
  extend exact_span back to the participant's one literal source mention; never
  invent a repeated local occurrence near the later clause.
- A mention anchor describes a literal occurrence, never an implied repetition.
  Leave mention_anchors empty when the argument span occurs exactly once inside
  the event exact_span. When it occurs more than once inside that event span,
  return source-verbatim left and right context that identifies exactly one
  occurrence.
- For a true anaphor such as "their", keep the anaphor as the argument exact_span
  and use source-verbatim referent_anchors to identify its antecedent. Never replace
  an anaphor's textual mention with the antecedent's name."""

_V14_REVIEW_POLICY: Final = """V14 DETERMINISTIC-MAPPING AND LITERAL-ANCHOR FALSIFICATION:
- Mapping operations shown in the normalized structure were computed from mapping
  cardinality and canonical equality. They are provenance, not agent judgments.
  Never treat REFRAME frequency as scientific loss, quality, or confidence.
- Verify that each event exact_span is contiguous source text containing its cue
  and every literal argument mention. A coordinated clause with an elided shared
  participant must extend its event span to the one literal participant mention;
  it must not invent a repeated local occurrence.
- Verify that every mention anchor describes a literal occurrence of its exact
  span inside the event span. A unique in-event occurrence should have no anchor;
  a repeated in-event occurrence needs verbatim context selecting exactly one.
- Keep participant semantics, anaphoric mentions, and referent locations separate.
  Reject invented mentions, but preserve valid source-verbatim referent anchors.
- Return categorical judgments, exact evidence, reasoning, and falsification only.
  Return no score, probability, confidence, or promotion decision."""

_V14_EXTRACTION_POLICY: Final = """V14 LITERAL-MENTION AND REFERENT POLICY:
- Each event exact_span must be one contiguous source span containing its relation
  cue and every literal argument mention used by that event. For a coordinated
  clause with an elided shared participant, extend the event span back to that
  participant's one literal mention; never invent a repeated local occurrence.
- mention_anchors only disambiguate repeated literal occurrences of the argument
  exact_span. Every mention_anchor.mention_span must equal that exact_span. Leave
  mention_anchors empty when the exact span occurs once inside the event span.
- Keep an anaphor such as "their" or "it" as the argument exact_span and use
  source-verbatim referent_anchors for its antecedent. Do not put aliases,
  antecedents, or different entities in mention_anchors.
- Return categorical claims, exact evidence, reasoning, and falsification only;
  never return a score, probability, confidence, or promotion decision."""


def v14_source_unit_extraction_prompt(
    unit: FrozenSourceUnit,
    *,
    _base_builder=v13_source_unit_extraction_prompt,
    _base_version: str = V13_EXTRACTION_PROMPT_VERSION,
    _version: str = V14_EXTRACTION_PROMPT_VERSION,
    _policy: str = _V14_EXTRACTION_POLICY,
) -> str:
    """Add literal occurrence custody to primary scientific extraction."""

    prompt = _base_builder(unit)
    marker = f"prompt_version: {_base_version}"
    if prompt.count(marker) != 1:
        raise RuntimeError("historical V13 extraction prompt identity changed")
    return prompt.replace(marker, f"{_policy}\n\nprompt_version: {_version}")


def v14_normalization_prompt(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    _base_builder=v13_normalization_prompt_v6,
    _base_version: str = V13_NORMALIZATION_PROMPT_VERSION_V6,
    _version: str = V14_NORMALIZATION_PROMPT_VERSION,
) -> str:
    """Remove procedural labels and bind literal occurrence semantics."""

    prompt = _base_builder(unit=unit, original=original)
    replacements = (
        (_OLD_MAPPING_POLICY, _V14_MAPPING_POLICY),
        (_OLD_CORRECTION_SENTENCE, _V14_CORRECTION_SENTENCE),
        (_OLD_ANCHOR_POLICY, _V14_ANCHOR_POLICY),
        (f"prompt_version: {_base_version}", f"prompt_version: {_version}"),
    )
    for old, new in replacements:
        if prompt.count(old) != 1:
            raise RuntimeError("historical V13 normalization prompt identity changed")
        prompt = prompt.replace(old, new)
    return prompt


def v14_normalized_review_prompt(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    normalized: SourceUnitNormalizationResult,
    _base_builder=v13_normalized_review_prompt_v6,
    _base_version: str = V13_NORMALIZED_REVIEW_PROMPT_VERSION_V6,
    _version: str = V14_NORMALIZED_REVIEW_PROMPT_VERSION,
    _policy: str = _V14_REVIEW_POLICY,
) -> str:
    """Review scientific fidelity independently of derived operation labels."""

    prompt = _base_builder(
        unit=unit,
        original=original,
        normalized=normalized,
    )
    marker = f"prompt_version: {_base_version}"
    if prompt.count(marker) != 1:
        raise RuntimeError("historical V13 review prompt identity changed")
    return prompt.replace(marker, f"{_policy}\n\nprompt_version: {_version}")


V14_PROMPT_POLICY: Final = SourceUnitPromptPolicy(
    extraction_version=V14_EXTRACTION_PROMPT_VERSION,
    verification_version=V13_PROMPT_POLICY.verification_version,
    extraction_prompt=v14_source_unit_extraction_prompt,
    verification_prompt=V13_PROMPT_POLICY.verification_prompt,
)


__all__ = [
    "V14_EXTRACTION_PROMPT_VERSION",
    "V14_NORMALIZATION_PROMPT_VERSION",
    "V14_NORMALIZED_REVIEW_PROMPT_VERSION",
    "V14_PROMPT_POLICY",
    "v14_source_unit_extraction_prompt",
    "v14_normalization_prompt",
    "v14_normalized_review_prompt",
]
