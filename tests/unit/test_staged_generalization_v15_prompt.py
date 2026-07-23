"""V15 focus-closure and occurrence-custody prompt regressions."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.validation.public_gold.staged_event.generalization.repair_v14.prompt import (
    provider_input as v14_provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.prompt import (
    EXPECTED_RULE,
    EXPECTED_RULE_SHA256,
    V15PromptError,
    ordered_cases,
    provider_input,
    verify_rule,
)


def test_v15_rule_is_the_exact_single_source_general_prompt_delta() -> None:
    rule = DEFAULT_PATHS.focus_occurrence_rule.read_text(encoding="utf-8")
    audit = verify_rule()

    assert rule == EXPECTED_RULE
    assert hashlib.sha256(rule.encode()).hexdigest() == EXPECTED_RULE_SHA256
    assert audit == {
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

    for leaked_term in (
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
    ):
        assert leaked_term not in rule


def test_v15_rule_fails_closed_on_any_wording_change(tmp_path: Path) -> None:
    changed_rule = tmp_path / "changed-v15-rule.md"
    changed_rule.write_text(
        EXPECTED_RULE.replace(
            "Do not traverse outward",
            "Usually do not traverse outward",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(V15PromptError, match="rule changed"):
        verify_rule(
            replace(DEFAULT_PATHS, focus_occurrence_rule=changed_rule),
        )


@pytest.mark.parametrize("case_id", CASE_ORDER)
def test_provider_packet_is_exact_v14_packet_plus_the_sole_v15_rule(
    case_id: str,
) -> None:
    frozen_v14 = v14_provider_input(case_id, DEFAULT_PATHS.v14)
    v14_prompt, delimiter, frozen_case = frozen_v14.partition(
        "\n--- FROZEN EXPOSED CASE ---\n"
    )
    expected = (
        v14_prompt
        + "\n--- V15 SINGLE SCIENTIFIC CHANGE ---\n"
        + EXPECTED_RULE
        + "--- END V15 SINGLE SCIENTIFIC CHANGE ---\n"
        + delimiter
        + frozen_case
    )

    actual = provider_input(case_id)
    prompt_only, actual_delimiter, actual_case = actual.partition(
        "\n--- FROZEN EXPOSED CASE ---\n"
    )

    assert actual == expected
    assert actual_delimiter == delimiter
    assert actual_case == frozen_case
    assert (
        prompt_only.removesuffix(
            "\n--- V15 SINGLE SCIENTIFIC CHANGE ---\n"
            + EXPECTED_RULE
            + "--- END V15 SINGLE SCIENTIFIC CHANGE ---\n"
        )
        == v14_prompt
    )
    assert actual.count("--- V15 SINGLE SCIENTIFIC CHANGE ---") == 1
    assert actual.count(EXPECTED_RULE) == 1
    assert '"reference"' not in actual
    assert "acceptable_texts" not in actual
    assert "expected participant" not in actual
    assert "grader policy" not in actual
    assert "focus-closure-consensus" not in actual
    assert "reviewer_id" not in actual


def test_v15_adversarial_focus_and_occurrence_boundaries_are_explicit() -> None:
    """Freeze the source-general decisions before the exposed provider run."""

    rule = DEFAULT_PATHS.focus_occurrence_rule.read_text(encoding="utf-8")
    required_decisions = {
        "focus_internal_nested_event_remains": (
            "complete focus-internal dependency closure of nested events"
        ),
        "outside_parent_is_not_an_event": (
            "Do not traverse outward to inventory a predicate outside "
            "the highlighted finding"
        ),
        "focus_local_role_occurrence_wins": ("bind that exact focus-local occurrence"),
        "outside_alias_cannot_replace_occurrence": (
            "may establish identity but cannot replace the bound occurrence"
        ),
        "true_anaphora_still_resolves": (
            "genuinely non-self-denoting pronoun, relative phrase, "
            "demonstrative, ellipsis, partitive, or implicit argument"
        ),
        "ambiguous_resolution_fails_closed": (
            "fail closed under the existing rules if no unique "
            "source-supported resolution exists"
        ),
        "v14_head_and_restriction_rule_remains": (
            "retaining its semantic noun head and nonredundant restrictive identity"
        ),
        "optional_context_cannot_fill_mandatory_gaps": (
            "Optional material cannot add an outside event, compensate "
            "for a missing mandatory participant or link"
        ),
    }

    assert all(decision in rule for decision in required_decisions.values())


def test_v15_keeps_the_frozen_six_case_order_and_rejects_fresh_access() -> None:
    assert tuple(case.case_id for case in ordered_cases()) == CASE_ORDER

    with pytest.raises(V15PromptError, match="unknown exposed case"):
        provider_input("fresh-case-must-not-be-accessed")
