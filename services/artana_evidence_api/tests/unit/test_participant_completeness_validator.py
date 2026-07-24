"""Unit tests for the V16 participant-completeness validator and bounded repair.

These tests pin the deterministic detection contract and the fail-closed repair
acceptance rules for ``staged-generalization-v16-exposed-run-v1``. They exercise
pure functions only: no provider call is issued and no prompt content is asserted
beyond the absence of answer-shaped hints.
"""

from __future__ import annotations

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,
    ParticipantCompletenessDecision,
    shortest_role_snippet,
    validate_claim_participant_completeness,
)
from artana_evidence_api.document_extraction_support.claim_frames.event_types import (
    ClaimEventRole,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_framing_repair import (
    accept_repaired_inventory_item,
    build_participant_repair_prompt,
)


def _argument(role: str, event_role: str, span: str) -> dict[str, object]:
    return {
        "role": role,
        "event_role": event_role,
        "exact_span": span,
        "role_rationale": f"{span} is named in the source.",
    }


def _inventory_item(
    *,
    event_type: str,
    arguments: list[dict[str, object]],
    exact_span: str = "SLC12A3 variants are linked to hypertension.",
) -> ClaimInventoryItem:
    return ClaimInventoryItem.model_validate(
        {
            "exact_span": exact_span,
            "relation_cue_span": "linked to",
            "arguments": arguments,
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": event_type,
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "The source states one explicit event.",
        },
    )


def test_regulation_with_cause_and_theme_is_complete() -> None:
    item = _inventory_item(
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "HCMV immediate-early proteins"),
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
        ],
    )
    finding = validate_claim_participant_completeness(item)
    assert finding.decision is ParticipantCompletenessDecision.COMPLETE
    assert finding.is_complete
    assert finding.missing_roles == ()
    assert finding.mandatory_roles == (ClaimEventRole.CAUSE, ClaimEventRole.THEME)


def test_regulation_missing_cause_is_incomplete() -> None:
    # Mirrors the V15 uncertainty failure: the mandatory CAUSE participant
    # (SLC12A3's regulator) was dropped, leaving only the THEME.
    item = _inventory_item(
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
            _argument("OTHER_ENTITY", "CONTEXT", "hypertension"),
        ],
    )
    finding = validate_claim_participant_completeness(item)
    assert finding.decision is ParticipantCompletenessDecision.INCOMPLETE
    assert finding.missing_roles == (ClaimEventRole.CAUSE,)
    assert finding.as_json()["missing_roles"] == ("CAUSE",)


def test_other_explicit_has_no_mandatory_roles() -> None:
    item = _inventory_item(
        event_type="OTHER_EXPLICIT",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "WT1"),
            _argument("OTHER_ENTITY", "CONTEXT", "fibroblasts"),
        ],
    )
    finding = validate_claim_participant_completeness(item)
    assert finding.decision is ParticipantCompletenessDecision.COMPLETE
    assert finding.mandatory_roles == ()


def test_expression_requires_theme() -> None:
    item = _inventory_item(
        event_type="EXPRESSION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "BRCA1"),
            _argument("OTHER_ENTITY", "CONTEXT", "lymphocytes"),
        ],
    )
    finding = validate_claim_participant_completeness(item)
    assert finding.decision is ParticipantCompletenessDecision.INCOMPLETE
    assert finding.missing_roles == (ClaimEventRole.THEME,)


def test_repair_prompt_names_missing_roles_without_answer_hint() -> None:
    item = _inventory_item(
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
            _argument("OTHER_ENTITY", "CONTEXT", "hypertension"),
        ],
    )
    finding = validate_claim_participant_completeness(item)
    source_text = "HCMV immediate-early proteins upregulate SLC12A3 expression."
    prompt = build_participant_repair_prompt(
        base_prompt="BASE INVENTORY PROMPT",
        finding=finding,
        source_text=source_text,
    )
    assert "BASE INVENTORY PROMPT" in prompt
    assert "CAUSE" in prompt
    assert source_text in prompt
    # The repair prompt must not leak the expected participant identity.
    assert "HCMV immediate-early proteins" not in prompt.replace(source_text, "")


def test_repair_prompt_rejects_complete_finding() -> None:
    item = _inventory_item(
        event_type="EXPRESSION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "BRCA1"),
            _argument("OTHER_ENTITY", "CONTEXT", "lymphocytes"),
        ],
    )
    finding = validate_claim_participant_completeness(item)
    with pytest.raises(ValueError, match="complete"):
        build_participant_repair_prompt(
            base_prompt="BASE",
            finding=finding,
            source_text="BRCA1 is expressed in lymphocytes.",
        )


def test_accept_repair_when_complete_and_preserved() -> None:
    original = _inventory_item(
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
            _argument("OTHER_ENTITY", "CONTEXT", "hypertension"),
        ],
    )
    repaired = _inventory_item(
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
            _argument("OTHER_ENTITY", "CONTEXT", "hypertension"),
            _argument("GENE_OR_PROTEIN", "CAUSE", "HCMV immediate-early proteins"),
        ],
    )
    finding = validate_claim_participant_completeness(original)
    acceptance = accept_repaired_inventory_item(
        original=original,
        repaired=repaired,
        finding=finding,
    )
    assert acceptance.accepted
    assert acceptance.reason == "repaired_complete_and_preserved"


def test_reject_repair_that_drops_bound_role() -> None:
    original = _inventory_item(
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
            _argument("OTHER_ENTITY", "CONTEXT", "hypertension"),
        ],
    )
    repaired = _inventory_item(
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "HCMV immediate-early proteins"),
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
        ],
    )
    finding = validate_claim_participant_completeness(original)
    acceptance = accept_repaired_inventory_item(
        original=original,
        repaired=repaired,
        finding=finding,
    )
    assert not acceptance.accepted
    assert acceptance.reason == "repaired_dropped_bound_role"


def test_reject_repair_that_changes_claim_span() -> None:
    original = _inventory_item(
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
            _argument("OTHER_ENTITY", "CONTEXT", "hypertension"),
        ],
    )
    repaired = _inventory_item(
        event_type="POSITIVE_REGULATION",
        exact_span="A different claim span entirely.",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
            _argument("OTHER_ENTITY", "CONTEXT", "hypertension"),
            _argument("GENE_OR_PROTEIN", "CAUSE", "HCMV immediate-early proteins"),
        ],
    )
    finding = validate_claim_participant_completeness(original)
    acceptance = accept_repaired_inventory_item(
        original=original,
        repaired=repaired,
        finding=finding,
    )
    assert not acceptance.accepted
    assert acceptance.reason == "repaired_claim_span_changed"


def test_reject_repair_that_changes_event_type() -> None:
    original = _inventory_item(
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
            _argument("OTHER_ENTITY", "CONTEXT", "hypertension"),
        ],
    )
    repaired = _inventory_item(
        event_type="EXPRESSION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
            _argument("OTHER_ENTITY", "CONTEXT", "hypertension"),
            _argument("GENE_OR_PROTEIN", "CAUSE", "HCMV immediate-early proteins"),
        ],
    )
    finding = validate_claim_participant_completeness(original)
    acceptance = accept_repaired_inventory_item(
        original=original,
        repaired=repaired,
        finding=finding,
    )
    assert not acceptance.accepted
    assert acceptance.reason == "repaired_event_type_changed"


def test_reject_repair_still_incomplete() -> None:
    original = _inventory_item(
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
            _argument("OTHER_ENTITY", "CONTEXT", "hypertension"),
        ],
    )
    # Repaired item still lacks the mandatory CAUSE role.
    repaired = _inventory_item(
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "SLC12A3"),
            _argument("OTHER_ENTITY", "CONTEXT", "hypertension"),
        ],
    )
    finding = validate_claim_participant_completeness(original)
    acceptance = accept_repaired_inventory_item(
        original=original,
        repaired=repaired,
        finding=finding,
    )
    assert not acceptance.accepted
    assert acceptance.reason == "repaired_still_incomplete"
    assert acceptance.still_missing_roles == (ClaimEventRole.CAUSE,)


def test_snippet_is_bounded_verbatim_prefix() -> None:
    long_text = "x" * 400
    snippet = shortest_role_snippet(long_text, max_length=160)
    assert len(snippet) == 160
    assert snippet == "x" * 160
    short_text = "  short claim  "
    assert shortest_role_snippet(short_text) == "short claim"


def test_snippet_rejects_nonpositive_length() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        shortest_role_snippet("text", max_length=0)
