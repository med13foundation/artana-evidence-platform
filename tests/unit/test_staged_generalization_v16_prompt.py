"""Provider-facing source-generality regressions for V16."""

from __future__ import annotations

import hashlib

import pytest

from scripts.validation.public_gold.staged_event.generalization.repair_v16.config import (
    CASE_ORDER,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.prompt import (
    EXPECTED_RULE,
    EXPECTED_RULE_SHA256,
    V16PromptError,
    provider_input,
    verify_rule,
)


def test_v16_rule_is_frozen_source_general_and_limited_to_scope_representation() -> (
    None
):
    observed = verify_rule()

    assert hashlib.sha256(EXPECTED_RULE.encode()).hexdigest() == EXPECTED_RULE_SHA256
    assert observed["source_general"] is True
    assert observed["participant_scope_link_added"] is True
    assert observed["partitive_scope_added"] is True
    assert observed["event_inventory_changed"] is False
    assert observed["mandatory_event_arguments_changed"] is False
    assert observed["v14_identifier_rule_preserved"] is True
    assert "SLC12A3" not in EXPECTED_RULE
    assert "947 variants" not in EXPECTED_RULE


@pytest.mark.parametrize("case_id", CASE_ORDER)
def test_v16_packet_preserves_prior_prompt_and_adds_only_the_scope_rule(
    case_id: str,
) -> None:
    value = provider_input(case_id)
    prompt, packet = value.split("\n--- FROZEN EXPOSED CASE ---\n", maxsplit=1)

    assert "--- V15 SINGLE SCIENTIFIC CHANGE ---" in prompt
    assert "--- V16 SINGLE SCIENTIFIC CHANGE ---" in prompt
    assert "participant_scope_links" in prompt
    assert "partitive_scope" in prompt
    assert '"reference"' not in value
    assert "acceptable_texts" not in value
    assert packet


def test_v16_packet_rejects_unknown_cases() -> None:
    with pytest.raises(V16PromptError, match="unknown exposed case"):
        provider_input("not-an-exposed-case")
