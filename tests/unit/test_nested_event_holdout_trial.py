"""Tests for the pre-registered hidden nested-event trial."""

from __future__ import annotations

import hashlib
import inspect
import os
from dataclasses import replace
from pathlib import Path

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    BoundControlledEventLink,
    ClaimEventRole,
    ClaimInventoryItem,
    ClaimKind,
    InventoryEpistemicStatus,
    InventoryPolarity,
    bind_claim_inventory,
    link_controlled_events,
)

from scripts.run_fourth_nested_event_holdout_trial import (
    fourth_nested_holdout_exit_code,
)
from scripts.run_nested_event_holdout_trial import nested_holdout_trial_exit_code
from scripts.run_second_nested_event_holdout_trial import (
    second_nested_holdout_exit_code,
)
from scripts.run_third_nested_event_holdout_trial import third_nested_holdout_exit_code
from scripts.validation.claim_events.bionlp_import import TG04_BIONLP_ARCHIVE_SHA256
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.corpus import (
    verified_corpus_root,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.fourth_selection import (
    _projection_set as fourth_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.fourth_selection import (
    select_fourth_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.gate import (
    NestedHoldoutGateInputs,
    nested_holdout_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.matching import (
    match_nested_event_graph,
    match_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.second_selection import (
    select_second_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
    CompleteGraphSelectionProfile,
    ProjectionProvenance,
    SealedArgument,
    SealedEvent,
    SealedEventLink,
    SealedEventSemantics,
    SealedGraphProjection,
    SealedNestedEventGraph,
    SealedProjectionSet,
    SealedTrigger,
    canonical_projection_set,
    enumerate_complete_event_graph_candidates,
    select_nested_event_holdout,
    validate_sealed_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.third_selection import (
    select_third_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    _binding_repair_prompt,
    _extraction_prompt,
    _verification_prompt,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)

_SOURCE = (
    "ZEB blocks the activity of c-Myb and Ets individually, but together the "
    "factors synergize to resist this repression."
)
_SOURCE_OFFSET = 770
_NULL_SOURCE = (
    "However, we did not observe any significant changes in the level of "
    "phospho-STAT3 or phospho-p38 upon BMP-6 treatment of B cells (data not shown)."
)
_NULL_SOURCE_OFFSET = 1022
_MULTI_LINK_SOURCE = (
    "Thus, although CD3, CD28, and CD2 activate many of the same signaling "
    "molecules, they differed in their capacity to induce the tyrosine "
    "phosphorylation of HSI."
)
_MULTI_LINK_SOURCE_OFFSET = 1593
_POPULATION_CONTRAST_SOURCE = (
    "Another publication describes an enhanced expression of A3G after IFN-alpha "
    "treatment in resting primary CD4 T cells, but not in activated T cells (53)."
)
_POPULATION_CONTRAST_OFFSET = 3398


def _argument(role: str, event_role: str, exact_span: str) -> dict[str, object]:
    return {
        "role": role,
        "event_role": event_role,
        "exact_span": exact_span,
        "role_rationale": "The source explicitly assigns this role.",
    }


def _item(
    *,
    exact_span: str,
    cue: str,
    arguments: list[dict[str, object]],
    event_type: str = "NEGATIVE_REGULATION",
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


def _trusted_inventory(*, wrong_outer_cause: bool = False):
    inner = _item(
        exact_span="ZEB blocks the activity of c-Myb",
        cue="blocks",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "ZEB"),
            _argument("GENE_OR_PROTEIN", "THEME", "c-Myb"),
        ],
    )
    outer_cause = "Ets" if wrong_outer_cause else "c-Myb"
    outer = _item(
        exact_span=_SOURCE,
        cue="synergize to resist",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", outer_cause),
            _argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                "ZEB blocks the activity of c-Myb",
            ),
        ],
    )
    return bind_claim_inventory(
        (inner, outer),
        source_text=_SOURCE,
        source_sha256=hashlib.sha256(_SOURCE.encode()).hexdigest(),
        chunk_index=6,
        source_start_offset=_SOURCE_OFFSET,
    )


def _sealed_graph() -> SealedNestedEventGraph:
    return SealedNestedEventGraph(
        events=(
            SealedEvent(
                event_id="E2",
                event_type="NEGATIVE_REGULATION",
                trigger=SealedTrigger("blocks", 774, 780),
                arguments=(
                    SealedArgument("CAUSE", "T6", "GENE_OR_PROTEIN", "ZEB", 770, 773),
                    SealedArgument(
                        "THEME",
                        "T7",
                        "GENE_OR_PROTEIN",
                        "c-Myb",
                        797,
                        802,
                    ),
                ),
            ),
            SealedEvent(
                event_id="E3",
                event_type="NEGATIVE_REGULATION",
                trigger=SealedTrigger("synergize to resist", 850, 869),
                arguments=(
                    SealedArgument(
                        "CAUSE",
                        "T7",
                        "GENE_OR_PROTEIN",
                        "c-Myb",
                        797,
                        802,
                    ),
                ),
            ),
        ),
        links=(SealedEventLink("E3", "THEME", "E2"),),
    )


def _projection_set(graph: SealedNestedEventGraph) -> SealedProjectionSet:
    return canonical_projection_set(
        graph,
        scientific_rationale="The complete source-supported nested graph.",
    )


def _frozen_test_unit() -> FrozenSourceUnit:
    return FrozenSourceUnit(
        unit_id="source-unit-projection-validation",
        index=6,
        source_start=_SOURCE_OFFSET,
        source_end=_SOURCE_OFFSET + len(_SOURCE),
        text=_SOURCE,
        source_sha256=hashlib.sha256(_SOURCE.encode()).hexdigest(),
    )


def _null_result_inventory(*, split_events: bool = True):
    def item(themes: tuple[str, ...]) -> ClaimInventoryItem:
        return ClaimInventoryItem.model_validate(
            {
                "exact_span": _NULL_SOURCE,
                "relation_cue_span": "changes",
                "arguments": [
                    _argument("GENE_OR_PROTEIN", "CAUSE", "BMP-6"),
                    *(_argument("BIOMARKER", "THEME", theme) for theme in themes),
                    _argument("POPULATION", "CONTEXT", "B cells"),
                ],
                "source_locator": "normalized_extraction_text",
                "claim_kind": "SCIENTIFIC_FINDING",
                "event_type": "REGULATION",
                "polarity": "NULL_RESULT",
                "epistemic_status": "ASSERTED",
                "inventory_rationale": "The source reports a null regulation result.",
            },
        )

    items = (
        (item(("phospho-STAT3",)), item(("phospho-p38",)))
        if split_events
        else (item(("phospho-STAT3", "phospho-p38")),)
    )
    return bind_claim_inventory(
        items,
        source_text=_NULL_SOURCE,
        source_sha256=hashlib.sha256(_NULL_SOURCE.encode()).hexdigest(),
        chunk_index=9,
        source_start_offset=_NULL_SOURCE_OFFSET,
    )


def _null_result_graph(*, split_events: bool = True) -> SealedNestedEventGraph:
    stat3 = SealedArgument(
        "THEME",
        "T14",
        "BIOMARKER",
        "phospho-STAT3",
        1090,
        1103,
    )
    p38 = SealedArgument(
        "THEME",
        "T15",
        "BIOMARKER",
        "phospho-p38",
        1107,
        1118,
    )
    themes = ((stat3,), (p38,)) if split_events else ((stat3, p38),)
    events = tuple(
        SealedEvent(
            event_id=f"SOURCE-NULL-{index}",
            event_type="REGULATION",
            trigger=SealedTrigger("changes", 1066, 1073),
            arguments=(
                SealedArgument(
                    "CAUSE",
                    "T16",
                    "GENE_OR_PROTEIN",
                    "BMP-6",
                    1124,
                    1129,
                ),
                *event_themes,
                SealedArgument(
                    "CONTEXT",
                    "SOURCE-POPULATION",
                    "POPULATION",
                    "B cells",
                    1143,
                    1150,
                ),
            ),
        )
        for index, event_themes in enumerate(themes, start=1)
    )
    return SealedNestedEventGraph(events=events, links=())


def _multi_link_inventory():
    inner = _item(
        exact_span="tyrosine phosphorylation of HSI",
        cue="phosphorylation",
        event_type="PHOSPHORYLATION",
        arguments=[
            _argument("OTHER_ENTITY", "SITE", "tyrosine"),
            _argument("GENE_OR_PROTEIN", "THEME", "HSI"),
        ],
    )
    process = _argument(
        "BIOLOGICAL_PROCESS",
        "THEME",
        "tyrosine phosphorylation of HSI",
    )
    cd28 = _item(
        exact_span=_MULTI_LINK_SOURCE,
        cue="induce",
        event_type="POSITIVE_REGULATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "CD28"),
            process,
        ],
    )
    cd2_argument = _argument("GENE_OR_PROTEIN", "CAUSE", "CD2")
    cd2_argument["mention_anchors"] = [
        {
            "mention_span": "CD2",
            "left_context": "and ",
            "right_context": " activate",
        },
    ]
    cd2 = _item(
        exact_span=_MULTI_LINK_SOURCE,
        cue="induce",
        event_type="POSITIVE_REGULATION",
        arguments=[cd2_argument, process],
    )
    return bind_claim_inventory(
        (cd28, cd2, inner),
        source_text=_MULTI_LINK_SOURCE,
        source_sha256=hashlib.sha256(_MULTI_LINK_SOURCE.encode()).hexdigest(),
        chunk_index=9,
        source_start_offset=_MULTI_LINK_SOURCE_OFFSET,
    )


def _multi_link_graph() -> SealedNestedEventGraph:
    inner = SealedEvent(
        event_id="E43",
        event_type="PHOSPHORYLATION",
        trigger=SealedTrigger("phosphorylation", 1729, 1744),
        arguments=(
            SealedArgument("SITE", "T63", "OTHER_ENTITY", "tyrosine", 1720, 1728),
            SealedArgument("THEME", "T32", "GENE_OR_PROTEIN", "HSI", 1748, 1751),
        ),
    )
    outers = tuple(
        SealedEvent(
            event_id=event_id,
            event_type="POSITIVE_REGULATION",
            trigger=SealedTrigger("induce", 1709, 1715),
            arguments=(
                SealedArgument(
                    "CAUSE",
                    reference_id,
                    "GENE_OR_PROTEIN",
                    span,
                    start,
                    start + len(span),
                ),
            ),
        )
        for event_id, reference_id, span, start in (
            ("E41", "T30", "CD28", 1613),
            ("E42", "T31", "CD2", 1623),
        )
    )
    return SealedNestedEventGraph(
        events=(*outers, inner),
        links=(
            SealedEventLink("E41", "THEME", "E43"),
            SealedEventLink("E42", "THEME", "E43"),
        ),
    )


def _population_contrast_inventory(
    *,
    cause_kind: str,
    cue: str,
    theme_shape: str = "entity",
):
    if cause_kind == "protein":
        cause = _argument("GENE_OR_PROTEIN", "CAUSE", "IFN-alpha")
    else:
        cause = _argument(
            {
                "process": "BIOLOGICAL_PROCESS",
                "intervention": "INTERVENTION",
                "exposure": "EXPOSURE",
            }[cause_kind],
            "CAUSE",
            "IFN-alpha treatment",
        )

    entity_theme = _argument("GENE_OR_PROTEIN", "THEME", "A3G")
    process_theme = _argument(
        "BIOLOGICAL_PROCESS",
        "THEME",
        "expression of A3G",
    )
    resting_reference_theme = _argument(
        "BIOLOGICAL_PROCESS",
        "THEME",
        "expression of A3G after IFN-alpha treatment in resting primary CD4 T cells",
    )
    outcome_theme = _argument("OUTCOME", "THEME", "expression of A3G")

    def item(
        *,
        population: str,
        polarity: str,
        theme: dict[str, object],
    ) -> ClaimInventoryItem:
        return ClaimInventoryItem.model_validate(
            {
                "exact_span": _POPULATION_CONTRAST_SOURCE,
                "relation_cue_span": cue,
                "relation_cue_anchor": (
                    {
                        "mention_span": "not",
                        "left_context": "cells, but ",
                        "right_context": " in activated T cells",
                    }
                    if cue == "not"
                    else None
                ),
                "arguments": [
                    cause,
                    theme,
                    _argument("POPULATION", "CONTEXT", population),
                ],
                "source_locator": "normalized_extraction_text",
                "claim_kind": "SCIENTIFIC_FINDING",
                "event_type": "POSITIVE_REGULATION",
                "polarity": polarity,
                "epistemic_status": "ASSERTED",
                "inventory_rationale": "The population-specific outcome is explicit.",
            },
        )

    resting_theme = (
        resting_reference_theme
        if theme_shape == "resting-decomposed"
        else process_theme
    )
    activated_theme = (
        outcome_theme if theme_shape == "resting-decomposed" else process_theme
    )
    contrast_items = (
        item(
            population="resting primary CD4 T cells",
            polarity="SUPPORT",
            theme=resting_theme,
        ),
        item(
            population="activated T cells",
            polarity="NULL_RESULT",
            theme=activated_theme,
        ),
    )
    expression_item = ClaimInventoryItem.model_validate(
        {
            "exact_span": _POPULATION_CONTRAST_SOURCE,
            "relation_cue_span": "expression",
            "arguments": [
                entity_theme,
                _argument(
                    "POPULATION",
                    "CONTEXT",
                    "resting primary CD4 T cells",
                ),
            ],
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "EXPRESSION",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "A3G expression is explicit in resting cells.",
        },
    )
    items = (
        (expression_item, *contrast_items)
        if theme_shape == "resting-decomposed"
        else contrast_items
    )
    return bind_claim_inventory(
        items,
        source_text=_POPULATION_CONTRAST_SOURCE,
        source_sha256=hashlib.sha256(_POPULATION_CONTRAST_SOURCE.encode()).hexdigest(),
        chunk_index=25,
        source_start_offset=_POPULATION_CONTRAST_OFFSET,
    )


def _observational_population_contrast_inventory() -> tuple[
    BoundClaimInventoryItem, ...
]:
    def item(*, population: str, cue: str, polarity: str) -> ClaimInventoryItem:
        return ClaimInventoryItem.model_validate(
            {
                "exact_span": _POPULATION_CONTRAST_SOURCE,
                "relation_cue_span": cue,
                "relation_cue_anchor": (
                    {
                        "mention_span": "not",
                        "left_context": "cells, but ",
                        "right_context": " in activated T cells",
                    }
                    if cue == "not"
                    else None
                ),
                "arguments": [
                    _argument("GENE_OR_PROTEIN", "THEME", "A3G"),
                    _argument(
                        "INTERVENTION",
                        "CONTEXT",
                        "IFN-alpha treatment",
                    ),
                    _argument(
                        "TIMEFRAME",
                        "CONTEXT",
                        "after IFN-alpha treatment",
                    ),
                    _argument("POPULATION", "CONTEXT", population),
                    *(
                        [
                            _argument(
                                "BIOLOGICAL_PROCESS",
                                "THEME",
                                "expression of A3G",
                            ),
                        ]
                        if cue == "not"
                        else []
                    ),
                ],
                "source_locator": "normalized_extraction_text",
                "claim_kind": "SCIENTIFIC_FINDING",
                "event_type": "INCREASE",
                "polarity": polarity,
                "epistemic_status": "ASSERTED",
                "inventory_rationale": "The source reports a contextual change.",
            },
        )

    return bind_claim_inventory(
        (
            item(
                population="resting primary CD4 T cells",
                cue="enhanced expression",
                polarity="SUPPORT",
            ),
            item(
                population="activated T cells",
                cue="not",
                polarity="NULL_RESULT",
            ),
        ),
        source_text=_POPULATION_CONTRAST_SOURCE,
        source_sha256=hashlib.sha256(_POPULATION_CONTRAST_SOURCE.encode()).hexdigest(),
        chunk_index=25,
        source_start_offset=_POPULATION_CONTRAST_OFFSET,
    )


def _observational_population_contrast_graph() -> SealedNestedEventGraph:
    theme = SealedArgument(
        "THEME",
        "T20",
        "GENE_OR_PROTEIN",
        "A3G",
        3454,
        3457,
    )
    intervention = SealedArgument(
        "CONTEXT",
        "SOURCE-INTERVENTION",
        "INTERVENTION",
        "IFN-alpha treatment",
        3464,
        3483,
    )
    timeframe = SealedArgument(
        "CONTEXT",
        "SOURCE-TIMEFRAME",
        "TIMEFRAME",
        "after IFN-alpha treatment",
        3458,
        3483,
    )
    return SealedNestedEventGraph(
        events=(
            SealedEvent(
                "SOURCE-RESTING",
                "INCREASE",
                SealedTrigger("enhanced expression", 3431, 3450),
                (
                    theme,
                    intervention,
                    timeframe,
                    SealedArgument(
                        "CONTEXT",
                        "SOURCE-RESTING-POPULATION",
                        "POPULATION",
                        "resting primary CD4 T cells",
                        3487,
                        3514,
                    ),
                ),
            ),
            SealedEvent(
                "SOURCE-ACTIVATED",
                "INCREASE",
                SealedTrigger("not", 3520, 3523),
                (
                    theme,
                    intervention,
                    timeframe,
                    SealedArgument(
                        "THEME",
                        "SOURCE-EXPRESSION-PROCESS",
                        "BIOLOGICAL_PROCESS",
                        "expression of A3G",
                        3440,
                        3457,
                    ),
                    SealedArgument(
                        "CONTEXT",
                        "SOURCE-ACTIVATED-POPULATION",
                        "POPULATION",
                        "activated T cells",
                        3527,
                        3544,
                    ),
                ),
            ),
        ),
        links=(),
    )


def _alternative_sealed_graph() -> SealedNestedEventGraph:
    graph = _sealed_graph()
    ets_start = _SOURCE_OFFSET + _SOURCE.index("Ets")
    ets = SealedArgument(
        "THEME",
        "T8",
        "GENE_OR_PROTEIN",
        "Ets",
        ets_start,
        ets_start + len("Ets"),
    )
    inner = replace(
        graph.events[0],
        arguments=(graph.events[0].arguments[0], ets),
    )
    outer = replace(
        graph.events[1],
        arguments=(replace(ets, event_role="CAUSE"),),
    )
    return SealedNestedEventGraph(events=(inner, outer), links=graph.links)


def _baseline_gate() -> NestedHoldoutGateInputs:
    return NestedHoldoutGateInputs(
        repeat_index=1,
        hidden_expert_event_count=2,
        hidden_expert_link_count=1,
        expected_eligibility_category=SourceUnitEligibilityCategory.FINDING,
        agent_execution_complete=True,
        extraction_category=SourceUnitEligibilityCategory.FINDING,
        verification_category=SourceUnitEligibilityCategory.FINDING,
        extraction_decision=SourceUnitDecision.EXPLICIT_EVENT,
        verification_coverage=SourceUnitCoverageDecision.CANDIDATES_COMPLETE,
        extracted_candidate_count=2,
        verification_decision_count=2,
        entailed_candidate_count=2,
        trusted_candidate_count=2,
        review_only_candidate_count=0,
        rejected_candidate_count=0,
        acceptable_projection_count=1,
        fully_recovered_projection_count=1,
        minimum_acceptable_projection_link_count=1,
        observed_binding_rejection_count=0,
        binding_rejection_count=0,
        schema_retry_count=0,
        reported_schema_retry_count=0,
        primary_extraction_attempt_count=1,
        schema_retry_attempt_count=0,
        weak_review_attempt_count=1,
        controlled_event_link_count=1,
        controlled_event_link_ambiguity_count=0,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        extraction_provider_response_id_count=1,
        verification_provider_response_id_count=1,
        distinct_provider_response_id_count=2,
        verified_provider_receipt_count=2,
        provider_receipt_gate_passed=True,
        model_transport_identity_field_count=0,
        audit_identity_mismatch_count=0,
        attempt_model_id_mismatch_count=0,
    )


def test_exact_nested_event_graph_matches_source_bound_inventory() -> None:
    trusted = _trusted_inventory()
    links = link_controlled_events(trusted)

    result = match_nested_event_graph(
        expert_graph=_sealed_graph(),
        trusted=trusted,
        links=links.links,
    )

    assert links.ambiguities == ()
    assert len(result.inner_inventory_ids) == 1
    assert len(result.outer_inventory_ids) == 1
    assert result.expert_link_match_count == 1
    assert result.complete_graph_match_count == 1


def test_wrong_outer_cause_cannot_receive_nested_graph_credit() -> None:
    trusted = _trusted_inventory(wrong_outer_cause=True)
    links = link_controlled_events(trusted)

    result = match_nested_event_graph(
        expert_graph=_sealed_graph(),
        trusted=trusted,
        links=links.links,
    )

    assert len(result.inner_inventory_ids) == 1
    assert result.outer_inventory_ids == ()
    assert result.expert_link_match_count == 0
    assert result.complete_graph_match_count == 0


def test_projection_set_requires_one_complete_projection_without_partial_credit() -> (
    None
):
    canonical_trusted = _trusted_inventory()
    canonical_links = link_controlled_events(canonical_trusted)
    projection_set = _projection_set(_sealed_graph())

    recovered = match_projection_set(
        projection_set=projection_set,
        trusted=canonical_trusted,
        links=canonical_links.links,
    )
    partial_trusted = _trusted_inventory(wrong_outer_cause=True)
    partial_links = link_controlled_events(partial_trusted)
    partial = match_projection_set(
        projection_set=projection_set,
        trusted=partial_trusted,
        links=partial_links.links,
    )

    assert recovered.fully_recovered_projection_ids == ("bionlp-expert",)
    assert recovered.projections[0].completely_recovered_once is True
    assert partial.fully_recovered_projection_ids == ()
    assert partial.projections[0].match.inner_inventory_ids
    assert partial.projections[0].match.outer_inventory_ids == ()


@pytest.mark.parametrize("split_events", [True, False])
def test_projection_matcher_accepts_complete_zero_link_event_shapes(
    split_events: bool,
) -> None:
    trusted = _null_result_inventory(split_events=split_events)

    result = match_nested_event_graph(
        expert_graph=_null_result_graph(split_events=split_events),
        trusted=trusted,
        links=(),
    )

    assert result.completely_recovered_once is True
    assert result.expected_link_count == 0
    assert result.expert_link_match_count == 0
    assert result.complete_graph_match_count == 1


def test_projection_matcher_rejects_unexpected_links_from_matched_events() -> None:
    trusted = _null_result_inventory(split_events=True)
    unexpected = BoundControlledEventLink(
        link_id="unexpected-link",
        controller_inventory_id=trusted[0].inventory_id,
        controller_argument_index=0,
        controller_event_role=ClaimEventRole.THEME,
        controlled_inventory_id=trusted[1].inventory_id,
        reference_source_start=1090,
        reference_source_end=1118,
    )

    result = match_nested_event_graph(
        expert_graph=_null_result_graph(split_events=True),
        trusted=trusted,
        links=(unexpected,),
    )

    assert result.completely_recovered_once is False
    assert result.complete_graph_match_count == 0


@pytest.mark.parametrize(
    ("cue", "cue_name"),
    [
        ("enhanced", "direction"),
        ("enhanced expression", "direction-and-process"),
    ],
)
@pytest.mark.parametrize(
    "cause_kind",
    ["protein", "process", "intervention", "exposure"],
)
@pytest.mark.parametrize(
    "theme_shape",
    ["process", "resting-decomposed"],
)
def test_population_contrast_projection_preserves_positive_and_null_outcomes(
    cue: str,
    cue_name: str,
    cause_kind: str,
    theme_shape: str,
) -> None:
    trusted = _population_contrast_inventory(
        cause_kind=cause_kind,
        cue=cue,
        theme_shape=theme_shape,
    )
    link_result = link_controlled_events(trusted)
    assert link_result.ambiguities == ()

    result = match_projection_set(
        projection_set=fourth_projection_set(),
        trusted=trusted,
        links=link_result.links,
    )

    assert result.fully_recovered_projection_ids == (
        f"source-valid-{cue_name}-{cause_kind}-{theme_shape}",
    )


def test_temporal_treatment_context_is_not_forced_into_causation() -> None:
    trusted = _observational_population_contrast_inventory()
    graph = _observational_population_contrast_graph()

    result = match_nested_event_graph(
        expert_graph=graph,
        trusted=trusted,
        links=(),
        event_semantics=(
            SealedEventSemantics(
                event_id="SOURCE-RESTING",
                claim_kind=ClaimKind.SCIENTIFIC_FINDING,
                polarity=InventoryPolarity.SUPPORT,
                epistemic_status=InventoryEpistemicStatus.ASSERTED,
            ),
            SealedEventSemantics(
                event_id="SOURCE-ACTIVATED",
                claim_kind=ClaimKind.SCIENTIFIC_FINDING,
                polarity=InventoryPolarity.NULL_RESULT,
                epistemic_status=InventoryEpistemicStatus.ASSERTED,
            ),
        ),
    )

    assert result.completely_recovered_once is True
    assert result.expected_link_count == 0
    assert result.expert_link_match_count == 0


def test_projection_matcher_requires_every_link_in_a_three_event_graph() -> None:
    trusted = _multi_link_inventory()
    link_result = link_controlled_events(trusted)
    assert link_result.ambiguities == ()
    assert len(link_result.links) == 2

    complete = match_nested_event_graph(
        expert_graph=_multi_link_graph(),
        trusted=trusted,
        links=link_result.links,
    )
    incomplete = match_nested_event_graph(
        expert_graph=_multi_link_graph(),
        trusted=trusted,
        links=link_result.links[:1],
    )

    assert complete.completely_recovered_once is True
    assert complete.expected_event_count == 3
    assert complete.expected_link_count == 2
    assert incomplete.completely_recovered_once is False
    assert incomplete.expert_link_match_count == 1


def test_projection_matcher_allows_one_reference_argument_for_multiple_siblings() -> (
    None
):
    trusted = _multi_link_inventory()
    cd28, cd2, phosphorylation = trusted
    base_graph = _multi_link_graph()
    shared_reference_graph = replace(
        base_graph,
        links=(
            SealedEventLink("E41", "THEME", "E42"),
            SealedEventLink("E41", "THEME", "E43"),
            SealedEventLink("E42", "THEME", "E43"),
        ),
    )
    links = (
        BoundControlledEventLink(
            link_id="shared-1",
            controller_inventory_id=cd28.inventory_id,
            controller_argument_index=1,
            controller_event_role=ClaimEventRole.THEME,
            controlled_inventory_id=cd2.inventory_id,
            reference_source_start=1720,
            reference_source_end=1751,
        ),
        BoundControlledEventLink(
            link_id="shared-2",
            controller_inventory_id=cd28.inventory_id,
            controller_argument_index=1,
            controller_event_role=ClaimEventRole.THEME,
            controlled_inventory_id=phosphorylation.inventory_id,
            reference_source_start=1720,
            reference_source_end=1751,
        ),
        BoundControlledEventLink(
            link_id="nested-3",
            controller_inventory_id=cd2.inventory_id,
            controller_argument_index=1,
            controller_event_role=ClaimEventRole.THEME,
            controlled_inventory_id=phosphorylation.inventory_id,
            reference_source_start=1720,
            reference_source_end=1751,
        ),
    )

    result = match_nested_event_graph(
        expert_graph=shared_reference_graph,
        trusted=trusted,
        links=links,
    )

    assert result.completely_recovered_once is True
    assert result.expert_link_match_count == 3


def test_projection_set_never_combines_partial_matches_across_alternatives() -> None:
    projection_set = SealedProjectionSet(
        canonical_projection_id="bionlp-expert",
        projections=(
            _projection_set(_sealed_graph()).projections[0],
            SealedGraphProjection(
                projection_id="alternative",
                provenance=ProjectionProvenance.SOURCE_VALID_ALTERNATIVE,
                scientific_rationale="A distinct complete test projection.",
                graph=_alternative_sealed_graph(),
                event_semantics=_projection_set(
                    _alternative_sealed_graph(),
                )
                .projections[0]
                .event_semantics,
            ),
        ),
    )
    mixed_trusted = _trusted_inventory(wrong_outer_cause=True)
    links = link_controlled_events(mixed_trusted)

    result = match_projection_set(
        projection_set=projection_set,
        trusted=mixed_trusted,
        links=links.links,
    )

    assert result.fully_recovered_projection_ids == ()
    canonical, alternative = result.projections
    assert canonical.match.inner_inventory_ids
    assert canonical.match.outer_inventory_ids == ()
    assert alternative.match.inner_inventory_ids == ()
    assert alternative.match.outer_inventory_ids


def test_duplicate_required_event_candidate_cannot_receive_projection_credit() -> None:
    inner, outer = _trusted_inventory()
    links = link_controlled_events((inner, outer))

    result = match_projection_set(
        projection_set=_projection_set(_sealed_graph()),
        trusted=(inner, inner, outer),
        links=links.links,
    )

    assert result.fully_recovered_projection_ids == ()
    assert len(result.projections[0].match.inner_inventory_ids) == 2


def test_surplus_event_argument_cannot_receive_projection_credit() -> None:
    inner, outer = _trusted_inventory()
    outer_payload = outer.item.model_dump(mode="json")
    outer_arguments = outer_payload["arguments"]
    assert isinstance(outer_arguments, list)
    outer_arguments.append(_argument("GENE_OR_PROTEIN", "SITE", "Ets"))
    surplus_outer = ClaimInventoryItem.model_validate(outer_payload)
    (bound_surplus_outer,) = bind_claim_inventory(
        (surplus_outer,),
        source_text=_SOURCE,
        source_sha256=hashlib.sha256(_SOURCE.encode()).hexdigest(),
        chunk_index=6,
        source_start_offset=_SOURCE_OFFSET,
    )
    trusted = (inner, bound_surplus_outer)
    links = link_controlled_events(trusted)

    result = match_projection_set(
        projection_set=_projection_set(_sealed_graph()),
        trusted=trusted,
        links=links.links,
    )

    assert result.fully_recovered_projection_ids == ()
    assert result.projections[0].match.outer_inventory_ids == ()


def test_projection_match_preserves_event_level_epistemic_status() -> None:
    trusted = _trusted_inventory()
    links = link_controlled_events(trusted)
    baseline = _projection_set(_sealed_graph())
    projection = baseline.projections[0]
    outer_semantics = replace(
        projection.event_semantics[1],
        claim_kind=ClaimKind.SCIENTIFIC_HYPOTHESIS,
        epistemic_status=InventoryEpistemicStatus.HYPOTHESIS,
    )
    hypothesis_projection = replace(
        baseline,
        projections=(
            replace(
                projection,
                event_semantics=(projection.event_semantics[0], outer_semantics),
            ),
        ),
    )

    result = match_projection_set(
        projection_set=hypothesis_projection,
        trusted=trusted,
        links=links.links,
    )

    assert result.fully_recovered_projection_ids == ()
    assert result.projections[0].match.inner_inventory_ids
    assert result.projections[0].match.outer_inventory_ids == ()


def test_projection_set_rejects_identity_and_source_drift_before_execution() -> None:
    valid = _projection_set(_sealed_graph())
    validate_sealed_projection_set(valid, unit=_frozen_test_unit())
    projection = valid.projections[0]
    dangling_graph = replace(
        projection.graph,
        links=(replace(projection.graph.links[0], controller_event_id="missing"),),
    )
    shifted_trigger = replace(
        projection.graph.events[0].trigger,
        source_start=projection.graph.events[0].trigger.source_start + 1,
    )
    shifted_graph = replace(
        projection.graph,
        events=(
            replace(projection.graph.events[0], trigger=shifted_trigger),
            projection.graph.events[1],
        ),
    )
    extra_event_graph = replace(
        projection.graph,
        events=(
            *projection.graph.events,
            replace(projection.graph.events[0], event_id="E4"),
        ),
    )
    duplicate_argument_graph = replace(
        projection.graph,
        events=(
            replace(
                projection.graph.events[0],
                arguments=(
                    *projection.graph.events[0].arguments,
                    projection.graph.events[0].arguments[0],
                ),
            ),
            projection.graph.events[1],
        ),
    )
    self_link_graph = replace(
        projection.graph,
        links=(
            replace(
                projection.graph.links[0],
                controlled_event_id=projection.graph.links[0].controller_event_id,
            ),
        ),
    )
    unsupported_role_graph = replace(
        projection.graph,
        links=(replace(projection.graph.links[0], event_role="CONTEXT"),),
    )
    invalid_sets = (
        replace(valid, canonical_projection_id="missing"),
        replace(valid, projections=(projection, projection)),
        replace(valid, projections=(replace(projection, graph=dangling_graph),)),
        replace(valid, projections=(replace(projection, graph=shifted_graph),)),
        replace(valid, projections=(replace(projection, graph=extra_event_graph),)),
        replace(
            valid,
            projections=(replace(projection, graph=duplicate_argument_graph),),
        ),
        replace(valid, projections=(replace(projection, graph=self_link_graph),)),
        replace(
            valid,
            projections=(replace(projection, graph=unsupported_role_graph),),
        ),
    )

    for invalid in invalid_sets:
        with pytest.raises(RuntimeError):
            validate_sealed_projection_set(invalid, unit=_frozen_test_unit())


def test_wrong_event_reference_role_cannot_receive_graph_credit() -> None:
    trusted = _trusted_inventory()
    links = link_controlled_events(trusted)
    wrong_role = replace(
        links.links[0],
        controller_event_role=ClaimEventRole.CAUSE,
    )

    result = match_nested_event_graph(
        expert_graph=_sealed_graph(),
        trusted=trusted,
        links=(wrong_role,),
    )

    assert result.inner_inventory_ids
    assert result.outer_inventory_ids
    assert result.expert_link_match_count == 0
    assert result.complete_graph_match_count == 0


def test_unrelated_source_bound_extra_claim_does_not_change_sealed_match() -> None:
    inner, outer = _trusted_inventory()
    extra = _item(
        exact_span="c-Myb and Ets",
        cue="and",
        event_type="ASSOCIATION",
        arguments=[
            _argument("GENE_OR_PROTEIN", "THEME", "c-Myb"),
            _argument("GENE_OR_PROTEIN", "THEME", "Ets"),
        ],
    )
    (bound_extra,) = bind_claim_inventory(
        (extra,),
        source_text=_SOURCE,
        source_sha256=hashlib.sha256(_SOURCE.encode()).hexdigest(),
        chunk_index=6,
        source_start_offset=_SOURCE_OFFSET,
    )
    trusted = (inner, outer, bound_extra)
    links = link_controlled_events(trusted)

    result = match_nested_event_graph(
        expert_graph=_sealed_graph(),
        trusted=trusted,
        links=links.links,
    )

    assert len(result.inner_inventory_ids) == 1
    assert len(result.outer_inventory_ids) == 1
    assert result.complete_graph_match_count == 1


def test_gate_allows_extra_claims_only_when_all_are_entailed_and_trusted() -> None:
    baseline = _baseline_gate()
    assert all(nested_holdout_gate_requirements(baseline).values())

    valid_extra = replace(
        baseline,
        extracted_candidate_count=3,
        verification_decision_count=3,
        entailed_candidate_count=3,
        trusted_candidate_count=3,
        controlled_event_link_count=2,
    )
    assert all(nested_holdout_gate_requirements(valid_extra).values())

    unsupported_extra = replace(valid_extra, entailed_candidate_count=2)
    assert not nested_holdout_gate_requirements(unsupported_extra)[
        "all_candidates_source_entailed"
    ]
    unsafe_extra = replace(valid_extra, trusted_candidate_count=2)
    assert not nested_holdout_gate_requirements(unsafe_extra)[
        "review_only_candidates_preserved"
    ]

    review_only_extra = replace(
        valid_extra,
        trusted_candidate_count=2,
        review_only_candidate_count=1,
    )
    assert all(nested_holdout_gate_requirements(review_only_extra).values())

    rejected_extra = replace(
        review_only_extra,
        review_only_candidate_count=0,
        rejected_candidate_count=1,
    )
    assert not nested_holdout_gate_requirements(rejected_extra)[
        "rejected_candidate_zero"
    ]


def test_gate_fails_closed_on_each_nested_identity_boundary() -> None:
    baseline = _baseline_gate()
    mutations = (
        {"hidden_expert_event_count": 0},
        {"hidden_expert_link_count": -1},
        {"expected_eligibility_category": SourceUnitEligibilityCategory.HYPOTHESIS},
        {"acceptable_projection_count": 0},
        {"fully_recovered_projection_count": 0},
        {"observed_binding_rejection_count": 1},
        {"schema_retry_count": 2},
        {"reported_schema_retry_count": 1},
        {"primary_extraction_attempt_count": 2},
        {"schema_retry_attempt_count": 1},
        {"weak_review_attempt_count": 2},
        {"controlled_event_link_count": 0},
        {"controlled_event_link_ambiguity_count": 1},
        {"provider_receipt_gate_passed": False},
        {"attempt_model_id_mismatch_count": 1},
    )
    for mutation in mutations:
        assert not all(
            nested_holdout_gate_requirements(replace(baseline, **mutation)).values(),
        )

    repaired = replace(
        baseline,
        observed_binding_rejection_count=1,
        schema_retry_count=1,
        reported_schema_retry_count=1,
        schema_retry_attempt_count=1,
        extraction_provider_response_id_count=2,
        distinct_provider_response_id_count=3,
        verified_provider_receipt_count=3,
    )
    assert all(nested_holdout_gate_requirements(repaired).values())


def test_selection_recomputes_frozen_holdout_when_corpus_is_available() -> None:
    corpus = os.getenv("ARTANA_TG04_BIONLP_CORPUS_ROOT")
    if corpus is None:
        pytest.skip("set ARTANA_TG04_BIONLP_CORPUS_ROOT for corpus-integrity test")

    selection = select_nested_event_holdout(
        corpus_root=Path(corpus),
        archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
    )

    assert selection.case_id == "bionlp-ge-2011-holdout:PMID-9233802"
    assert selection.unit.index == 6
    assert selection.unit.text == _SOURCE
    assert selection.candidate_unit_count == 16
    assert len(selection.expert_graph.events) == 2
    assert len(selection.expert_graph.links) == 1


def test_complete_graph_null_profile_is_corpus_categorical_and_nonempty() -> None:
    corpus = os.getenv("ARTANA_TG04_BIONLP_CORPUS_ROOT")
    if corpus is None:
        pytest.skip("set ARTANA_TG04_BIONLP_CORPUS_ROOT for corpus-integrity test")

    universe = enumerate_complete_event_graph_candidates(
        corpus_root=Path(corpus),
        selection_seed="profile-contract-only",
        profile=CompleteGraphSelectionProfile.NEGATED_RESULT_GRAPH,
    )

    assert universe.candidates
    for candidate in universe.candidates:
        local_ids = {event.event_id for event in candidate.local_events}
        controlled_ids = {
            argument.reference_id
            for event in candidate.local_events
            for argument in event.arguments
            if argument.reference_id in local_ids
        }
        assert any(
            modifier.modifier_type == "Negation"
            and modifier.event_id in local_ids - controlled_ids
            for modifier in candidate.document.modifiers
        )


def test_verified_archive_is_the_only_live_corpus_input() -> None:
    archive = os.getenv("ARTANA_TG04_BIONLP_ARCHIVE")
    if archive is None:
        pytest.skip("set ARTANA_TG04_BIONLP_ARCHIVE for archive-integrity test")

    with verified_corpus_root(Path(archive)) as corpus_root:
        selection = select_nested_event_holdout(
            corpus_root=corpus_root,
            archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
        )

    assert selection.unit.text == _SOURCE


def test_second_selection_excludes_exposed_unit_and_seals_causal_link() -> None:
    corpus = os.getenv("ARTANA_TG04_BIONLP_CORPUS_ROOT")
    if corpus is None:
        pytest.skip("set ARTANA_TG04_BIONLP_CORPUS_ROOT for corpus-integrity test")

    selection = select_second_nested_event_holdout(
        corpus_root=Path(corpus),
        archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
    )

    assert selection.trial_generation == 2
    assert selection.case_id == ("bionlp-ge-2011-holdout:PMC-2806624-07-DISCUSSION")
    assert selection.unit.index == 54
    assert selection.unit.unit_id == (
        "source-unit-edb3591fbea79678533ddb57259dddfc3be3bb0e8f003c2e06c62fbf4b50f0cd"
    )
    assert selection.unit.source_sha256 == (
        "70de20a933092f2eb987b0ac86b6c988e38c6acf5d71461eb132147699ef53b6"
    )
    assert selection.unit.input_sha256 == (
        "4e9bca5f89e9ece248a0acc9405ebdc7abb6b386ef69c3b910a9c8aaa82df920"
    )
    assert selection.selection_rank == (
        "23e11013c67e5cc27925588c0999a74af6192f4a6626c9a4ea644ee7479adbac"
    )
    assert selection.expert_graph_sha256 == (
        "b881b0e63ac7ea503820a444b0352160277e5b4d6df695430a283a0eea610696"
    )
    assert selection.candidate_unit_count == 15
    assert selection.excluded_document_ids == ("PMID-9233802",)
    assert selection.expert_graph.links[0].event_role == "CAUSE"
    assert ClaimEventRole.CAUSE.value == selection.expert_graph.links[0].event_role
    assert {event.event_type for event in selection.expert_graph.events} == {
        "BINDING",
        "NEGATIVE_REGULATION",
    }


def test_third_selection_freezes_projection_set_before_execution() -> None:
    corpus = os.getenv("ARTANA_TG04_BIONLP_CORPUS_ROOT")
    if corpus is None:
        pytest.skip("set ARTANA_TG04_BIONLP_CORPUS_ROOT for corpus-integrity test")

    selection = select_third_nested_event_holdout(
        corpus_root=Path(corpus),
        archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
    )

    assert selection.trial_generation == 3
    assert selection.case_id == ("bionlp-ge-2011-holdout:PMC-2222968-08-Discussion")
    assert selection.unit.index == 23
    assert selection.candidate_unit_count == 14
    assert selection.excluded_document_ids == (
        "PMC-2806624-07-DISCUSSION",
        "PMID-9233802",
    )
    assert selection.expert_graph_sha256 == (
        "2de75032dafdf1072a7c86d592b89044c3b024f05ca679b0dd6461c7c81c696b"
    )
    assert selection.projection_set_sha256 == (
        "7828ded0f5ccca1ed3e3af1362277688bffad30ccb7bd27318e0196d2a332a21"
    )
    assert len(selection.projection_set.projections) == 1
    assert selection.projection_set.projections[0].provenance is (
        ProjectionProvenance.BIONLP_EXPERT
    )
    semantics = {
        item.event_id: (item.claim_kind.value, item.epistemic_status.value)
        for item in selection.projection_set.projections[0].event_semantics
    }
    assert semantics == {
        "E46": ("SCIENTIFIC_FINDING", "ASSERTED"),
        "E47": ("SCIENTIFIC_HYPOTHESIS", "HYPOTHESIS"),
    }
    assert selection.expected_eligibility_category is (
        SourceUnitEligibilityCategory.MIXED_SCIENTIFIC
    )


def test_fourth_selection_is_direct_seeded_and_frozen_after_prompt_commit() -> None:
    corpus = os.getenv("ARTANA_TG04_BIONLP_CORPUS_ROOT")
    if corpus is None:
        pytest.skip("set ARTANA_TG04_BIONLP_CORPUS_ROOT for corpus-integrity test")

    selection = select_fourth_nested_event_holdout(
        corpus_root=Path(corpus),
        archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
    )

    assert selection.trial_generation == 4
    assert selection.selection_seed == (
        "f2d1c55426cf241fa95b7bf06db11cab12749204b0cfd81e8d851811b230cff7"
    )
    assert selection.case_id == "bionlp-ge-2011-holdout:PMC-1920263-15-DISCUSSION"
    assert selection.unit.index == 25
    assert selection.unit.unit_id == (
        "source-unit-372b0632f7433058002746584f09b6a55db2fcde52724d1f59104731edb29870"
    )
    assert selection.candidate_unit_count == 11
    assert selection.expert_graph_sha256 == (
        "1420609f10dbb6e2d667acdc6d3d0909a96ccd1572a032ef4986bd1ab4f746ca"
    )
    assert selection.projection_set_sha256 == (
        "5d725c8feedfaf292cb3753c7c9cd8a557ceb7eeba23538068325f7f4f1f237d"
    )
    assert selection.expected_eligibility_category is (
        SourceUnitEligibilityCategory.MIXED_SCIENTIFIC
    )
    assert len(selection.projection_set.projections) == 16
    assert all(
        len(projection.graph.events) in {2, 3}
        for projection in selection.projection_set.projections
    )
    agent_inputs = (
        _extraction_prompt(selection.unit),
        _verification_prompt(
            unit=selection.unit,
            candidates=_population_contrast_inventory(
                cause_kind="protein",
                cue="enhanced",
            ),
        ),
    )
    for hidden_value in (
        selection.expert_graph_sha256,
        selection.projection_set_sha256,
        *(
            projection.projection_id
            for projection in selection.projection_set.projections
        ),
        *(
            projection.scientific_rationale
            for projection in selection.projection_set.projections
        ),
    ):
        assert all(hidden_value not in prompt for prompt in agent_inputs)


def test_agent_prompt_interfaces_cannot_receive_hidden_projection_data() -> None:
    unit = FrozenSourceUnit(
        unit_id="source-unit-prompt-blindness",
        index=9,
        source_start=_NULL_SOURCE_OFFSET,
        source_end=_NULL_SOURCE_OFFSET + len(_NULL_SOURCE),
        text=_NULL_SOURCE,
        source_sha256=hashlib.sha256(_NULL_SOURCE.encode()).hexdigest(),
    )
    secret = "sealed-projection-secret-that-must-not-leak"
    agent_inputs = (
        _extraction_prompt(unit),
        _verification_prompt(unit=unit, candidates=_null_result_inventory()),
    )
    for prompt_builder in (
        _extraction_prompt,
        _verification_prompt,
        _binding_repair_prompt,
    ):
        assert "projection" not in inspect.signature(prompt_builder).parameters
    assert all(secret not in prompt for prompt in agent_inputs)


def test_nested_holdout_cli_exit_status_follows_gate() -> None:
    assert nested_holdout_trial_exit_code({"gate": {"passed": True}}) == 0
    assert nested_holdout_trial_exit_code({"gate": {"passed": False}}) == 1
    assert nested_holdout_trial_exit_code({}) == 1
    assert second_nested_holdout_exit_code({"gate": {"passed": True}}) == 0
    assert second_nested_holdout_exit_code({"gate": {"passed": False}}) == 1
    assert second_nested_holdout_exit_code({}) == 1
    assert third_nested_holdout_exit_code({"gate": {"passed": True}}) == 0
    assert third_nested_holdout_exit_code({"gate": {"passed": False}}) == 1
    assert third_nested_holdout_exit_code({}) == 1
    assert fourth_nested_holdout_exit_code({"gate": {"passed": True}}) == 0
    assert fourth_nested_holdout_exit_code({"gate": {"passed": False}}) == 1
    assert fourth_nested_holdout_exit_code({}) == 1
