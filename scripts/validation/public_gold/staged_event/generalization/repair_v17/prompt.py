"""Compose and verify V17's inline-versus-anaphoric scope correction."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.repair_v15.prompt import (
    ordered_cases as v15_ordered_cases,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.prompt import (
    provider_input as v15_provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    V17Paths,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )


EXPECTED_RULE = """# V17 Inline Participant Spans and Anaphoric Scope

This rule resolves only the boundary between a complete role-bearing participant
span and a separately represented source scope. It does not authorize new
events, participant types, event arguments, event links, or source claims.

- First bind the smallest complete participant span that bears the event role.
  Retain its noun head and every restrictive modifier needed to identify that
  participant. A restrictive modifier already retained inside that complete
  role-bearing span is represented by the parent participant itself. Do not
  split that inline modifier into another participant or a
  `participant_scope_links` item merely to restate information already present
  in the parent span.
- Preserve the existing separately represented scope only when an explicit
  restriction is needed to resolve a downstream anaphoric aggregate or partitive
  whose antecedent is an existing event argument and the restriction is not
  already retained in that argument's complete role-bearing span. In that
  setting, use the existing participant-scope link and attach an explicit
  `MAJORITY` partitive only when the source states one. The scope link preserves
  identity; it is not an event argument and cannot replace the antecedent's
  ordinary event argument.
- Never remove a restrictive modifier from the complete parent span in order to
  create a separate scope participant. Do not infer a separate scope, a
  partitive, or a new direct event argument from surrounding context alone.

This rule is additive to the frozen occurrence, focus, and source-grounding
rules. It changes only whether an already-retained inline modifier is
redundantly decomposed. It does not change event inventory, entity types,
mandatory event arguments, root selection, semantic axes, evidence grounding,
completeness, historical graders, or BioNLP-CG projection policy.
"""
EXPECTED_RULE_SHA256 = hashlib.sha256(EXPECTED_RULE.encode()).hexdigest()
_CASE_DELIMITER = "\n--- FROZEN EXPOSED CASE ---\n"
_FORBIDDEN_RULE_TERMS = (
    "PMID",
    "HCMV",
    "SLC12A3",
    "947 variants",
    "5-FU",
    "RA",
    "gold",
    "reference answer",
)
_FORBIDDEN_PROVIDER_TERMS = (
    '"reference"',
    "acceptable_texts",
    "expected participant",
    "grader policy",
    "source-scope-tiebreak",
    "reviewer_id",
)


class V17PromptError(ValueError):
    """The V17 rule or provider packet diverged from its frozen boundary."""


def ordered_cases(
    paths: V17Paths = DEFAULT_PATHS,
) -> tuple[GeneralizationCase, ...]:
    """Return the unchanged exposed panel in the preregistered V17 order."""

    cases = v15_ordered_cases(paths.v16.v15)
    if tuple(case.case_id for case in cases) != CASE_ORDER:
        raise V17PromptError("V17 panel or order differs from sealed V15")
    return cases


def verify_rule(paths: V17Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Fail closed if V17 wording or its deliberately narrow scope changes."""

    actual = paths.inline_scope_rule.read_text(encoding="utf-8")
    if actual != EXPECTED_RULE:
        raise V17PromptError("V17 inline-scope rule changed")
    forbidden = tuple(term for term in _FORBIDDEN_RULE_TERMS if term in actual)
    if forbidden:
        raise V17PromptError(f"V17 rule contains case-specific terms: {forbidden}")
    return {
        "rule_sha256": EXPECTED_RULE_SHA256,
        "source_general": True,
        "inline_restrictive_modifier_decomposition_permitted": False,
        "complete_parent_span_preserved": True,
        "anaphoric_scope_and_majority_path_preserved": True,
        "event_inventory_changed": False,
        "entity_types_changed": False,
        "mandatory_event_arguments_changed": False,
        "new_schema_introduced": False,
        "benchmark_projection_specific": False,
        "case_specific_terms": [],
    }


def provider_input(
    case_id: str,
    paths: V17Paths = DEFAULT_PATHS,
) -> str:
    """Append the sole V17 rule to the exact sealed V15 provider packet."""

    if case_id not in CASE_ORDER:
        raise V17PromptError(f"unknown exposed case: {case_id}")
    verify_rule(paths)
    frozen_v15_packet = v15_provider_input(case_id, paths.v16.v15)
    preserved_prompt, delimiter, frozen_case = frozen_v15_packet.partition(
        _CASE_DELIMITER
    )
    if delimiter != _CASE_DELIMITER or not frozen_case:
        raise V17PromptError("sealed V15 packet has no exposed-case boundary")
    value = (
        preserved_prompt
        + "\n--- V17 SINGLE SCIENTIFIC CHANGE ---\n"
        + paths.inline_scope_rule.read_text(encoding="utf-8")
        + "--- END V17 SINGLE SCIENTIFIC CHANGE ---\n"
        + delimiter
        + frozen_case
    )
    forbidden = tuple(term for term in _FORBIDDEN_PROVIDER_TERMS if term in value)
    if forbidden:
        raise V17PromptError(f"V17 provider input exposes frozen answers: {forbidden}")
    return value


__all__ = [
    "EXPECTED_RULE",
    "EXPECTED_RULE_SHA256",
    "V17PromptError",
    "ordered_cases",
    "provider_input",
    "verify_rule",
]
