"""V14 complete-participant prompt and provider-packet regressions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from scripts.validation.public_gold.staged_event.generalization.panel import (
    agent_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.prompt import (
    EXPECTED_RULE,
    EXPECTED_RULE_SHA256,
    V14PromptError,
    ordered_cases,
    provider_input,
    verify_rule,
)


def test_v14_rule_is_the_exact_single_source_general_prompt_delta() -> None:
    rule = DEFAULT_PATHS.participant_rule.read_text(encoding="utf-8")
    audit = verify_rule()

    assert rule == EXPECTED_RULE
    assert hashlib.sha256(rule.encode()).hexdigest() == EXPECTED_RULE_SHA256
    assert audit == {
        "rule_sha256": EXPECTED_RULE_SHA256,
        "source_general": True,
        "participant_occurrence_text_only": True,
        "can_create_events_participants_or_links": False,
        "benchmark_projection_specific": False,
        "case_specific_terms": [],
    }
    assert "smallest exact contiguous source span" in rule
    assert "independently denotes" in rule
    assert "Retain the semantic noun head" in rule
    assert "only modifiers" in rule
    assert "Retain nonredundant restrictive modifiers" in rule
    assert "retain the modifier in the participant span" in rule
    assert "This rule changes only participant occurrence text." in rule

    for leaked_term in (
        "PMID",
        "HCMV",
        "SLC12A3",
        "immediate-early",
        "p53",
        "fibroblast",
        "BioNLP",
        "gold",
        "reference answer",
    ):
        assert leaked_term not in rule


def test_v14_rule_fails_closed_on_any_wording_change(
    tmp_path: Path,
) -> None:
    changed_rule = tmp_path / "changed-v14-rule.md"
    changed_rule.write_text(
        EXPECTED_RULE.replace(
            "smallest exact contiguous source span",
            "shortest convenient source span",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(V14PromptError, match="rule changed"):
        verify_rule(replace(DEFAULT_PATHS, participant_rule=changed_rule))


def test_v14_preserves_standalone_identifiers_without_case_specific_examples() -> None:
    """The rule keeps V11's SLC12A3 behavior without teaching that answer."""

    rule = DEFAULT_PATHS.participant_rule.read_text(encoding="utf-8")
    uncertainty_packet = provider_input("generalization-uncertainty")
    prompt_only, case_only = uncertainty_packet.split(
        "\n--- FROZEN EXPOSED CASE ---\n",
        maxsplit=1,
    )

    assert (
        "An adjacent entity-type noun may be omitted only when the retained "
        "text is an\n  independently referential lexicalized biomedical "
        "identifier"
    ) in rule
    assert (
        "Retain the semantic noun head when removing it would leave only modifiers"
    ) in rule
    assert "SLC12A3" not in rule
    assert "SLC12A3" not in prompt_only
    assert "SLC12A3" in case_only
    assert (
        "Do not expand that name merely to include an\n  adjacent generic "
        "entity-type word"
    ) in prompt_only


@pytest.mark.parametrize("case_id", CASE_ORDER)
def test_provider_packet_is_exact_frozen_v11_through_v14_plus_one_exposed_case(
    case_id: str,
) -> None:
    cases = ordered_cases()
    case = next(item for item in cases if item.case_id == case_id)
    expected_prompt = (
        DEFAULT_PATHS.v13.v11_prompt.read_text(encoding="utf-8")
        + "\n\n--- V12 PRESERVED SCIENTIFIC CHANGE ---\n"
        + DEFAULT_PATHS.v13.v12_focus_rule.read_text(encoding="utf-8")
        + "--- END V12 PRESERVED SCIENTIFIC CHANGE ---\n"
        + "\n--- V13 PRESERVED SCIENTIFIC CHANGE ---\n"
        + DEFAULT_PATHS.v13.root_rule.read_text(encoding="utf-8")
        + "--- END V13 PRESERVED SCIENTIFIC CHANGE ---\n"
        + "\n--- V14 SINGLE SCIENTIFIC CHANGE ---\n"
        + DEFAULT_PATHS.participant_rule.read_text(encoding="utf-8")
        + "--- END V14 SINGLE SCIENTIFIC CHANGE ---\n"
    )
    expected_packet = (
        expected_prompt
        + "\n--- FROZEN EXPOSED CASE ---\n"
        + json.dumps(agent_case(case), indent=2, sort_keys=True)
        + "\n--- END FROZEN EXPOSED CASE ---\n"
    )

    actual = provider_input(case_id)
    prompt_only, serialized_case = actual.split(
        "\n--- FROZEN EXPOSED CASE ---\n",
        maxsplit=1,
    )
    serialized_case = serialized_case.removesuffix(
        "\n--- END FROZEN EXPOSED CASE ---\n"
    )
    packet_case = _object(json.loads(serialized_case))

    assert actual == expected_packet
    assert prompt_only == expected_prompt
    assert packet_case == agent_case(case)
    assert set(packet_case) == {
        "case_id",
        "source_id",
        "source_sha256",
        "local_context",
        "focus_passage",
    }
    assert packet_case["case_id"] == case_id
    assert '"reference"' not in actual
    assert "acceptable_texts" not in actual
    assert "expected participant" not in actual
    assert "grader policy" not in actual
    assert "participant-and-role-consensus" not in actual
    assert "reviewer_id" not in actual


def test_provider_packet_rejects_every_non_exposed_case() -> None:
    assert tuple(case.case_id for case in ordered_cases()) == CASE_ORDER

    with pytest.raises(V14PromptError, match="unknown exposed case"):
        provider_input("fresh-case-must-not-be-accessed")


def _object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return cast("dict[str, object]", value)
