"""Scientific projection and selection tests for the fresh V12 holdout."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
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
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.projection import (
    twelfth_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.selection import (
    select_twelfth_nested_event_holdout,
    twelfth_unit_identity,
)

_SOURCE = (
    "Regulation of Fas ligand expression and cell death by apoptosis-linked gene 4."
)


def _argument(
    role: str,
    event_role: str,
    exact_span: str,
    *,
    controlled_event_ref: str | None = None,
) -> dict[str, object]:
    return {
        "role": role,
        "event_role": event_role,
        "exact_span": exact_span,
        "mention_anchors": [],
        "referent_anchors": [],
        "controlled_event_ref": controlled_event_ref,
        "role_rationale": "The title explicitly assigns this event-local role.",
    }


def _event(
    *,
    local_event_id: str,
    event_type: str,
    cue: str,
    arguments: list[dict[str, object]],
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
            "polarity": "UNSCOPED" if controlled_target else "SUPPORT",
            "epistemic_status": "UNASSERTED" if controlled_target else "ASSERTED",
            "local_event_id": local_event_id,
            "inventory_rationale": "The title explicitly reports this regulation.",
        }
    )


def _bind(items: tuple[ClaimInventoryItem, ...]) -> tuple[BoundClaimInventoryItem, ...]:
    return bind_claim_inventory(
        items,
        source_text=_SOURCE,
        source_sha256=hashlib.sha256(_SOURCE.encode()).hexdigest(),
        chunk_index=0,
    )


def _expression_target() -> ClaimInventoryItem:
    return _event(
        local_event_id="expression-target",
        event_type="EXPRESSION",
        cue="expression",
        controlled_target=True,
        arguments=[_argument("GENE_OR_PROTEIN", "THEME", "Fas ligand")],
    )


def _death_target() -> ClaimInventoryItem:
    return _event(
        local_event_id="death-target",
        event_type="OTHER_EXPLICIT",
        cue="cell death",
        controlled_target=True,
        arguments=[_argument("OUTCOME", "THEME", "cell death")],
    )


def _controller(
    local_event_id: str,
    target_span: str,
    target_id: str,
) -> ClaimInventoryItem:
    return _event(
        local_event_id=local_event_id,
        event_type="REGULATION",
        cue="Regulation",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "apoptosis-linked gene 4"),
            _argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                target_span,
                controlled_event_ref=target_id,
            ),
        ],
    )


def _nested_split_inventory() -> tuple[BoundClaimInventoryItem, ...]:
    return _bind(
        (
            _controller(
                "expression-regulation",
                "Fas ligand expression",
                "expression-target",
            ),
            _controller("death-regulation", "cell death", "death-target"),
            _expression_target(),
            _death_target(),
        )
    )


def _nested_joint_inventory() -> tuple[BoundClaimInventoryItem, ...]:
    controller = _event(
        local_event_id="joint-regulation",
        event_type="REGULATION",
        cue="Regulation",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "apoptosis-linked gene 4"),
            _argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                "Fas ligand expression",
                controlled_event_ref="expression-target",
            ),
            _argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                "cell death",
                controlled_event_ref="death-target",
            ),
        ],
    )
    return _bind((controller, _expression_target(), _death_target()))


def _direct_expression() -> ClaimInventoryItem:
    return _event(
        local_event_id="direct-expression",
        event_type="REGULATION",
        cue="Regulation",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "apoptosis-linked gene 4"),
            _argument("GENE_OR_PROTEIN", "THEME", "Fas ligand"),
            _argument("OUTCOME", "EFFECT", "Fas ligand expression"),
        ],
    )


def _direct_death() -> ClaimInventoryItem:
    return _event(
        local_event_id="direct-death",
        event_type="REGULATION",
        cue="Regulation",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "apoptosis-linked gene 4"),
            _argument("OUTCOME", "EFFECT", "cell death"),
        ],
    )


@pytest.mark.parametrize(
    ("trusted_factory", "expected_projection"),
    [
        (_nested_split_inventory, "source-complete-split-nested-regulation"),
        (_nested_joint_inventory, "source-complete-joint-nested-regulation"),
        (
            lambda: _bind((_direct_expression(), _direct_death())),
            "source-complete-split-direct-regulation",
        ),
        (
            lambda: _bind(
                (
                    _event(
                        local_event_id="joint-direct",
                        event_type="REGULATION",
                        cue="Regulation",
                        arguments=[
                            _argument(
                                "GENE_OR_PROTEIN",
                                "CAUSE",
                                "apoptosis-linked gene 4",
                            ),
                            _argument("GENE_OR_PROTEIN", "THEME", "Fas ligand"),
                            _argument("OUTCOME", "EFFECT", "Fas ligand expression"),
                            _argument("OUTCOME", "EFFECT", "cell death"),
                        ],
                    ),
                )
            ),
            "source-complete-joint-direct-regulation",
        ),
    ],
)
def test_v12_complete_representation_families_recover_exactly_one_projection(
    trusted_factory: Callable[[], tuple[BoundClaimInventoryItem, ...]],
    expected_projection: str,
) -> None:
    trusted = trusted_factory()
    links = link_controlled_events(trusted)

    result = match_projection_set(
        projection_set=twelfth_projection_set(),
        trusted=trusted,
        links=links.links,
    )

    assert links.ambiguities == ()
    assert result.fully_recovered_projection_ids == (expected_projection,)
    assert len(result.fully_recovered_inventory_ids) == len(trusted)


def test_v12_corpus_partial_graph_cannot_qualify_without_cell_death() -> None:
    trusted = _bind(
        (
            _controller(
                "expression-regulation",
                "Fas ligand expression",
                "expression-target",
            ),
            _expression_target(),
        )
    )
    links = link_controlled_events(trusted)

    result = match_projection_set(
        projection_set=twelfth_projection_set(),
        trusted=trusted,
        links=links.links,
    )

    assert result.fully_recovered_projection_ids == ()
    assert result.fully_recovered_inventory_ids == ()


def test_v12_direct_claim_cannot_qualify_without_cell_death() -> None:
    result = match_projection_set(
        projection_set=twelfth_projection_set(),
        trusted=_bind((_direct_expression(),)),
        links=(),
    )

    assert result.fully_recovered_projection_ids == ()


def test_v12_direct_claim_cannot_hide_fas_ligand_inside_outcome_text() -> None:
    event = _event(
        local_event_id="lossy-direct",
        event_type="REGULATION",
        cue="Regulation",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "apoptosis-linked gene 4"),
            _argument("OUTCOME", "EFFECT", "Fas ligand expression"),
            _argument("OUTCOME", "EFFECT", "cell death"),
        ],
    )

    result = match_projection_set(
        projection_set=twelfth_projection_set(),
        trusted=_bind((event,)),
        links=(),
    )

    assert result.fully_recovered_projection_ids == ()


def test_twelfth_selection_is_frozen_before_luna() -> None:
    corpus = os.getenv("ARTANA_TG04_BIONLP_CORPUS_ROOT")
    if corpus is None:
        pytest.skip("set ARTANA_TG04_BIONLP_CORPUS_ROOT for corpus-integrity test")

    selection = select_twelfth_nested_event_holdout(
        corpus_root=Path(corpus),
        archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
    )

    assert selection.trial_generation == 12
    assert selection.expected_eligibility_category.value == "FINDING"
    assert selection.candidate_unit_count == 44
    assert selection.expert_graph_sha256 == (
        "2ed9270cd4baae75ca69bb4308dd03d9fdc5b7ee0931fa9d6e7d2756cd708878"
    )
    assert selection.projection_set_sha256 == (
        "7fefffec28dbfe70ce743afcdc413ca50f56d0093adfbc08f45014679693ef49"
    )
    assert twelfth_unit_identity() == {
        "case_id": selection.case_id,
        "unit_id": selection.unit.unit_id,
        "unit_index": selection.unit.index,
        "source_start": selection.unit.source_start,
        "source_end": selection.unit.source_end,
        "source_sha256": selection.unit.source_sha256,
        "input_sha256": selection.unit.input_sha256,
    }
