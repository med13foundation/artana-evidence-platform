"""Regression tests for deterministic source-mention localization."""

from __future__ import annotations

import hashlib

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryBindingError,
    ClaimInventoryItem,
    ClaimMentionAnchor,
    bind_claim_inventory,
    claim_inventory_batch_input_sha256,
    claim_inventory_identity,
    claim_inventory_input_sha256,
)
from pydantic import ValidationError


def _inventory_item(
    *,
    text: str,
    cue: str,
    cue_anchor: dict[str, str] | None = None,
    first_argument: dict[str, object],
    second_span: str,
    claim_kind: str = "SCIENTIFIC_FINDING",
    polarity: str = "SUPPORT",
    epistemic_status: str = "ASSERTED",
) -> ClaimInventoryItem:
    return ClaimInventoryItem.model_validate(
        {
            "exact_span": text,
            "relation_cue_span": cue,
            "relation_cue_anchor": cue_anchor,
            "arguments": [
                first_argument,
                {
                    "role": "OTHER_ENTITY",
                    "event_role": "THEME",
                    "exact_span": second_span,
                    "role_rationale": "The source names the second participant.",
                },
            ],
            "source_locator": "normalized_extraction_text",
            "claim_kind": claim_kind,
            "event_type": "OTHER_EXPLICIT",
            "polarity": polarity,
            "epistemic_status": epistemic_status,
            "inventory_rationale": "The source contains one explicit event.",
        },
    )


def test_mention_anchor_requires_verbatim_context() -> None:
    with pytest.raises(ValidationError, match="left or right"):
        ClaimMentionAnchor.model_validate(
            {"mention_span": "WT1", "left_context": "", "right_context": ""},
        )


def test_repeated_argument_without_anchor_fails_closed() -> None:
    text = "WT1 in fibroblasts and WT1 in lymphocytes suggests regulation."
    item = _inventory_item(
        text=text,
        cue="suggests",
        first_argument={
            "role": "GENE_OR_PROTEIN",
            "event_role": "THEME",
            "exact_span": "WT1",
            "role_rationale": "WT1 is the repeated semantic participant.",
        },
        second_span="regulation",
    )

    with pytest.raises(ClaimInventoryBindingError, match="requires.*context anchor"):
        bind_claim_inventory(
            (item,),
            source_text=text,
            source_sha256=hashlib.sha256(text.encode()).hexdigest(),
            chunk_index=0,
        )


def test_one_argument_preserves_multiple_context_anchored_mentions() -> None:
    text = "WT1 in fibroblasts and WT1 in lymphocytes suggests regulation."
    item = _inventory_item(
        text=text,
        cue="suggests",
        first_argument={
            "role": "GENE_OR_PROTEIN",
            "event_role": "THEME",
            "exact_span": "WT1",
            "mention_anchors": [
                {
                    "mention_span": "WT1",
                    "left_context": "",
                    "right_context": " in fibroblasts",
                },
                {
                    "mention_span": "WT1",
                    "left_context": " and ",
                    "right_context": " in lymphocytes",
                },
            ],
            "role_rationale": "Both mentions denote the same participant.",
        },
        second_span="regulation",
    )

    bound = bind_claim_inventory(
        (item,),
        source_text=text,
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        chunk_index=0,
        source_start_offset=100,
    )[0]
    mentions = bound.bound_arguments[0].mentions

    assert [mention.source_start for mention in mentions] == [
        100 + text.index("WT1"),
        100 + text.rindex("WT1"),
    ]
    assert all(mention.exact_span == "WT1" for mention in mentions)


def test_context_anchor_must_select_exactly_one_occurrence() -> None:
    text = "WT1 in fibroblasts and WT1 in lymphocytes suggests regulation."
    item = _inventory_item(
        text=text,
        cue="suggests",
        first_argument={
            "role": "GENE_OR_PROTEIN",
            "event_role": "THEME",
            "exact_span": "WT1",
            "mention_anchors": [
                {
                    "mention_span": "WT1",
                    "left_context": "",
                    "right_context": " in",
                },
            ],
            "role_rationale": "The anchor is intentionally ambiguous.",
        },
        second_span="regulation",
    )

    with pytest.raises(ClaimInventoryBindingError, match="exactly one occurrence"):
        bind_claim_inventory(
            (item,),
            source_text=text,
            source_sha256=hashlib.sha256(text.encode()).hexdigest(),
            chunk_index=0,
        )


def test_exact_span_binding_rejects_overlapping_occurrences() -> None:
    item = _inventory_item(
        text="ABA",
        cue="B",
        first_argument={
            "role": "GENE_OR_PROTEIN",
            "event_role": "AGENT",
            "exact_span": "A",
            "role_rationale": "The first A is the source participant.",
        },
        second_span="B",
    )

    with pytest.raises(ClaimInventoryBindingError, match="exactly once"):
        bind_claim_inventory(
            (item,),
            source_text="ABABA",
            source_sha256=hashlib.sha256(b"ABABA").hexdigest(),
            chunk_index=0,
        )


def test_argument_anchor_context_may_extend_outside_claim_boundary() -> None:
    source = (
        "Therefore, iTreg induction has to occur before "
        "effector T cell differentiation occurs."
    )
    claim = source.removeprefix("Therefore, ")
    item = _inventory_item(
        text=claim,
        cue="has to occur before",
        first_argument={
            "role": "BIOLOGICAL_PROCESS",
            "event_role": "CAUSE",
            "exact_span": "iTreg induction",
            "mention_anchors": [
                {
                    "mention_span": "iTreg induction",
                    "left_context": "Therefore, ",
                    "right_context": " has to occur before",
                },
            ],
            "role_rationale": "The source names the preceding process.",
        },
        second_span="effector T cell differentiation",
    )

    bound = bind_claim_inventory(
        (item,),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        chunk_index=0,
    )[0]

    assert bound.source_start == len("Therefore, ")
    assert bound.bound_arguments[0].primary_mention.source_start == len("Therefore, ")


def test_trigger_anchor_context_may_extend_outside_claim_boundary() -> None:
    claim = (
        "The Wilms' tumor suppressor gene ( WT1 ) was previously identified "
        "as being imprinted"
    )
    source = f"{claim}, with frequent maternal expression."
    item = _inventory_item(
        text=claim,
        cue="was previously identified as being imprinted",
        cue_anchor={
            "mention_span": "was previously identified as being imprinted",
            "left_context": "( WT1 ) ",
            "right_context": ", with frequent maternal expression",
        },
        first_argument={
            "role": "GENE_OR_PROTEIN",
            "event_role": "THEME",
            "exact_span": "WT1",
            "role_rationale": "WT1 is the source-local gene.",
        },
        second_span="imprinted",
    )

    bound = bind_claim_inventory(
        (item,),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        chunk_index=0,
    )[0]

    assert bound.trigger_mention.exact_span == item.relation_cue_span
    assert bound.trigger_mention.source_end == len(claim)


def test_anchor_cannot_select_a_mention_outside_claim_boundary() -> None:
    source = "WT1 baseline. WT1 increases expression."
    claim = "WT1 increases expression."
    item = _inventory_item(
        text=claim,
        cue="increases",
        first_argument={
            "role": "GENE_OR_PROTEIN",
            "event_role": "AGENT",
            "exact_span": "WT1",
            "mention_anchors": [
                {
                    "mention_span": "WT1",
                    "left_context": "",
                    "right_context": " baseline",
                },
            ],
            "role_rationale": "The anchor deliberately selects the wrong WT1.",
        },
        second_span="expression",
    )

    with pytest.raises(ClaimInventoryBindingError, match="inside the claim"):
        bind_claim_inventory(
            (item,),
            source_text=source,
            source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            chunk_index=0,
        )


@pytest.mark.parametrize(
    ("claim_kind", "polarity", "epistemic_status"),
    [
        ("SCIENTIFIC_FINDING", "NULL_RESULT", "ASSERTED"),
        ("SCIENTIFIC_HYPOTHESIS", "SUPPORT", "PROVISIONAL"),
        ("SCIENTIFIC_HYPOTHESIS", "SUPPORT", "HYPOTHESIS"),
    ],
)
def test_inventory_direction_and_epistemic_force_are_independent(
    claim_kind: str,
    polarity: str,
    epistemic_status: str,
) -> None:
    item = _inventory_item(
        text="IL-4 did not alter TGF-beta signaling.",
        cue="did not alter",
        first_argument={
            "role": "CHEMICAL_OR_DRUG",
            "event_role": "AGENT",
            "exact_span": "IL-4",
            "role_rationale": "IL-4 is the tested factor.",
        },
        second_span="TGF-beta signaling",
        claim_kind=claim_kind,
        polarity=polarity,
        epistemic_status=epistemic_status,
    )

    assert item.polarity.value == polarity
    assert item.epistemic_status.value == epistemic_status


def test_repeated_trigger_uses_verbatim_context_instead_of_agent_offset() -> None:
    text = "AKT1 activates B cells and activates T cells."
    item = _inventory_item(
        text=text,
        cue="activates",
        cue_anchor={
            "mention_span": "activates",
            "left_context": " and ",
            "right_context": " T cells",
        },
        first_argument={
            "role": "GENE_OR_PROTEIN",
            "event_role": "AGENT",
            "exact_span": "AKT1",
            "role_rationale": "AKT1 is the event agent.",
        },
        second_span="T cells",
    )

    bound = bind_claim_inventory(
        (item,),
        source_text=text,
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        chunk_index=0,
        source_start_offset=500,
    )[0]

    assert bound.trigger_mention.source_start == 500 + text.rindex("activates")


def test_alias_and_coreference_mentions_preserve_canonical_argument() -> None:
    text = "WT1 was measured. The gene increased, and it remained elevated."
    item = _inventory_item(
        text=text,
        cue="increased",
        first_argument={
            "role": "GENE_OR_PROTEIN",
            "event_role": "THEME",
            "exact_span": "WT1",
            "mention_anchors": [
                {
                    "mention_span": "WT1",
                    "left_context": "",
                    "right_context": " was measured",
                },
                {
                    "mention_span": "The gene",
                    "left_context": "WT1 was measured. ",
                    "right_context": " increased",
                },
                {
                    "mention_span": "it",
                    "left_context": "increased, and ",
                    "right_context": " remained elevated",
                },
            ],
            "role_rationale": "The aliases refer to WT1 in this local claim.",
        },
        second_span="elevated",
    )

    bound = bind_claim_inventory(
        (item,),
        source_text=text,
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        chunk_index=0,
    )[0]

    assert bound.bound_arguments[0].argument.exact_span == "WT1"
    assert [mention.exact_span for mention in bound.bound_arguments[0].mentions] == [
        "WT1",
        "The gene",
        "it",
    ]
    assert "mention_anchors" not in bound.bound_arguments[0].argument.model_dump()


def test_legacy_source_start_uses_canonical_mention_when_alias_appears_first() -> None:
    text = "It remained elevated after WT1 increased regulation."
    item = _inventory_item(
        text=text,
        cue="increased",
        first_argument={
            "role": "GENE_OR_PROTEIN",
            "event_role": "AGENT",
            "exact_span": "WT1",
            "mention_anchors": [
                {
                    "mention_span": "It",
                    "left_context": "",
                    "right_context": " remained elevated",
                },
                {
                    "mention_span": "WT1",
                    "left_context": "remained elevated after ",
                    "right_context": " increased",
                },
            ],
            "role_rationale": "The local pronoun and WT1 name the same participant.",
        },
        second_span="regulation",
    )

    bound_argument = bind_claim_inventory(
        (item,),
        source_text=text,
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        chunk_index=0,
    )[0].bound_arguments[0]

    assert bound_argument.mentions[0].exact_span == "It"
    assert bound_argument.primary_mention.exact_span == "WT1"
    assert bound_argument.primary_mention.source_start == text.index("WT1")


def test_inventory_identity_excludes_localization_but_input_hash_includes_it() -> None:
    text = "WT1 in fibroblasts and WT1 in lymphocytes suggests regulation."
    common = {
        "role": "GENE_OR_PROTEIN",
        "event_role": "THEME",
        "exact_span": "WT1",
        "role_rationale": "WT1 is the participant.",
    }
    first = _inventory_item(
        text=text,
        cue="suggests",
        first_argument={
            **common,
            "mention_anchors": [
                {
                    "mention_span": "WT1",
                    "left_context": "",
                    "right_context": " in fibroblasts",
                },
            ],
        },
        second_span="regulation",
    )
    second = _inventory_item(
        text=text,
        cue="suggests",
        first_argument={
            **common,
            "mention_anchors": [
                {
                    "mention_span": "WT1",
                    "left_context": " and ",
                    "right_context": " in lymphocytes",
                },
            ],
        },
        second_span="regulation",
    )
    source_sha256 = hashlib.sha256(text.encode()).hexdigest()
    first_id = claim_inventory_identity(
        item=first,
        source_sha256=source_sha256,
        source_start=0,
    )
    second_id = claim_inventory_identity(
        item=second,
        source_sha256=source_sha256,
        source_start=0,
    )

    assert first_id == second_id
    assert claim_inventory_input_sha256(
        inventory_id=first_id,
        item=first,
    ) != claim_inventory_input_sha256(inventory_id=second_id, item=second)
    first_bound = bind_claim_inventory(
        (first,),
        source_text=text,
        source_sha256=source_sha256,
        chunk_index=0,
    )
    second_bound = bind_claim_inventory(
        (second,),
        source_text=text,
        source_sha256=source_sha256,
        chunk_index=0,
    )
    assert claim_inventory_batch_input_sha256(
        first_bound,
    ) != claim_inventory_batch_input_sha256(second_bound)


def test_duplicate_mention_anchors_fail_schema_validation() -> None:
    anchor = {
        "mention_span": "WT1",
        "left_context": "",
        "right_context": " in fibroblasts",
    }
    with pytest.raises(ValidationError, match="mention anchors must be unique"):
        _inventory_item(
            text="WT1 in fibroblasts suggests regulation.",
            cue="suggests",
            first_argument={
                "role": "GENE_OR_PROTEIN",
                "event_role": "THEME",
                "exact_span": "WT1",
                "mention_anchors": [anchor, anchor],
                "role_rationale": "WT1 is the participant.",
            },
            second_span="regulation",
        )


def test_duplicate_semantic_claims_cannot_hide_different_mention_payloads() -> None:
    text = "WT1 in fibroblasts and WT1 in lymphocytes suggests regulation."
    source_sha256 = hashlib.sha256(text.encode()).hexdigest()
    items = tuple(
        _inventory_item(
            text=text,
            cue="suggests",
            first_argument={
                "role": "GENE_OR_PROTEIN",
                "event_role": "THEME",
                "exact_span": "WT1",
                "mention_anchors": [anchor],
                "role_rationale": "WT1 is the semantic participant.",
            },
            second_span="regulation",
        )
        for anchor in (
            {
                "mention_span": "WT1",
                "left_context": "",
                "right_context": " in fibroblasts",
            },
            {
                "mention_span": "WT1",
                "left_context": " and ",
                "right_context": " in lymphocytes",
            },
        )
    )

    with pytest.raises(ClaimInventoryBindingError, match="cannot repeat"):
        bind_claim_inventory(
            items,
            source_text=text,
            source_sha256=source_sha256,
            chunk_index=0,
        )
