"""Regression tests for the pre-registered V10 scientific contract."""

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
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.matching import (
    match_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.projection import (
    V10_EVENT_CONTEXT_SCOPE_MATRIX,
    V10EventScope,
    tenth_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.prompts import (
    v10_source_unit_extraction_prompt,
    v10_source_unit_verification_prompt,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.selection import (
    select_tenth_nested_event_holdout,
    tenth_unit_identity,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)

_SOURCE = (
    "Similarly pre-existing iTreg cells did not decrease FOXP3 expression upon "
    "IL-4 exposure (Figure S3B)."
)
_SOURCE_START = 2622


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
        "role_rationale": "The source explicitly assigns this event-local role.",
    }


def _item(
    *,
    cue: str,
    event_type: str,
    arguments: list[dict[str, object]],
    local_event_id: str,
    controlled_target: bool = False,
    polarity: str = "NULL_RESULT",
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
            "polarity": "UNSCOPED" if controlled_target else polarity,
            "epistemic_status": "UNASSERTED" if controlled_target else "ASSERTED",
            "local_event_id": local_event_id,
            "inventory_rationale": "The source explicitly reports this null event.",
        }
    )


def _nested_inventory(
    *,
    cue: str = "decrease",
    inner_event_type: str = "EXPRESSION",
    include_outer_exposure_context: bool = True,
    include_inner_exposure_context: bool = False,
    include_separate_pre_existing_state: bool = False,
) -> tuple[BoundClaimInventoryItem, ...]:
    outer_arguments = [
        _argument("GENE_OR_PROTEIN", "CAUSE", "IL-4"),
        _argument(
            "BIOLOGICAL_PROCESS",
            "THEME",
            "FOXP3 expression",
            controlled_event_ref="v10-expression",
        ),
        _argument("POPULATION", "CONTEXT", "pre-existing iTreg cells"),
    ]
    inner_arguments = [
        _argument("GENE_OR_PROTEIN", "THEME", "FOXP3"),
        _argument("POPULATION", "CONTEXT", "pre-existing iTreg cells"),
    ]
    if include_outer_exposure_context:
        outer_arguments.append(_argument("EXPOSURE", "CONTEXT", "IL-4 exposure"))
        outer_arguments.append(_argument("TIMEFRAME", "CONTEXT", "upon IL-4 exposure"))
    if include_inner_exposure_context:
        inner_arguments.append(_argument("EXPOSURE", "CONTEXT", "IL-4 exposure"))
        inner_arguments.append(_argument("TIMEFRAME", "CONTEXT", "upon IL-4 exposure"))
    if include_separate_pre_existing_state:
        outer_arguments.append(_argument("TIMEFRAME", "CONTEXT", "pre-existing"))
        inner_arguments.append(_argument("TIMEFRAME", "CONTEXT", "pre-existing"))
    items = (
        _item(
            cue=cue,
            event_type="NEGATIVE_REGULATION",
            arguments=outer_arguments,
            local_event_id="v10-outer",
        ),
        _item(
            cue="expression",
            event_type=inner_event_type,
            arguments=inner_arguments,
            local_event_id="v10-expression",
            controlled_target=True,
        ),
    )
    return bind_claim_inventory(
        items,
        source_text=_SOURCE,
        source_sha256=hashlib.sha256(_SOURCE.encode()).hexdigest(),
        chunk_index=17,
        source_start_offset=_SOURCE_START,
    )


def _direct_inventory(
    *,
    cue: str = "not decrease",
    event_type: str = "DECREASE",
    process_role: str = "OUTCOME",
    include_cause: bool = False,
    include_population: bool = True,
    include_separate_pre_existing_state: bool = False,
    polarity: str = "NULL_RESULT",
) -> tuple[BoundClaimInventoryItem, ...]:
    arguments = [
        _argument("GENE_OR_PROTEIN", "THEME", "FOXP3"),
        _argument(process_role, "EFFECT", "FOXP3 expression"),
        _argument("EXPOSURE", "CONTEXT", "IL-4 exposure"),
        _argument("TIMEFRAME", "CONTEXT", "upon IL-4 exposure"),
    ]
    if include_cause:
        arguments.insert(0, _argument("GENE_OR_PROTEIN", "CAUSE", "IL-4"))
    if include_population:
        arguments.append(_argument("POPULATION", "CONTEXT", "pre-existing iTreg cells"))
    if include_separate_pre_existing_state:
        arguments.append(_argument("TIMEFRAME", "CONTEXT", "pre-existing"))
    item = _item(
        cue=cue,
        event_type=event_type,
        local_event_id="v10-direct",
        arguments=arguments,
        polarity=polarity,
    )
    return bind_claim_inventory(
        (item,),
        source_text=_SOURCE,
        source_sha256=hashlib.sha256(_SOURCE.encode()).hexdigest(),
        chunk_index=17,
        source_start_offset=_SOURCE_START,
    )


def test_tenth_bionlp_projection_accepts_only_corpus_native_cue() -> None:
    trusted = _nested_inventory()
    links = link_controlled_events(trusted)

    result = match_projection_set(
        projection_set=tenth_projection_set(),
        trusted=trusted,
        links=links.links,
    )

    assert links.ambiguities == ()
    assert result.fully_recovered_projection_ids == ("bionlp-nested-null-decrease",)
    assert len(result.fully_recovered_inventory_ids) == 2


def test_tenth_source_only_noncausal_projection_is_credited() -> None:
    trusted = _direct_inventory()

    result = match_projection_set(
        projection_set=tenth_projection_set(),
        trusted=trusted,
        links=(),
    )

    assert result.fully_recovered_projection_ids == (
        "source-only-noncausal-direct-null-decrease",
    )
    assert len(result.fully_recovered_inventory_ids) == 1


def test_tenth_context_scope_matrix_is_explicit_and_noninventive() -> None:
    decisions = {
        decision.context_id: decision for decision in V10_EVENT_CONTEXT_SCOPE_MATRIX
    }

    assert decisions["population_identity"].event_scopes == frozenset(V10EventScope)
    assert decisions["exposure"].event_scopes == frozenset(
        {
            V10EventScope.BIONLP_OUTER,
            V10EventScope.SOURCE_ONLY_DIRECT,
        }
    )
    assert decisions["exposure_timeframe"].event_scopes == (
        decisions["exposure"].event_scopes
    )
    pre_existing = decisions["pre_existing_state"]
    assert pre_existing.event_scopes == frozenset()
    assert pre_existing.participant_type is None
    assert pre_existing.event_role is None
    assert pre_existing.embedded_in_context_id == "population_identity"

    projection_set = tenth_projection_set()
    corpus_trigger = projection_set.canonical_projection.graph.events[0].trigger
    source_trigger = projection_set.projections[1].graph.events[0].trigger
    assert (
        corpus_trigger.exact_span,
        corpus_trigger.source_start,
        corpus_trigger.source_end,
    ) == ("decrease", 2665, 2673)
    assert (
        source_trigger.exact_span,
        source_trigger.source_start,
        source_trigger.source_end,
    ) == ("not decrease", 2661, 2673)


def test_tenth_prompt_policy_matches_context_scope_matrix() -> None:
    unit = FrozenSourceUnit(
        unit_id="source-unit-v10-prompt-regression",
        index=17,
        source_start=_SOURCE_START,
        source_end=_SOURCE_START + len(_SOURCE),
        text=_SOURCE,
        source_sha256=hashlib.sha256(_SOURCE.encode()).hexdigest(),
    )
    extraction = v10_source_unit_extraction_prompt(unit)
    verification = v10_source_unit_verification_prompt(unit=unit, candidates=())
    normalized_verification = " ".join(verification.split())

    assert "Scope context event by event" in extraction
    assert "Do not copy an outer exposure or timeframe" in extraction
    assert "remains part of that population identity" in extraction
    assert "Do not require outer-only exposure or timeframe" in normalized_verification
    assert "invented temporal argument" in normalized_verification


@pytest.mark.parametrize("cue", ["not decrease", "did not decrease"])
def test_tenth_bionlp_projection_rejects_source_only_cues(cue: str) -> None:
    trusted = _nested_inventory(cue=cue)
    links = link_controlled_events(trusted)

    result = match_projection_set(
        projection_set=tenth_projection_set(),
        trusted=trusted,
        links=links.links,
    )

    assert result.fully_recovered_projection_ids == ()
    assert result.fully_recovered_inventory_ids == ()


@pytest.mark.parametrize("cue", ["decrease", "did not decrease"])
def test_tenth_source_only_projection_requires_shortest_material_negation(
    cue: str,
) -> None:
    trusted = _direct_inventory(cue=cue)

    result = match_projection_set(
        projection_set=tenth_projection_set(),
        trusted=trusted,
        links=(),
    )

    assert result.fully_recovered_projection_ids == ()
    assert result.fully_recovered_inventory_ids == ()


@pytest.mark.parametrize(
    "trusted",
    [
        _direct_inventory(
            event_type="NEGATIVE_REGULATION",
            include_cause=True,
        ),
        _direct_inventory(process_role="BIOLOGICAL_PROCESS"),
        _direct_inventory(include_population=False),
        _direct_inventory(include_separate_pre_existing_state=True),
        _direct_inventory(polarity="SUPPORT"),
    ],
)
def test_tenth_source_only_projection_rejects_causal_type_and_context_drift(
    trusted: tuple[BoundClaimInventoryItem, ...],
) -> None:
    result = match_projection_set(
        projection_set=tenth_projection_set(),
        trusted=trusted,
        links=(),
    )

    assert result.fully_recovered_projection_ids == ()
    assert result.fully_recovered_inventory_ids == ()


def test_tenth_mixed_complete_representation_families_receive_no_credit() -> None:
    nested = _nested_inventory()
    direct = _direct_inventory()
    trusted = (*nested, *direct)
    links = link_controlled_events(trusted)

    result = match_projection_set(
        projection_set=tenth_projection_set(),
        trusted=trusted,
        links=links.links,
    )

    assert result.fully_recovered_projection_ids == (
        "bionlp-nested-null-decrease",
        "source-only-noncausal-direct-null-decrease",
    )
    assert result.fully_recovered_inventory_ids == ()


@pytest.mark.parametrize(
    ("trusted", "expected_link_count"),
    [
        (_nested_inventory(include_outer_exposure_context=False), 1),
        (_nested_inventory(include_inner_exposure_context=True), 1),
        (_nested_inventory(include_separate_pre_existing_state=True), 1),
        (_nested_inventory(inner_event_type="OTHER_EXPLICIT"), 1),
        (_nested_inventory(cue="did not decrease FOXP3"), 1),
    ],
)
def test_tenth_projection_rejects_context_type_and_unsealed_cue_loss(
    trusted: tuple[BoundClaimInventoryItem, ...],
    expected_link_count: int,
) -> None:
    links = link_controlled_events(trusted)

    result = match_projection_set(
        projection_set=tenth_projection_set(),
        trusted=trusted,
        links=links.links,
    )

    assert len(links.links) == expected_link_count
    assert result.fully_recovered_projection_ids == ()
    assert result.fully_recovered_inventory_ids == ()


def test_tenth_selection_is_frozen_before_luna() -> None:
    corpus = os.getenv("ARTANA_TG04_BIONLP_CORPUS_ROOT")
    if corpus is None:
        pytest.skip("set ARTANA_TG04_BIONLP_CORPUS_ROOT for corpus-integrity test")

    selection = select_tenth_nested_event_holdout(
        corpus_root=Path(corpus),
        archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
    )

    assert selection.trial_generation == 10
    assert selection.case_id == ("bionlp-ge-2011-holdout:PMC-2222968-04-Results-03")
    assert selection.unit.index == 17
    assert selection.candidate_unit_count == 3
    assert "PMID-8622948" in selection.excluded_document_ids
    assert selection.expert_graph_sha256 == (
        "ddd564c4fc7a431358df7f193c4b0284ff5dcebc87a4fd6ce6f61d6b29f28cc5"
    )
    assert selection.projection_set_sha256 == (
        "4f6add86982fe4eabb9df893ee71af9b8cce60aa1b280d18edff9598004821cd"
    )
    assert selection.expected_eligibility_category is (
        SourceUnitEligibilityCategory.NULL_RESULT
    )
    assert tenth_unit_identity() == {
        "case_id": selection.case_id,
        "unit_id": selection.unit.unit_id,
        "unit_index": selection.unit.index,
        "source_start": selection.unit.source_start,
        "source_end": selection.unit.source_end,
        "source_sha256": selection.unit.source_sha256,
        "input_sha256": selection.unit.input_sha256,
    }
