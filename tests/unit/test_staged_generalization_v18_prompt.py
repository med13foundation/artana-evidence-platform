"""Provider-facing regressions for the narrowly scoped V18 instruction."""

from __future__ import annotations

import hashlib

import pytest

from scripts.validation.public_gold.staged_event.generalization.repair_v18.config import (
    CASE_ORDER,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v18.prompt import (
    EXPECTED_RULE,
    EXPECTED_RULE_SHA256,
    V18PromptError,
    provider_input,
    verify_rule,
)


def test_v18_rule_is_frozen_source_general_and_does_not_add_a_schema() -> None:
    observed = verify_rule()

    assert hashlib.sha256(EXPECTED_RULE.encode()).hexdigest() == EXPECTED_RULE_SHA256
    assert observed["source_general"] is True
    assert observed["inline_restrictive_modifier_decomposition_permitted"] is False
    assert observed["complete_parent_span_preserved"] is True
    assert observed["non_inline_anaphoric_locus_scope_mandatory"] is True
    assert observed["entity_types_changed"] is False
    assert observed["new_schema_introduced"] is False
    assert "SLC12A3" not in EXPECTED_RULE
    assert "947 variants" not in EXPECTED_RULE
    assert "RA" not in EXPECTED_RULE


@pytest.mark.parametrize("case_id", CASE_ORDER)
def test_v18_packet_replaces_the_v17_prompt_rule_with_one_v15_based_change(
    case_id: str,
) -> None:
    value = provider_input(case_id)
    prompt, packet = value.split("\n--- FROZEN EXPOSED CASE ---\n", maxsplit=1)

    assert "--- V15 SINGLE SCIENTIFIC CHANGE ---" in prompt
    assert "--- V16 SINGLE SCIENTIFIC CHANGE ---" not in prompt
    assert "--- V17 SINGLE SCIENTIFIC CHANGE ---" not in prompt
    assert "--- V18 SINGLE SCIENTIFIC CHANGE ---" in prompt
    assert "inline modifier" in prompt
    assert "participant_scope_links" in prompt
    assert "mandatory" in prompt.lower()
    assert '"reference"' not in value
    assert "acceptable_texts" not in value
    assert packet


def test_v18_rule_states_the_anaphoric_requirement_is_independent_of_the_inline_rule() -> (
    None
):
    assert "independently of the inline-modifier prohibition" in EXPECTED_RULE
    assert "not weakened, excused, or made optional" in EXPECTED_RULE
    assert "inferable, minor, or already implied by nearby context" in EXPECTED_RULE


def test_v18_packet_rejects_unknown_cases() -> None:
    with pytest.raises(V18PromptError, match="unknown exposed case"):
        provider_input("not-an-exposed-case")
