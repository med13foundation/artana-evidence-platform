"""Regression tests for the pre-registered V11 scientific contract."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    ClaimInventoryItem,
    bind_claim_inventory,
    link_controlled_events,
)

from scripts.validation.claim_events.bionlp_import import TG04_BIONLP_ARCHIVE_SHA256
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.matching import (
    match_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.projection import (
    V11_EVENT_CONTEXT_SCOPE_MATRIX,
    V11_TRIGGER_EQUIVALENCE,
    V11EventScope,
    eleventh_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.selection import (
    eleventh_unit_identity,
    select_eleventh_nested_event_holdout,
)

_SOURCE = (
    "Fig. S6 shows that endogenous IL-4 and IFN-gamma do not effect Foxp3 "
    "expression in naive CD4+ T cells of CbfbF/F CD4-cre and CbfbF/F control "
    "mice, which were stimulated with anti-CD3 and anti-CD28 mAbs, IL-2 and "
    "TGF-beta in the absence or presence of anti-IL-4 and anti-IFN-gamma "
    "neutralizing mAbs."
)
_SOURCE_START = 19662


def _argument(
    role: str,
    event_role: str,
    exact_span: str,
    *,
    controlled_event_ref: str | None = None,
) -> dict[str, object]:
    mention_anchors: list[dict[str, str]] = []
    if exact_span == "IL-4":
        mention_anchors.append(
            {
                "mention_span": "IL-4",
                "left_context": "endogenous ",
                "right_context": " and IFN-gamma",
            }
        )
    elif exact_span == "IFN-gamma":
        mention_anchors.append(
            {
                "mention_span": "IFN-gamma",
                "left_context": "IL-4 and ",
                "right_context": " do not effect",
            }
        )
    return {
        "role": role,
        "event_role": event_role,
        "exact_span": exact_span,
        "mention_anchors": mention_anchors,
        "referent_anchors": [],
        "controlled_event_ref": controlled_event_ref,
        "role_rationale": "The source explicitly assigns this event-local role.",
    }


def _item(
    *,
    cue: str,
    event_type: str,
    arguments: list[dict[str, object]],
    local_event_id: str,
    controlled_target: bool = False,
) -> ClaimInventoryItem:
    return ClaimInventoryItem.model_validate(
        {
            "exact_span": _SOURCE,
            "relation_cue_span": cue,
            "arguments": arguments,
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": event_type,
            "assertion_scope": (
                "CONTROLLED_TARGET" if controlled_target else "SOURCE_ASSERTED"
            ),
            "polarity": "UNSCOPED" if controlled_target else "NULL_RESULT",
            "epistemic_status": "UNASSERTED" if controlled_target else "ASSERTED",
            "local_event_id": local_event_id,
            "inventory_rationale": "The source explicitly reports this null event.",
        }
    )


def _common_context() -> list[dict[str, object]]:
    return [
        _argument("POPULATION", "CONTEXT", "naive CD4+ T cells"),
        _argument("VARIANT", "CONTEXT", "CbfbF/F CD4-cre"),
        _argument("VARIANT", "CONTEXT", "CbfbF/F control mice"),
    ]


def _endogenous_context() -> list[dict[str, object]]:
    return [_argument("CONDITION", "CONTEXT", "endogenous")]


def _experimental_context() -> list[dict[str, object]]:
    return [
        _argument("INTERVENTION", "CONTEXT", "anti-CD3 and anti-CD28 mAbs"),
        _argument("INTERVENTION", "CONTEXT", "IL-2"),
        _argument("INTERVENTION", "CONTEXT", "TGF-beta"),
        _argument(
            "CONDITION",
            "CONTEXT",
            "in the absence or presence of anti-IL-4 and anti-IFN-gamma "
            "neutralizing mAbs",
        ),
        _argument(
            "INTERVENTION",
            "CONTEXT",
            "anti-IL-4 and anti-IFN-gamma neutralizing mAbs",
        ),
    ]


def _bind(items: tuple[ClaimInventoryItem, ...]) -> tuple[BoundClaimInventoryItem, ...]:
    return bind_claim_inventory(
        items,
        source_text=_SOURCE,
        source_sha256=hashlib.sha256(_SOURCE.encode()).hexdigest(),
        chunk_index=141,
        source_start_offset=_SOURCE_START,
    )


def _nested_inventory(
    *,
    cue: str = "effect",
    include_tgfb_on_controlled_target: bool = True,
) -> tuple[BoundClaimInventoryItem, ...]:
    outer_context = [
        *_endogenous_context(),
        *_common_context(),
        *_experimental_context(),
    ]
    controlled_target_context = _experimental_context()
    if not include_tgfb_on_controlled_target:
        controlled_target_context = [
            argument
            for argument in controlled_target_context
            if argument["exact_span"] != "TGF-beta"
        ]
    events = (
        _item(
            cue=cue,
            event_type="REGULATION",
            local_event_id="il4-regulation",
            arguments=[
                _argument("GENE_OR_PROTEIN", "CAUSE", "IL-4"),
                _argument(
                    "BIOLOGICAL_PROCESS",
                    "THEME",
                    "Foxp3 expression",
                    controlled_event_ref="foxp3-expression",
                ),
                *outer_context,
            ],
        ),
        _item(
            cue=cue,
            event_type="REGULATION",
            local_event_id="ifng-regulation",
            arguments=[
                _argument("GENE_OR_PROTEIN", "CAUSE", "IFN-gamma"),
                _argument(
                    "BIOLOGICAL_PROCESS",
                    "THEME",
                    "Foxp3 expression",
                    controlled_event_ref="foxp3-expression",
                ),
                *outer_context,
            ],
        ),
        _item(
            cue="expression",
            event_type="EXPRESSION",
            local_event_id="foxp3-expression",
            controlled_target=True,
            arguments=[
                _argument("GENE_OR_PROTEIN", "THEME", "Foxp3"),
                *_common_context(),
                *controlled_target_context,
            ],
        ),
    )
    return _bind(events)


def _direct_inventory(
    *,
    cue: str = "not effect",
    split: bool,
    include_tgfb: bool = True,
    include_endogenous: bool = True,
) -> tuple[BoundClaimInventoryItem, ...]:
    context = [
        *_endogenous_context(),
        *_common_context(),
        *_experimental_context(),
    ]
    if not include_tgfb:
        context = [
            argument for argument in context if argument["exact_span"] != "TGF-beta"
        ]
    if not include_endogenous:
        context = [
            argument for argument in context if argument["exact_span"] != "endogenous"
        ]

    def direct(event_id: str, agents: tuple[str, ...]) -> ClaimInventoryItem:
        return _item(
            cue=cue,
            event_type="NO_EFFECT",
            local_event_id=event_id,
            arguments=[
                *(_argument("GENE_OR_PROTEIN", "AGENT", agent) for agent in agents),
                _argument("GENE_OR_PROTEIN", "THEME", "Foxp3"),
                _argument("OUTCOME", "EFFECT", "Foxp3 expression"),
                *context,
            ],
        )

    items = (
        (
            direct("il4-direct", ("IL-4",)),
            direct("ifng-direct", ("IFN-gamma",)),
        )
        if split
        else (direct("joint-direct", ("IL-4", "IFN-gamma")),)
    )
    return _bind(items)


@pytest.mark.parametrize("cue", ["effect", "not effect", "do not effect"])
def test_eleventh_nested_projection_accepts_preregistered_surface_cues(
    cue: str,
) -> None:
    trusted = _nested_inventory(cue=cue)
    links = link_controlled_events(trusted)

    result = match_projection_set(
        projection_set=eleventh_projection_set(),
        trusted=trusted,
        links=links.links,
    )

    assert links.ambiguities == ()
    assert result.fully_recovered_projection_ids == (
        "bionlp-shared-expression-null-regulation",
    )
    assert len(result.fully_recovered_inventory_ids) == 3


@pytest.mark.parametrize(
    ("split", "expected"),
    [
        (False, "source-only-joint-direct-null-effect"),
        (True, "source-only-split-direct-null-effect"),
    ],
)
@pytest.mark.parametrize("cue", ["effect", "not effect", "do not effect"])
def test_eleventh_direct_families_accept_preregistered_surface_cues(
    *,
    split: bool,
    expected: str,
    cue: str,
) -> None:
    trusted = _direct_inventory(split=split, cue=cue)

    result = match_projection_set(
        projection_set=eleventh_projection_set(),
        trusted=trusted,
        links=(),
    )

    assert result.fully_recovered_projection_ids == (expected,)
    assert len(result.fully_recovered_inventory_ids) == (2 if split else 1)


def test_eleventh_context_scope_matrix_is_explicit() -> None:
    decisions = {
        decision.context_id: decision for decision in V11_EVENT_CONTEXT_SCOPE_MATRIX
    }

    assert decisions["population"].event_scopes == frozenset(V11EventScope)
    assert decisions["cd4_cre_variant"].event_scopes == frozenset(V11EventScope)
    assert decisions["control_variant"].event_scopes == frozenset(V11EventScope)
    assert decisions["tcr_stimulation"].event_scopes == frozenset(V11EventScope)
    assert decisions["endogenous_agent_qualifier"].event_scopes == frozenset(
        {V11EventScope.REGULATION, V11EventScope.DIRECT}
    )
    assert tuple(span.exact for span in V11_TRIGGER_EQUIVALENCE) == (
        "effect",
        "not effect",
        "do not effect",
    )


def test_eleventh_projection_rejects_material_context_loss() -> None:
    trusted = _direct_inventory(split=False, include_tgfb=False)

    result = match_projection_set(
        projection_set=eleventh_projection_set(),
        trusted=trusted,
        links=(),
    )

    assert result.fully_recovered_projection_ids == ()
    assert result.fully_recovered_inventory_ids == ()


def test_eleventh_projection_rejects_endogenous_qualifier_loss() -> None:
    trusted = _direct_inventory(split=False, include_endogenous=False)

    result = match_projection_set(
        projection_set=eleventh_projection_set(),
        trusted=trusted,
        links=(),
    )

    assert result.fully_recovered_projection_ids == ()


def test_eleventh_nested_projection_rejects_context_loss_on_controlled_target() -> None:
    trusted = _nested_inventory(include_tgfb_on_controlled_target=False)
    links = link_controlled_events(trusted)

    result = match_projection_set(
        projection_set=eleventh_projection_set(),
        trusted=trusted,
        links=links.links,
    )

    assert links.ambiguities == ()
    assert result.fully_recovered_projection_ids == ()
    assert result.fully_recovered_inventory_ids == ()


def test_eleventh_mixed_complete_families_receive_no_inventory_credit() -> None:
    nested = _nested_inventory()
    direct = _direct_inventory(split=False)
    trusted = (*nested, *direct)
    links = link_controlled_events(trusted)

    result = match_projection_set(
        projection_set=eleventh_projection_set(),
        trusted=trusted,
        links=links.links,
    )

    assert set(result.fully_recovered_projection_ids) == {
        "bionlp-shared-expression-null-regulation",
        "source-only-joint-direct-null-effect",
    }
    assert result.fully_recovered_inventory_ids == ()


def test_eleventh_selection_is_frozen_before_luna() -> None:
    corpus = os.getenv("ARTANA_TG04_BIONLP_CORPUS_ROOT")
    if corpus is None:
        pytest.skip("set ARTANA_TG04_BIONLP_CORPUS_ROOT for corpus-integrity test")

    selection = select_eleventh_nested_event_holdout(
        corpus_root=Path(corpus),
        archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
    )

    assert selection.trial_generation == 11
    assert selection.unit.index == 141
    assert selection.candidate_unit_count == 1
    assert selection.expert_graph_sha256 == (
        "a77aa47edb35008c9149e9ab92bc0f01dce32510c92e1adb4b2bbca8df310a15"
    )
    assert selection.projection_set_sha256 == (
        "e74d4cce878d1e6894bbd82345f438df437bddfbe8663bb26f91b161ce687f1a"
    )
    assert eleventh_unit_identity() == {
        "case_id": selection.case_id,
        "unit_id": selection.unit.unit_id,
        "unit_index": selection.unit.index,
        "source_start": selection.unit.source_start,
        "source_end": selection.unit.source_end,
        "source_sha256": selection.unit.source_sha256,
        "input_sha256": selection.unit.input_sha256,
    }
