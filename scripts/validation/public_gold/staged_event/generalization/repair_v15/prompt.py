"""Compose and verify the sole V15 provider-facing scientific change."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.repair_v14.prompt import (
    ordered_cases as v14_ordered_cases,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.prompt import (
    provider_input as v14_provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    V15Paths,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )

EXPECTED_RULE = """# V15 Focus Closure and Role-Bearing Occurrence Custody

This rule clarifies two boundaries of the existing focused graph.

1. Focus closure. Construct the mandatory event graph from events denoted by the highlighted finding and the complete focus-internal dependency closure of nested events needed to represent that finding. Follow a dependency inward when a nested event is an argument of a focus-internal event. Do not traverse outward to inventory a predicate outside the highlighted finding merely because it governs, embeds, relates to, or takes the focused event as an argument. A genuinely dependent focus-internal referring expression may resolve under the existing unique-antecedent and ellipsis rules; that resolution does not authorize a neighboring or governing predicate as an event.

2. Occurrence custody. For each participant role, bind the role-bearing source occurrence before minimizing its text. If the highlighted finding contains an explicit self-denoting name, symbol, abbreviation, independently referential lexicalized biomedical identifier, or head-complete nominal bearing that role, bind that exact focus-local occurrence. A definition, synonym, long form, abbreviation expansion, canonical alias, or repeated mention outside the highlighted finding may establish identity but cannot replace the bound occurrence. Only when no independently denoting focus-local occurrence bears the role may a genuinely non-self-denoting pronoun, relative phrase, demonstrative, ellipsis, partitive, or implicit argument resolve to one unique explicit antecedent in the supplied context; ground the participant to that antecedent’s exact occurrence, or fail closed under the existing rules if no unique source-supported resolution exists. Within the bound occurrence, apply the existing complete participant denotation rule unchanged: select the smallest exact contiguous span that independently denotes the participant while retaining its semantic noun head and nonredundant restrictive identity.

Existing source-supported optional contextual participants and optional edges remain permitted only where the frozen rules permit them, and they remain optional; this rule authorizes no new optional context. Optional material cannot add an outside event, compensate for a missing mandatory participant or link, change the root, or change semantic axes, evidence, or completeness.

This rule changes only the outward focus-closure boundary and participant occurrence custody. It does not prescribe or alter event types, entity types, mandatory participants or links, roles, root-selection rules, semantic axes, statistics, evidence grounding, completeness rules, or projection policy.
"""
EXPECTED_RULE_SHA256 = hashlib.sha256(EXPECTED_RULE.encode()).hexdigest()
_CASE_DELIMITER = "\n--- FROZEN EXPOSED CASE ---\n"
_FORBIDDEN_RULE_TERMS = (
    "PMID",
    "HCMV",
    "SLC12A3",
    "immediate-early",
    "5-FU",
    "5-fluorouracil",
    "are involved in",
    "drug sensitivity",
    "BioNLP",
    "gold",
    "reference answer",
)
_FORBIDDEN_PROVIDER_TERMS = (
    '"reference"',
    "acceptable_texts",
    "expected participant",
    "grader policy",
    "focus-closure-consensus",
    "reviewer_id",
)


class V15PromptError(ValueError):
    """The V15 rule or provider packet diverged from its frozen scope."""


def ordered_cases(
    paths: V15Paths = DEFAULT_PATHS,
) -> tuple[GeneralizationCase, ...]:
    """Return the unchanged exposed panel in the preregistered V15 order."""

    cases = v14_ordered_cases(paths.v14)
    if tuple(case.case_id for case in cases) != CASE_ORDER:
        raise V15PromptError("V15 panel or order differs from frozen V14")
    return cases


def verify_rule(paths: V15Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Fail closed if wording, scope, or source-generality changed."""

    actual = paths.focus_occurrence_rule.read_text(encoding="utf-8")
    if actual != EXPECTED_RULE:
        raise V15PromptError("V15 focus-occurrence rule changed")
    forbidden = tuple(term for term in _FORBIDDEN_RULE_TERMS if term in actual)
    if forbidden:
        raise V15PromptError(f"V15 rule contains case-specific terms: {forbidden}")
    return {
        "rule_sha256": EXPECTED_RULE_SHA256,
        "source_general": True,
        "focus_internal_dependency_closure_preserved": True,
        "outward_parent_event_traversal_permitted": False,
        "role_bearing_occurrence_bound_before_minimization": True,
        "true_anaphora_and_ellipsis_preserved": True,
        "v14_complete_participant_denotation_preserved": True,
        "new_optional_context_authorized": False,
        "evaluator_change": False,
        "benchmark_projection_specific": False,
        "case_specific_terms": [],
    }


def provider_input(
    case_id: str,
    paths: V15Paths = DEFAULT_PATHS,
) -> str:
    """Append the sole V15 rule to the exact frozen V11-V14 provider packet."""

    if case_id not in CASE_ORDER:
        raise V15PromptError(f"unknown exposed case: {case_id}")
    verify_rule(paths)
    frozen_v14_packet = v14_provider_input(case_id, paths.v14)
    preserved_prompt, delimiter, frozen_case = frozen_v14_packet.partition(
        _CASE_DELIMITER
    )
    if delimiter != _CASE_DELIMITER or not frozen_case:
        raise V15PromptError("frozen V14 provider packet has no exposed-case boundary")
    value = (
        preserved_prompt
        + "\n--- V15 SINGLE SCIENTIFIC CHANGE ---\n"
        + paths.focus_occurrence_rule.read_text(encoding="utf-8")
        + "--- END V15 SINGLE SCIENTIFIC CHANGE ---\n"
        + delimiter
        + frozen_case
    )
    forbidden = tuple(term for term in _FORBIDDEN_PROVIDER_TERMS if term in value)
    if forbidden:
        raise V15PromptError(f"V15 provider input exposes frozen answers: {forbidden}")
    return value


__all__ = [
    "EXPECTED_RULE",
    "EXPECTED_RULE_SHA256",
    "V15PromptError",
    "ordered_cases",
    "provider_input",
    "verify_rule",
]
