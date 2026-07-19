"""Frozen blinded prompts for the V12 three-agent diagnostic."""

from __future__ import annotations

import json
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
    from scripts.validation.claim_events.finite_source_unit.normalization.service import (
        SourceUnitNormalizationResult,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        SourceUnitExtractionResult,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

V12_EXTRACTION_PROMPT_VERSION: Final = V10_EXTRACTION_PROMPT_VERSION
V12_NORMALIZATION_PROMPT_VERSION: Final = (
    "tg04.finite_source_unit.structure_normalization.v3"
)
V12_NORMALIZED_REVIEW_PROMPT_VERSION: Final = (
    "tg04.finite_source_unit.normalized_review.v3"
)


def v12_source_unit_extraction_prompt(unit: FrozenSourceUnit) -> str:
    """Reuse the exact V10 extractor so V12 isolates downstream decomposition."""

    return v10_source_unit_extraction_prompt(unit)


def v12_normalization_prompt(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
) -> str:
    """Ask a second agent for one lossless production representation."""

    original_payload = original.output.model_dump(mode="json")
    binding_failures = [
        {
            "source_event_position": rejection.batch_index,
            "disposition": rejection.disposition.value,
            "validation_evidence": rejection.validation_evidence,
        }
        for rejection in original.rejected
    ]
    return f"""You are the role-separated structure-normalization agent in a sealed
biomedical diagnostic. Use only the frozen source and original extraction below.
You cannot see expert gold, expected projection IDs, prior scores, or promotion
decisions.

Choose exactly one family:
- DIRECT: one or more complete source-asserted events, with no controlled targets
  or controlled_event_ref values.
- NESTED: explicit controller events plus separately represented controlled
  targets, connected with controlled_event_ref.
- ABSTAIN: no events when neither family can preserve the source without guessing.

Return every normalized event yourself. Deterministic code will bind spans and
links, but it will not add participants, change types, repair polarity, or infer
scientific meaning. Preserve the original extraction; do not overwrite it.

For each normalized event, map its zero-based normalized_event_position to every
zero-based source_event_position it represents and choose UNCHANGED, REFRAME,
SPLIT, or MERGE. Cover every original event. Repeated use of one source position
is permitted only for SPLIT. MERGE requires multiple source positions. Use
UNCHANGED only for byte-equivalent structured content. Adding or changing a
local_event_id is a REFRAME even when every scientific field is unchanged.

Hard requirements:
- Give every normalized event a nonempty, unique local_event_id beginning with a
  letter and containing only letters, digits, hyphens, or underscores. Author
  these IDs yourself. Deterministic code will not create, rename, or repair them.
- Every controlled_event_ref and every context-dimension event reference must
  exactly equal one returned local_event_id. Never use an array position such as
  "0" as an event reference unless that exact string is a valid returned ID.
- Preserve every explicit agent, target, outcome, population, genotype or
  variant, intervention, condition, direction, polarity, and assertion scope.
- Treat coordinated clauses and coordinated objects as a completeness test:
  preserve each material participant, process, and outcome even when the
  original extraction or an external corpus annotation represents only one.
  A source-explicit coordinated sibling is not an unsupported addition.
- Do not convert experimental exposure or context into realized causation.
- Do not mix DIRECT and NESTED fragments.
- Preserve source-distinct participants, outcomes, processes, and events as
  distinct structured fields; do not collapse one into another.
- Represent source-explicit mutually exclusive factor levels in
  context_dimensions. When factors are crossed, link both dimensions
  symmetrically. Do not flatten alternative experimental arms into one
  simultaneous bag of event contexts.
- Copy all source spans verbatim and supply mention anchors for repeated spans.
- Return categorical findings, reasoning, and a falsification condition. Return
  no confidence, score, probability, or numeric quality grade.

prompt_version: {V12_NORMALIZATION_PROMPT_VERSION}

--- FROZEN SOURCE UNIT ---
{unit.text}
--- END SOURCE UNIT ---

--- ORIGINAL EXTRACTION ---
{_json(original_payload)}
--- END ORIGINAL EXTRACTION ---

--- DETERMINISTIC BINDING FAILURES ---
{_json(binding_failures)}
--- END BINDING FAILURES ---
"""


def v12_normalized_review_prompt(
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    normalized: SourceUnitNormalizationResult,
) -> str:
    """Ask a third agent to challenge source meaning and normalization fidelity."""

    original_structure = {
        "eligibility_category": original.output.eligibility_category.value,
        "events": [event.model_dump(mode="json") for event in original.output.events],
        "binding_failures": [
            {
                "source_event_position": rejection.batch_index,
                "disposition": rejection.disposition.value,
            }
            for rejection in original.rejected
        ],
    }
    normalized_structure = {
        "eligibility_category": normalized.output.eligibility_category.value,
        "family": normalized.output.family.value,
        "events": [event.model_dump(mode="json") for event in normalized.output.events],
        "mappings": [
            {
                "normalized_event_position": mapping.normalized_event_position,
                "source_event_positions": mapping.source_event_positions,
                "operation": mapping.operation.value,
            }
            for mapping in normalized.output.mappings
        ],
        "context_dimensions": [
            {
                "dimension_id": dimension.dimension_id,
                "dimension_type": dimension.dimension_type.value,
                "operator": dimension.operator.value,
                "factor_span": dimension.factor_span,
                "level_spans": dimension.level_spans,
                "applies_to_local_event_ids": (dimension.applies_to_local_event_ids),
                "crossed_dimension_ids": dimension.crossed_dimension_ids,
            }
            for dimension in normalized.output.context_dimensions
        ],
    }
    return f"""You are the role-separated adversarial biomedical reviewer in a sealed
diagnostic. Use only the source, original structure, and normalized structure.
You cannot see expert gold, benchmark projection IDs, prior agent reasoning,
numeric scores, or promotion decisions.

Return one categorical review for every material axis in exactly this order:
EVENT_INVENTORY, EVENT_TYPE, DIRECTION, POLARITY, PARTICIPANTS, CAUSAL_ROLES,
CONTEXT_SCOPE, ASSERTION_EPISTEMIC_SCOPE, CONTROLLED_EVENT_TOPOLOGY,
REFERENT_RESOLUTION.

For each axis choose PRESERVED, COMPATIBLE_REFINEMENT, MATERIAL_LOSS,
MATERIAL_ADDITION, CONTRADICTION, NOT_APPLICABLE, or ABSTAIN. Separately classify
cue wording as EXACT, SURFACE_EQUIVALENT, MATERIAL_MISMATCH, or ABSTAIN. Review
every normalized event in order as ENTAILED, CONTRADICTED, INSUFFICIENT, or
ABSTAIN, with verbatim source evidence.

Answer these hard questions in your categorical decisions and reasoning:
1. Is every original event represented and every normalized event source-entailed?
   Independently re-read the source for coordinated events or targets omitted
   from both structures; agreement between the first two agents is not proof of
   whole-source completeness.
2. Was direction or null-result polarity changed?
3. Was exposure or experimental context incorrectly converted into causation?
4. Are source-distinct participants, coordinated outcomes, processes, and roles
   preserved? Does every returned local_event_id exist, remain unique, and own
   the references that point to it?
5. Is each population, variant, intervention, and condition scoped correctly?
   Are mutually exclusive levels and crossed factors explicit rather than
   flattened into simultaneous context?
6. Does nested output preserve controller versus controlled-target assertion scope?
7. Were referents invented, omitted, or attached to the wrong event?
8. Does cue variation preserve predicate, direction, and negation scope?
9. Did normalization mix DIRECT and NESTED fragments?
10. What exact source change would falsify each decisive answer?

Return no confidence, score, probability, aggregate grade, GO decision, or
promotion recommendation. Deterministic code calculates all metrics.

prompt_version: {V12_NORMALIZED_REVIEW_PROMPT_VERSION}

--- FROZEN SOURCE UNIT ---
{unit.text}
--- END SOURCE UNIT ---

--- ORIGINAL STRUCTURE ---
{_json(original_structure)}
--- END ORIGINAL STRUCTURE ---

--- NORMALIZED STRUCTURE ---
{_json(normalized_structure)}
--- END NORMALIZED STRUCTURE ---
"""


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


V12_EXTRACTION_PROMPT_POLICY: Final = SourceUnitPromptPolicy(
    extraction_version=V12_EXTRACTION_PROMPT_VERSION,
    verification_version=V10_VERIFICATION_PROMPT_VERSION,
    extraction_prompt=v12_source_unit_extraction_prompt,
    verification_prompt=v10_source_unit_verification_prompt,
)


__all__ = [
    "V12_EXTRACTION_PROMPT_VERSION",
    "V12_EXTRACTION_PROMPT_POLICY",
    "V12_NORMALIZATION_PROMPT_VERSION",
    "V12_NORMALIZED_REVIEW_PROMPT_VERSION",
    "v12_normalization_prompt",
    "v12_normalized_review_prompt",
    "v12_source_unit_extraction_prompt",
]
