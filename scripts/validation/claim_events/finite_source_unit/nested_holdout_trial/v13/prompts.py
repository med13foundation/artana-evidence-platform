"""V13-only prompt policy for orthogonal scientific semantic axes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.prompts import (
    V10_EXTRACTION_PROMPT_VERSION,
    V10_VERIFICATION_PROMPT_VERSION,
    v10_source_unit_extraction_prompt,
    v10_source_unit_verification_prompt,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.prompts import (
    V12_NORMALIZATION_PROMPT_VERSION,
    V12_NORMALIZED_REVIEW_PROMPT_VERSION,
    v12_normalization_prompt,
    v12_normalized_review_prompt,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    SourceUnitPromptPolicy,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimInventoryItem,
    )

    from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
        NormalizationPromptBuilder,
        NormalizedReviewPromptBuilder,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.service import (
        SourceUnitNormalizationResult,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        ExtractionPromptBuilder,
        SourceUnitExtractionResult,
        VerificationPromptBuilder,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


class _NormalizationPromptRenderer(Protocol):
    def __call__(
        self,
        *,
        unit: FrozenSourceUnit,
        original: SourceUnitExtractionResult,
        policy: str,
        version: str,
    ) -> str: ...


class _NormalizedReviewPromptRenderer(Protocol):
    def __call__(
        self,
        *,
        unit: FrozenSourceUnit,
        original: SourceUnitExtractionResult,
        normalized: SourceUnitNormalizationResult,
        policy: str,
        version: str,
    ) -> str: ...

V13_EXTRACTION_PROMPT_VERSION: Final = "tg04.finite_source_unit.extraction.v22"
V13_VERIFICATION_PROMPT_VERSION: Final = V10_VERIFICATION_PROMPT_VERSION
V13_NORMALIZATION_PROMPT_VERSION_V4: Final = (
    "tg04.finite_source_unit.structure_normalization.v4"
)
V13_NORMALIZED_REVIEW_PROMPT_VERSION_V4: Final = (
    "tg04.finite_source_unit.normalized_review.v4"
)
V13_NORMALIZATION_PROMPT_VERSION: Final = (
    "tg04.finite_source_unit.structure_normalization.v5"
)
V13_NORMALIZED_REVIEW_PROMPT_VERSION: Final = (
    "tg04.finite_source_unit.normalized_review.v5"
)
V13_NORMALIZATION_PROMPT_VERSION_V6: Final = (
    "tg04.finite_source_unit.structure_normalization.v6"
)
V13_NORMALIZED_REVIEW_PROMPT_VERSION_V6: Final = (
    "tg04.finite_source_unit.normalized_review.v6"
)

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

_CORRECTION_POLICY_V4: Final = """V13 AGENT-AUTHORED SCIENTIFIC CORRECTION POLICY:
- Treat the original extraction as a source-bound proposal, not as scientific
  authority. Re-read the frozen source and independently challenge every event
  type, participant type, event role, claim outcome, epistemic status, and
  assertion scope.
- When an original category contradicts its source wording or its own rationale,
  return the corrected category yourself and mark that mapping REFRAME. The
  deterministic binder will preserve provenance but will never make the change.
- Use GENE_OR_PROTEIN for a source-named gene, gene product, protein, ligand,
  receptor, kinase, transcription factor, enzyme, or cytokine. Do not use
  OTHER_ENTITY merely because the exact biological identity is unfamiliar.
- Standard biomedical entity-class knowledge is allowed only for categorical
  typing. Do not import an unstated mechanism, direction, interaction, or fact.
- Keep every source-explicit coordinated participant and target. Abstain with
  UNRESOLVED_TYPING rather than guessing when the source and standard name class
  do not support one type.
- Return categorical findings, reasoning, exact spans, and a falsification
  condition. Return no numeric score or confidence."""

_CONTROLLED_EVENT_REFERENCE_POLICY_V5: Final = """CONTROLLED-EVENT REFERENCE OWNERSHIP:
- A controlled_event_ref belongs only on a SOURCE_ASSERTED outer regulation
  event's BIOLOGICAL_PROCESS CAUSE or THEME argument. It points outward-to-inner:
  from that process argument to the local_event_id of the distinct
  referenced scientific event represented by the same process span. The
  referenced event may be independently SOURCE_ASSERTED or may be only a
  CONTROLLED_TARGET; reference identity and assertion scope are independent.
- Never point an argument to its owning event's local_event_id. Never place a
  controlled_event_ref on the referenced event's own entity or process
  arguments. Every returned CONTROLLED_TARGET must be referenced by an outer
  controller.
- Generic two-target topology example: an outer event with local_event_id
  regulation-1 has process THEME "Y expression" pointing to expression-1 and
  process THEME "cell death" pointing to death-1. The separate controlled
  events expression-1 and death-1 contain only their own event-local
  participants, all with controlled_event_ref null. The outer arguments never
  point to regulation-1.
- The referenced target must fit the exact outer process span. Do not swap IDs
  between coordinated sibling targets; abstain if the source does not determine
  the correspondence."""

_CORRECTION_POLICY_V5: Final = (
    _CORRECTION_POLICY_V4 + "\n\n" + _CONTROLLED_EVENT_REFERENCE_POLICY_V5
)

_CONTEXT_DIMENSION_ELIGIBILITY_POLICY_V6: Final = """V13 CONTEXT-DIMENSION ELIGIBILITY:
- For each returned context dimension, identify exactly one source-explicit
  experimental factor and at least two distinct, mutually exclusive levels of
  that same factor. The factor span and every level span must each be verbatim
  source text. Otherwise return no dimension for that proposed factor.
- A genotype, treatment, condition, population, or other item already represented
  as an event participant is not automatically an experimental factor. It may
  also be a factor level only when the source explicitly contrasts at least two
  levels of the same factor and scopes an event or outcome across those levels.
  A single causal participant is not a multi-level comparison.
- Never invent, translate, repair, duplicate, or paraphrase a level to satisfy the
  schema's minimum of two levels. If two source-verbatim levels are unavailable,
  return no dimension for that factor. Never infer an unstated untreated,
  wild-type, baseline, placebo, healthy, or other control level.
- Encode explicit parallel-arm dose contrasts as alternative levels only when
  every arm and unit is source-verbatim. Repeated-measures dose or time series and
  overlapping population subgroups are not mutually exclusive alternative levels;
  omit the dimension because this contract has no valid operator for them.
- Do not invent an abstract factor label. If the source names levels such as
  women and men but does not supply a verbatim factor span, omit the dimension.
- Populate crossed_dimension_ids only when the source explicitly states the
  crossing of separately eligible factors; otherwise leave them empty.
- Context dimensions preserve explicit study design only. They must never add a
  mechanism, comparison, participant, or claim that the source does not state."""

_CORRECTION_POLICY_V6: Final = (
    _CORRECTION_POLICY_V5 + "\n\n" + _CONTEXT_DIMENSION_ELIGIBILITY_POLICY_V6
)

_FALSIFICATION_POLICY_V4: Final = """V13 SOURCE-ONLY SCIENTIFIC FALSIFICATION:
- Independently compare every normalized participant type with the frozen source
  wording. Agreement with the correction agent is not evidence.
- A participant category contradicting the source wording or the agent's own
  rationale is a material PARTICIPANTS failure, not a stylistic difference.
- Verify effect direction from event_type, claim outcome from polarity,
  epistemic force from epistemic_status, and standalone status from
  assertion_scope as four independent axes.
- Reject a correction that fixes one category while dropping a coordinated
  target, changing a role, inventing direction, or promoting a controlled target
  into a standalone assertion.
- Return categorical judgments, verbatim evidence, reasoning, and falsification
  conditions only. Return no numeric score or promotion recommendation."""

_FALSIFICATION_TOPOLOGY_POLICY_V5: Final = """V13 CONTROLLED-EVENT TOPOLOGY FALSIFICATION:
- Verify that each outer process argument points to the distinct controlled
  event represented by its own span; reject self-references, orphan controlled
  targets, procedural controllers, non-scientific referenced events, and
  swapped sibling IDs. Do not reject an independently SOURCE_ASSERTED inner
  event merely because it is also referenced by an outer event."""

_FALSIFICATION_POLICY_V5: Final = (
    _FALSIFICATION_POLICY_V4 + "\n\n" + _FALSIFICATION_TOPOLOGY_POLICY_V5
)

_CONTEXT_DIMENSION_FALSIFICATION_POLICY_V6: Final = """V13 CONTEXT-DIMENSION FALSIFICATION:
- Return one context_dimension_review for every proposed dimension, in array
  order, using its exact dimension_id. Categorize factor eligibility, level-set
  validity, event scope, crossing validity, and the final decision; do not reduce
  these questions to aggregate prose.
- Bind each subdecision to separate verbatim evidence: factor_evidence_spans for
  factor identity; one ordered level_review per proposed level with its exact
  level_span and membership category; contrast_evidence_spans covering the
  explicit same-factor comparison; event_scope_evidence_spans covering every
  referenced event; and crossing_evidence_spans covering every declared crossing.
  Missing or conflicting subdecision evidence requires ABSTAIN or UNSUPPORTED,
  never SUPPORTED.
- Independently reject any context dimension unless the frozen source contains
  its explicit factor and at least two distinct, mutually exclusive, verbatim
  levels of that same factor, scoped to the referenced event or outcome.
- Treat a participant promoted into a factor without an explicit source-level
  comparison as a material unsupported addition.
- Reject any invented, translated, repaired, duplicated, or paraphrased factor
  or level span, including implicit control levels and abstract factor labels.
- Reject mixed participants, repeated-measures series, overlapping subgroups, and
  unstated factor crossings as context dimensions under this contract.
- Every unsupported dimension requires unsupported_additions PRESENT and
  CONTEXT_SCOPE MATERIAL_ADDITION. Every unresolved dimension requires
  CONTEXT_SCOPE ABSTAIN. Do not repair or delete a dimension; return categorical
  findings and exact source evidence.
- SUPPORTED preserves a source-only finding for further adjudication; one review
  never authorizes trusted context qualification by itself."""

_FALSIFICATION_POLICY_V6: Final = (
    _FALSIFICATION_POLICY_V5 + "\n\n" + _CONTEXT_DIMENSION_FALSIFICATION_POLICY_V6
)


def v13_source_unit_extraction_prompt(
    unit: FrozenSourceUnit,
    *,
    _base_builder: ExtractionPromptBuilder = v10_source_unit_extraction_prompt,
    _base_version: str = V10_EXTRACTION_PROMPT_VERSION,
    _axis_policy: str = _ORTHOGONAL_AXIS_POLICY,
    _version: str = V13_EXTRACTION_PROMPT_VERSION,
) -> str:
    """Return V10 semantics plus the non-ambiguous V13 axis contract."""

    prompt = _base_builder(unit)
    marker = f"prompt_version: {_base_version}"
    if prompt.count(marker) != 1:
        raise RuntimeError("historical V10 extraction prompt identity changed")
    return prompt.replace(
        marker,
        f"{_axis_policy}\n\nprompt_version: {_version}",
    )


def v13_source_unit_verification_prompt(
    *,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
    _base_builder: VerificationPromptBuilder = v10_source_unit_verification_prompt,
) -> str:
    """Reuse the frozen verifier until a visible extraction canary passes."""

    return _base_builder(unit=unit, candidates=candidates)


def _v13_normalization_prompt(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    policy: str,
    version: str,
    _base_builder: NormalizationPromptBuilder = v12_normalization_prompt,
    _base_version: str = V12_NORMALIZATION_PROMPT_VERSION,
) -> str:
    """Build one explicitly versioned V13 normalization prompt."""

    prompt = _base_builder(unit=unit, original=original)
    marker = f"prompt_version: {_base_version}"
    if prompt.count(marker) != 1:
        raise RuntimeError("historical V12 normalization prompt identity changed")
    return prompt.replace(
        marker,
        f"{policy}\n\nprompt_version: {version}",
    )


def v13_normalization_prompt(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    _renderer: _NormalizationPromptRenderer = _v13_normalization_prompt,
    _policy: str = _CORRECTION_POLICY_V5,
    _version: str = V13_NORMALIZATION_PROMPT_VERSION,
) -> str:
    """Upgrade V12 normalization with source-only agent correction authority."""

    return _renderer(
        unit=unit,
        original=original,
        policy=_policy,
        version=_version,
    )


def v13_normalization_prompt_v4(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
) -> str:
    """Reconstruct the immutable V13-v4 normalization prompt."""

    return _v13_normalization_prompt(
        unit=unit,
        original=original,
        policy=_CORRECTION_POLICY_V4,
        version=V13_NORMALIZATION_PROMPT_VERSION_V4,
    )


def v13_normalization_prompt_v6(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    _renderer: _NormalizationPromptRenderer = _v13_normalization_prompt,
    _policy: str = _CORRECTION_POLICY_V6,
    _version: str = V13_NORMALIZATION_PROMPT_VERSION_V6,
) -> str:
    """Apply the explicit source-level context eligibility boundary."""

    return _renderer(
        unit=unit,
        original=original,
        policy=_policy,
        version=_version,
    )


def _v13_normalized_review_prompt(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    normalized: SourceUnitNormalizationResult,
    policy: str,
    version: str,
    _base_builder: NormalizedReviewPromptBuilder = v12_normalized_review_prompt,
    _base_version: str = V12_NORMALIZED_REVIEW_PROMPT_VERSION,
) -> str:
    """Build one explicitly versioned V13 normalized-review prompt."""

    prompt = _base_builder(
        unit=unit,
        original=original,
        normalized=normalized,
    )
    marker = f"prompt_version: {_base_version}"
    if prompt.count(marker) != 1:
        raise RuntimeError("historical V12 review prompt identity changed")
    return prompt.replace(
        marker,
        f"{policy}\n\nprompt_version: {version}",
    )


def v13_normalized_review_prompt(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    normalized: SourceUnitNormalizationResult,
    _renderer: _NormalizedReviewPromptRenderer = _v13_normalized_review_prompt,
    _policy: str = _FALSIFICATION_POLICY_V5,
    _version: str = V13_NORMALIZED_REVIEW_PROMPT_VERSION,
) -> str:
    """Upgrade V12 review with independent entity-type falsification."""

    return _renderer(
        unit=unit,
        original=original,
        normalized=normalized,
        policy=_policy,
        version=_version,
    )


def v13_normalized_review_prompt_v4(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    normalized: SourceUnitNormalizationResult,
) -> str:
    """Reconstruct the immutable V13-v4 normalized-review prompt."""

    return _v13_normalized_review_prompt(
        unit=unit,
        original=original,
        normalized=normalized,
        policy=_FALSIFICATION_POLICY_V4,
        version=V13_NORMALIZED_REVIEW_PROMPT_VERSION_V4,
    )


def v13_normalized_review_prompt_v6(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    normalized: SourceUnitNormalizationResult,
    _renderer: _NormalizedReviewPromptRenderer = _v13_normalized_review_prompt,
    _policy: str = _FALSIFICATION_POLICY_V6,
    _version: str = V13_NORMALIZED_REVIEW_PROMPT_VERSION_V6,
) -> str:
    """Falsify context eligibility independently from normalization."""

    return _renderer(
        unit=unit,
        original=original,
        normalized=normalized,
        policy=_policy,
        version=_version,
    )


V13_PROMPT_POLICY: Final = SourceUnitPromptPolicy(
    extraction_version=V13_EXTRACTION_PROMPT_VERSION,
    verification_version=V13_VERIFICATION_PROMPT_VERSION,
    extraction_prompt=v13_source_unit_extraction_prompt,
    verification_prompt=v13_source_unit_verification_prompt,
)


__all__ = [
    "V13_EXTRACTION_PROMPT_VERSION",
    "V13_NORMALIZATION_PROMPT_VERSION",
    "V13_NORMALIZATION_PROMPT_VERSION_V4",
    "V13_NORMALIZATION_PROMPT_VERSION_V6",
    "V13_NORMALIZED_REVIEW_PROMPT_VERSION",
    "V13_NORMALIZED_REVIEW_PROMPT_VERSION_V4",
    "V13_NORMALIZED_REVIEW_PROMPT_VERSION_V6",
    "V13_PROMPT_POLICY",
    "V13_VERIFICATION_PROMPT_VERSION",
    "v13_source_unit_extraction_prompt",
    "v13_normalization_prompt",
    "v13_normalization_prompt_v4",
    "v13_normalization_prompt_v6",
    "v13_normalized_review_prompt",
    "v13_normalized_review_prompt_v4",
    "v13_normalized_review_prompt_v6",
    "v13_source_unit_verification_prompt",
]
