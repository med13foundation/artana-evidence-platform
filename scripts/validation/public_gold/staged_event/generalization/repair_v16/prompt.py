"""Compose and verify the sole V16 provider-facing scientific change."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.repair_v15.prompt import (
    ordered_cases as v15_ordered_cases,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.prompt import (
    provider_input as v15_provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    V16Paths,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )

EXPECTED_RULE = """# V16 Participant Scope and Partitive Meaning

This rule adds a source-semantic representation for a condition that narrows a
participant set used by a focused event. It does not authorize additional
events, participants, event arguments, or source claims.

- When a named participant restricts the identity or scientific scope of a
  participant set used by a focused event, emit both participant nodes and one
  `participant_scope_links` item from the restricted set to its restrictor with
  relation type `IDENTITY_OR_SCOPE_RESTRICTION`. Ground the link to the complete
  source sentence that expresses the restriction.
- When an existing event argument denotes a stated partitive subset of its
  participant set, retain the ordinary argument and attach `partitive_scope` to
  that argument. Use kind `MAJORITY` only for an explicit majority expression,
  copy its exact text and complete evidence sentence, and bind its antecedent to
  the same participant target as the argument.
- A scope link preserves participant identity; it is not a new event argument.
  Do not add a direct event-to-restrictor argument merely to restate the scope.
  If such a direct argument is independently explicit in the source, retain it
  only under the existing role and occurrence rules.
- Bind every scope participant to its exact source occurrence before minimizing
  its text. The existing complete-participant-denotation rule remains unchanged:
  an independently referential lexicalized biomedical identifier may omit an
  adjacent generic entity-type word, but the complete evidence sentence must
  still anchor the source occurrence.
- Use empty `participant_scope_links` and no `partitive_scope` when the focused
  finding contains no source-stated scope or partitive condition. Never infer a
  restriction or a majority from surrounding context alone.

This rule changes only the representation of explicit participant scope and
partitive meaning. It does not change event inventory, entity types, mandatory
event arguments, root selection, semantic axes, evidence grounding,
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


class V16PromptError(ValueError):
    """The V16 rule or provider packet diverged from its frozen scope."""


def ordered_cases(
    paths: V16Paths = DEFAULT_PATHS,
) -> tuple[GeneralizationCase, ...]:
    """Return the unchanged exposed panel in the preregistered V16 order."""

    cases = v15_ordered_cases(paths.v15)
    if tuple(case.case_id for case in cases) != CASE_ORDER:
        raise V16PromptError("V16 panel or order differs from sealed V15")
    return cases


def verify_rule(paths: V16Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Fail closed if wording, scope, or source-generality changed."""

    actual = paths.scope_rule.read_text(encoding="utf-8")
    if actual != EXPECTED_RULE:
        raise V16PromptError("V16 participant-scope rule changed")
    forbidden = tuple(term for term in _FORBIDDEN_RULE_TERMS if term in actual)
    if forbidden:
        raise V16PromptError(f"V16 rule contains case-specific terms: {forbidden}")
    return {
        "rule_sha256": EXPECTED_RULE_SHA256,
        "source_general": True,
        "participant_scope_link_added": True,
        "partitive_scope_added": True,
        "event_inventory_changed": False,
        "mandatory_event_arguments_changed": False,
        "v14_identifier_rule_preserved": True,
        "direct_scope_restatement_required": False,
        "benchmark_projection_specific": False,
        "case_specific_terms": [],
    }


def provider_input(
    case_id: str,
    paths: V16Paths = DEFAULT_PATHS,
) -> str:
    """Append the sole V16 rule to the exact frozen V11-V15 provider packet."""

    if case_id not in CASE_ORDER:
        raise V16PromptError(f"unknown exposed case: {case_id}")
    verify_rule(paths)
    frozen_v15_packet = v15_provider_input(case_id, paths.v15)
    preserved_prompt, delimiter, frozen_case = frozen_v15_packet.partition(
        _CASE_DELIMITER
    )
    if delimiter != _CASE_DELIMITER or not frozen_case:
        raise V16PromptError("sealed V15 packet has no exposed-case boundary")
    value = (
        preserved_prompt
        + "\n--- V16 SINGLE SCIENTIFIC CHANGE ---\n"
        + paths.scope_rule.read_text(encoding="utf-8")
        + "--- END V16 SINGLE SCIENTIFIC CHANGE ---\n"
        + delimiter
        + frozen_case
    )
    forbidden = tuple(term for term in _FORBIDDEN_PROVIDER_TERMS if term in value)
    if forbidden:
        raise V16PromptError(f"V16 provider input exposes frozen answers: {forbidden}")
    return value


__all__ = [
    "EXPECTED_RULE",
    "EXPECTED_RULE_SHA256",
    "V16PromptError",
    "ordered_cases",
    "provider_input",
    "verify_rule",
]
