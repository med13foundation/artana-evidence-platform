"""Tests for source-bound links between nested biomedical events."""

from __future__ import annotations

import copy
import hashlib

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,
    bind_claim_inventory,
    bind_claim_inventory_items,
    link_controlled_events,
)

_SOURCE = "Runx deficiency reduced TGF-beta induction of Foxp3."


def _argument(
    role: str,
    event_role: str,
    exact_span: str,
) -> dict[str, object]:
    return {
        "role": role,
        "event_role": event_role,
        "exact_span": exact_span,
        "role_rationale": "The source assigns this event-local role.",
    }


def _item(
    *,
    exact_span: str,
    cue: str,
    event_type: str,
    arguments: list[dict[str, object]],
) -> ClaimInventoryItem:
    return ClaimInventoryItem.model_validate(
        {
            "exact_span": exact_span,
            "relation_cue_span": cue,
            "arguments": arguments,
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": event_type,
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "The source explicitly states this event.",
        },
    )


def _outer_item() -> ClaimInventoryItem:
    return _item(
        exact_span=_SOURCE,
        cue="reduced",
        event_type="NEGATIVE_REGULATION",
        arguments=[
            _argument("OTHER_ENTITY", "CAUSE", "Runx deficiency"),
            _argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                "TGF-beta induction of Foxp3",
            ),
        ],
    )


def _inner_item(*, event_type: str = "POSITIVE_REGULATION") -> ClaimInventoryItem:
    return _item(
        exact_span="TGF-beta induction of Foxp3",
        cue="induction",
        event_type=event_type,
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "TGF-beta"),
            _argument("GENE_OR_PROTEIN", "THEME", "Foxp3"),
        ],
    )


def _bind(*items: ClaimInventoryItem):
    return bind_claim_inventory(
        tuple(items),
        source_text=_SOURCE,
        source_sha256=hashlib.sha256(_SOURCE.encode()).hexdigest(),
        chunk_index=0,
    )


def test_unique_source_containment_links_outer_theme_to_inner_event() -> None:
    outer, inner = _bind(_outer_item(), _inner_item())

    result = link_controlled_events((outer, inner))

    assert result.ambiguities == ()
    assert len(result.links) == 1
    link = result.links[0]
    assert link.controller_inventory_id == outer.inventory_id
    assert link.controller_theme_argument_index == 1
    assert link.controlled_inventory_id == inner.inventory_id
    assert _SOURCE[link.theme_source_start : link.theme_source_end] == (
        "TGF-beta induction of Foxp3"
    )


def test_process_theme_without_explicit_sibling_does_not_invent_event() -> None:
    (outer,) = _bind(_outer_item())

    result = link_controlled_events((outer,))

    assert result.links == ()
    assert result.ambiguities == ()


def test_two_matching_sibling_events_fail_closed_as_ambiguous() -> None:
    outer, specific, generic = _bind(
        _outer_item(),
        _inner_item(),
        _inner_item(event_type="REGULATION"),
    )

    result = link_controlled_events((outer, specific, generic))

    assert result.links == ()
    assert len(result.ambiguities) == 1
    assert set(result.ambiguities[0].candidate_inventory_ids) == {
        specific.inventory_id,
        generic.inventory_id,
    }


def test_link_identity_follows_bound_inner_semantics_without_role_inference() -> None:
    inner_payload = _inner_item().model_dump(mode="json")
    changed_payload = copy.deepcopy(inner_payload)
    changed_payload["arguments"][0]["event_role"] = "AGENT"
    changed_inner = ClaimInventoryItem.model_validate(changed_payload)
    outer, inner = _bind(_outer_item(), changed_inner)

    result = link_controlled_events((outer, inner))

    assert len(result.links) == 1
    assert result.links[0].controlled_inventory_id == inner.inventory_id
    assert inner.inventory_id != _bind(_inner_item())[0].inventory_id


def test_inner_context_outside_process_span_does_not_block_core_link() -> None:
    source = "Runx deficiency reduced TGF-beta induction of Foxp3 in T cells."
    outer = _item(
        exact_span=source,
        cue="reduced",
        event_type="NEGATIVE_REGULATION",
        arguments=[
            _argument("OTHER_ENTITY", "CAUSE", "Runx deficiency"),
            _argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                "TGF-beta induction of Foxp3",
            ),
        ],
    )
    inner = _item(
        exact_span="TGF-beta induction of Foxp3 in T cells",
        cue="induction",
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "TGF-beta"),
            _argument("GENE_OR_PROTEIN", "THEME", "Foxp3"),
            _argument("POPULATION", "CONTEXT", "T cells"),
        ],
    )
    bound = bind_claim_inventory(
        (outer, inner),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        chunk_index=0,
    )

    assert len(link_controlled_events(bound).links) == 1


def test_same_surface_in_different_chunks_cannot_cross_link() -> None:
    source_sha256 = hashlib.sha256(_SOURCE.encode()).hexdigest()
    (outer,) = bind_claim_inventory(
        (_outer_item(),),
        source_text=_SOURCE,
        source_sha256=source_sha256,
        chunk_index=0,
    )
    (inner,) = bind_claim_inventory(
        (_inner_item(),),
        source_text=_SOURCE,
        source_sha256=source_sha256,
        chunk_index=1,
    )

    assert link_controlled_events((outer, inner)).links == ()


def test_partial_token_prefix_cannot_form_a_controlled_event_link() -> None:
    partial_inner = _item(
        exact_span="TGF-beta induction of Fox",
        cue="induction",
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "TGF-beta"),
            _argument("GENE_OR_PROTEIN", "THEME", "Fox"),
        ],
    )
    outer, inner = _bind(_outer_item(), partial_inner)

    assert link_controlled_events((outer, inner)).links == ()


def test_source_distinct_coordinated_inner_events_form_fan_out_links() -> None:
    source = "CIITA controls transactivation of DR alpha at S and X2."
    outer = _item(
        exact_span=source,
        cue="controls",
        event_type="REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "CIITA"),
            _argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                "transactivation of DR alpha at S and X2",
            ),
        ],
    )
    inner_s = _item(
        exact_span="transactivation of DR alpha at S",
        cue="transactivation",
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "DR alpha"),
            _argument("OTHER_ENTITY", "SITE", "S"),
        ],
    )
    inner_x2 = _item(
        exact_span="transactivation of DR alpha at S and X2",
        cue="transactivation",
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "DR alpha"),
            _argument("OTHER_ENTITY", "SITE", "X2"),
        ],
    )
    bound = bind_claim_inventory(
        (outer, inner_s, inner_x2),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        chunk_index=0,
    )

    result = link_controlled_events(bound)

    assert result.ambiguities == ()
    assert len(result.links) == 2
    assert {link.controlled_inventory_id for link in result.links} == {
        bound[1].inventory_id,
        bound[2].inventory_id,
    }


def test_agent_declared_anaphoric_process_referent_links_sibling_events() -> None:
    source = (
        "ZEB blocks the activity of c-Myb and Ets individually, but together the "
        "factors synergize to resist this repression."
    )
    inner_cmyb = _item(
        exact_span="ZEB blocks the activity of c-Myb and Ets individually",
        cue="blocks",
        event_type="NEGATIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "ZEB"),
            _argument("GENE_OR_PROTEIN", "THEME", "c-Myb"),
        ],
    )
    inner_ets = _item(
        exact_span="ZEB blocks the activity of c-Myb and Ets individually",
        cue="blocks",
        event_type="NEGATIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "ZEB"),
            _argument("GENE_OR_PROTEIN", "THEME", "Ets"),
        ],
    )
    outer = _item(
        exact_span="together the factors synergize to resist this repression",
        cue="synergize to resist",
        event_type="NEGATIVE_REGULATION",
        arguments=[
            {
                **_argument("GENE_OR_PROTEIN", "CAUSE", "the factors"),
                "referent_anchors": [
                    {
                        "mention_span": "c-Myb",
                        "left_context": "the activity of ",
                        "right_context": " and Ets individually",
                    },
                    {
                        "mention_span": "Ets",
                        "left_context": "the activity of c-Myb and ",
                        "right_context": " individually",
                    },
                ],
            },
            {
                **_argument("BIOLOGICAL_PROCESS", "THEME", "this repression"),
                "referent_anchors": [
                    {
                        "mention_span": (
                            "ZEB blocks the activity of c-Myb and Ets individually"
                        ),
                        "left_context": "",
                        "right_context": ", but together",
                    },
                ],
            },
        ],
    )

    bound = bind_claim_inventory(
        (inner_cmyb, inner_ets, outer),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        chunk_index=0,
    )
    result = link_controlled_events(bound)

    assert [mention.exact_span for mention in bound[2].bound_arguments[0].referent_mentions] == [
        "c-Myb",
        "Ets",
    ]
    assert result.ambiguities == ()
    assert len(result.links) == 2
    assert {link.controlled_inventory_id for link in result.links} == {
        bound[0].inventory_id,
        bound[1].inventory_id,
    }


def test_referent_anchors_change_claim_identity_without_rewriting_surface() -> None:
    source = "c-Myb acts, and the factor responds."
    without_referent = _item(
        exact_span="the factor responds",
        cue="responds",
        event_type="TREATMENT_RESPONSE",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "the factor"),
            _argument("OTHER_ENTITY", "CONTEXT", "responds"),
        ],
    )
    payload = without_referent.model_dump(mode="json")
    payload["arguments"][0]["referent_anchors"] = [
        {
            "mention_span": "c-Myb",
            "left_context": "",
            "right_context": " acts",
        },
    ]
    with_referent = ClaimInventoryItem.model_validate(payload)

    first = bind_claim_inventory(
        (without_referent,),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        chunk_index=0,
    )[0]
    second = bind_claim_inventory(
        (with_referent,),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        chunk_index=0,
    )[0]

    assert first.inventory_id != second.inventory_id
    assert second.item.arguments[0].exact_span == "the factor"
    assert second.bound_arguments[0].referent_mentions[0].exact_span == "c-Myb"


def test_referent_anchor_order_does_not_change_claim_identity() -> None:
    source = "c-Myb and Ets act, and the factors respond."
    payload = _item(
        exact_span="the factors respond",
        cue="respond",
        event_type="TREATMENT_RESPONSE",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "the factors"),
            _argument("OTHER_ENTITY", "CONTEXT", "respond"),
        ],
    ).model_dump(mode="json")
    referents = [
        {
            "mention_span": "c-Myb",
            "left_context": "",
            "right_context": " and Ets act",
        },
        {
            "mention_span": "Ets",
            "left_context": "c-Myb and ",
            "right_context": " act",
        },
    ]
    payload["arguments"][0]["referent_anchors"] = referents
    first = ClaimInventoryItem.model_validate(payload)
    payload["arguments"][0]["referent_anchors"] = list(reversed(referents))
    second = ClaimInventoryItem.model_validate(payload)

    bound_first = bind_claim_inventory(
        (first,),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        chunk_index=0,
    )[0]
    bound_second = bind_claim_inventory(
        (second,),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        chunk_index=0,
    )[0]

    assert bound_first.inventory_id == bound_second.inventory_id


def test_overlapping_or_missing_referent_anchor_fails_closed() -> None:
    source = "the factor responds."
    payload = _item(
        exact_span="the factor responds",
        cue="responds",
        event_type="TREATMENT_RESPONSE",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "the factor"),
            _argument("OTHER_ENTITY", "CONTEXT", "responds"),
        ],
    ).model_dump(mode="json")
    payload["arguments"][0]["referent_anchors"] = [
        {
            "mention_span": "factor",
            "left_context": "the ",
            "right_context": " responds",
        },
    ]
    overlapping = ClaimInventoryItem.model_validate(payload)
    payload["arguments"][0]["referent_anchors"] = [
        {
            "mention_span": "c-Myb",
            "left_context": "",
            "right_context": " acts",
        },
    ]
    missing = ClaimInventoryItem.model_validate(payload)

    for item in (overlapping, missing):
        result = bind_claim_inventory_items(
            (item,),
            source_text=source,
            source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            chunk_index=0,
        )
        assert result.accepted == ()
        assert len(result.rejected) == 1
        assert result.rejected[0].disposition.value == "ARGUMENT_MENTION_INVALID"
