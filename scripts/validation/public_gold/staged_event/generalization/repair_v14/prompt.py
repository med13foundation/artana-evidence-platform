"""Compose and verify the sole V14 provider-facing scientific change."""

from __future__ import annotations

import hashlib
import json

from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
    agent_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_panel import (
    load_frozen_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    V14Paths,
)

EXPECTED_RULE = """# V14 Complete Biomedical Participant Denotation

This rule clarifies the existing named-biomedical occurrence boundary. It does
not replace any event, evidence, or semantic rule.

- Select the smallest exact contiguous source span that independently denotes
  the same biomedical participant occurrence while preserving its
  scientifically restrictive identity and scope.
- An adjacent entity-type noun may be omitted only when the retained text is an
  independently referential lexicalized biomedical identifier that denotes the
  same participant in that occurrence.
- Retain the semantic noun head when removing it would leave only modifiers,
  classifiers, stages, taxonomic restrictions, or other attributive text. Do
  not reconstruct an omitted head from `entity_type`, the explanation, or
  surrounding evidence.
- Retain nonredundant restrictive modifiers unless the same output explicitly
  represents and links an equivalent restriction. If the schema cannot
  represent that relation, retain the modifier in the participant span.
- If either denotation or restrictive scope would be lost, fail closed with
  `INCOMPLETE` or `ABSTAIN`; do not shorten the participant.

This rule changes only participant occurrence text. It cannot create or remove
events, participants, entity types, roles, links, root choices, semantic axes,
statistics, evidence, completeness states, or scientific claims.
"""
EXPECTED_RULE_SHA256 = hashlib.sha256(EXPECTED_RULE.encode()).hexdigest()
_FORBIDDEN_RULE_TERMS = (
    "PMID",
    "HCMV",
    "SLC12A3",
    "immediate-early",
    "p53",
    "fibroblast",
    "BioNLP",
    "gold",
    "reference answer",
)
_FORBIDDEN_PROVIDER_TERMS = (
    '"reference"',
    "acceptable_texts",
    "expected participant",
    "grader policy",
    "participant-and-role-consensus",
    "reviewer_id",
)


class V14PromptError(ValueError):
    """The V14 rule or provider packet diverged from its frozen scope."""


def ordered_cases(
    paths: V14Paths = DEFAULT_PATHS,
) -> tuple[GeneralizationCase, ...]:
    """Return the unchanged exposed panel in the preregistered V14 order."""

    cases = load_frozen_panel(paths.v13.panel)
    by_id = {case.case_id: case for case in cases}
    if set(by_id) != set(CASE_ORDER):
        raise V14PromptError("V14 panel membership differs from frozen V13")
    return tuple(by_id[case_id] for case_id in CASE_ORDER)


def verify_rule(paths: V14Paths = DEFAULT_PATHS) -> dict[str, object]:
    """Fail closed if wording, scope, or source-generality changed."""

    actual = paths.participant_rule.read_text(encoding="utf-8")
    if actual != EXPECTED_RULE:
        raise V14PromptError("V14 participant-denotation rule changed")
    forbidden = tuple(term for term in _FORBIDDEN_RULE_TERMS if term in actual)
    if forbidden:
        raise V14PromptError(f"V14 rule contains case-specific terms: {forbidden}")
    return {
        "rule_sha256": EXPECTED_RULE_SHA256,
        "source_general": True,
        "participant_occurrence_text_only": True,
        "can_create_events_participants_or_links": False,
        "benchmark_projection_specific": False,
        "case_specific_terms": [],
    }


def provider_input(
    case_id: str,
    paths: V14Paths = DEFAULT_PATHS,
) -> str:
    """Compose frozen V11-V13 rules, the sole V14 rule, and one exposed case."""

    case = next(
        (item for item in ordered_cases(paths) if item.case_id == case_id),
        None,
    )
    if case is None:
        raise V14PromptError(f"unknown exposed case: {case_id}")
    verify_rule(paths)
    value = (
        paths.v13.v11_prompt.read_text(encoding="utf-8")
        + "\n\n--- V12 PRESERVED SCIENTIFIC CHANGE ---\n"
        + paths.v13.v12_focus_rule.read_text(encoding="utf-8")
        + "--- END V12 PRESERVED SCIENTIFIC CHANGE ---\n"
        + "\n--- V13 PRESERVED SCIENTIFIC CHANGE ---\n"
        + paths.v13.root_rule.read_text(encoding="utf-8")
        + "--- END V13 PRESERVED SCIENTIFIC CHANGE ---\n"
        + "\n--- V14 SINGLE SCIENTIFIC CHANGE ---\n"
        + paths.participant_rule.read_text(encoding="utf-8")
        + "--- END V14 SINGLE SCIENTIFIC CHANGE ---\n"
        + "\n--- FROZEN EXPOSED CASE ---\n"
        + json.dumps(agent_case(case), indent=2, sort_keys=True)
        + "\n--- END FROZEN EXPOSED CASE ---\n"
    )
    forbidden = tuple(term for term in _FORBIDDEN_PROVIDER_TERMS if term in value)
    if forbidden:
        raise V14PromptError(f"V14 provider input exposes frozen answers: {forbidden}")
    return value


__all__ = [
    "EXPECTED_RULE",
    "EXPECTED_RULE_SHA256",
    "V14PromptError",
    "ordered_cases",
    "provider_input",
    "verify_rule",
]
