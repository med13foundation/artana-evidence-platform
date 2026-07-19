"""Tests for the pre-registered hidden nested-event trial."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
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
    unlinked_controlled_target_ids,
)

from scripts.run_eighth_nested_event_holdout_trial import (
    eighth_nested_holdout_exit_code,
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
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.eighth_selection import (
    _projection_set as eighth_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.eighth_selection import (
    select_eighth_nested_event_holdout,
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
    SealedReferenceArgument,
    SealedTrigger,
    canonical_projection_set,
    enumerate_complete_event_graph_candidates,
    select_nested_event_holdout,
    validate_sealed_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.third_selection import (
    select_third_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v9.projection import (
    ninth_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v9.selection import (
    ninth_unit_identity,
    select_ninth_nested_event_holdout,
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
_V9_SOURCE = (
    "Exogenous IL-2, which restitutes the proliferative response of the "
    "anti-CD3- and anti-CD28-treated Rel-/- T cells, restores production of "
    "IL-5, TNF-alpha, and IFN-gamma, but not IL-3 and GM-CSF expression to "
    "approximately normal levels."
)
_V9_SOURCE_OFFSET = 1266


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
            "assertion_scope": "SOURCE_ASSERTED",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "The source explicitly states this event.",
        },
    )


def _v9_projection_inventory(
    *,
    projection_index: int = 0,
    omitted_argument_span: str | None = None,
) -> tuple[BoundClaimInventoryItem, ...]:
    projection = ninth_projection_set().projections[projection_index]
    semantics = {item.event_id: item for item in projection.event_semantics}
    links_by_controller = {
        event.event_id: tuple(
            link
            for link in projection.graph.links
            if link.controller_event_id == event.event_id
        )
        for event in projection.graph.events
    }
    items: list[ClaimInventoryItem] = []
    for event in projection.graph.events:
        arguments = [
            _sealed_argument_payload(argument)
            for argument in event.arguments
            if argument.exact_span != omitted_argument_span
        ]
        reference_identities: set[tuple[str, str, int, int]] = set()
        for link in links_by_controller[event.event_id]:
            reference = link.controller_argument
            assert reference is not None
            identity = (
                link.event_role,
                reference.exact_span,
                reference.source_start,
                reference.source_end,
            )
            if identity in reference_identities:
                continue
            reference_identities.add(identity)
            reference_payload: dict[str, object] = {
                "role": reference.participant_type,
                "event_role": link.event_role,
                "exact_span": reference.exact_span,
                "role_rationale": "The source names this controlled event.",
            }
            if projection.projection_id.endswith("__bionlp-expert-nested-restoration"):
                reference_payload["controlled_event_ref"] = link.controlled_event_id
            arguments.append(reference_payload)
        event_semantics = semantics[event.event_id]
        payload: dict[str, object] = {
            "exact_span": _V9_SOURCE,
            "relation_cue_span": event.trigger.exact_span,
            "arguments": arguments,
            "source_locator": "normalized_extraction_text",
            "claim_kind": event_semantics.claim_kind.value,
            "event_type": event.event_type,
            "assertion_scope": event_semantics.assertion_scope.value,
            "polarity": event_semantics.polarity.value,
            "epistemic_status": event_semantics.epistemic_status.value,
            "inventory_rationale": "Synthetic exact conformance fixture.",
        }
        if projection.projection_id.endswith("__bionlp-expert-nested-restoration"):
            payload["local_event_id"] = event.event_id
        items.append(ClaimInventoryItem.model_validate(payload))
    return bind_claim_inventory(
        tuple(items),
        source_text=_V9_SOURCE,
        source_sha256=hashlib.sha256(_V9_SOURCE.encode()).hexdigest(),
        chunk_index=0,
        source_start_offset=_V9_SOURCE_OFFSET,
    )


def _sealed_argument_payload(argument: SealedArgument) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": argument.participant_type,
        "event_role": argument.event_role,
        "exact_span": argument.exact_span,
        "role_rationale": "The sealed source assigns this role.",
    }
    if argument.referents:
        payload["referent_anchors"] = [
            _v9_referent_anchor(referent) for referent in argument.referents
        ]
    return payload


def _v9_referent_anchor(referent: SealedReferenceArgument) -> dict[str, str]:
    local_start = referent.source_start - _V9_SOURCE_OFFSET
    local_end = referent.source_end - _V9_SOURCE_OFFSET
    return {
        "mention_span": referent.exact_span,
        "left_context": _V9_SOURCE[max(0, local_start - 12) : local_start],
        "right_context": _V9_SOURCE[local_end : local_end + 12],
    }


def _trusted_inventory(
    *,
    wrong_outer_cause: bool = False,
    outer_cue: str = "synergize to resist",
):
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
        cue=outer_cue,
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
                "assertion_scope": "SOURCE_ASSERTED",
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
                "assertion_scope": "SOURCE_ASSERTED",
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
            "assertion_scope": "SOURCE_ASSERTED",
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
                "assertion_scope": "SOURCE_ASSERTED",
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
        unmatched_trusted_candidate_count=0,
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
        unlinked_controlled_event_reference_count=0,
        unlinked_controlled_target_count=0,
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


def test_matcher_accepts_only_pre_adjudicated_trigger_alternative() -> None:
    trusted = _trusted_inventory(outer_cue="resist")
    links = link_controlled_events(trusted)
    graph = _sealed_graph()
    outer = replace(
        graph.events[1],
        trigger_alternatives=(SealedTrigger("resist", 863, 869),),
    )
    result = match_nested_event_graph(
        expert_graph=replace(graph, events=(graph.events[0], outer)),
        trusted=trusted,
        links=links.links,
    )
    unadjudicated = match_nested_event_graph(
        expert_graph=graph,
        trusted=trusted,
        links=links.links,
    )

    assert result.completely_recovered_once is True
    assert unadjudicated.complete_graph_match_count == 0


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
    split_events: bool,  # noqa: FBT001 - pytest supplies the categorical case
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


def test_surplus_argument_referent_cannot_receive_nested_graph_credit() -> None:
    inner_payload = _item(
        exact_span="ZEB blocks the activity of c-Myb",
        cue="blocks",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "ZEB"),
            _argument("GENE_OR_PROTEIN", "THEME", "c-Myb"),
        ],
    ).model_dump(mode="json")
    inner_payload["arguments"][0]["referent_anchors"] = [
        {
            "mention_span": "Ets",
            "left_context": "c-Myb and ",
            "right_context": " individually",
        }
    ]
    inner = ClaimInventoryItem.model_validate(inner_payload)
    outer = _item(
        exact_span=_SOURCE,
        cue="synergize to resist",
        arguments=[
            _argument("GENE_OR_PROTEIN", "CAUSE", "c-Myb"),
            _argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                "ZEB blocks the activity of c-Myb",
            ),
        ],
    )
    trusted = bind_claim_inventory(
        (inner, outer),
        source_text=_SOURCE,
        source_sha256=hashlib.sha256(_SOURCE.encode()).hexdigest(),
        chunk_index=6,
        source_start_offset=_SOURCE_OFFSET,
    )
    links = link_controlled_events(trusted).links

    result = match_nested_event_graph(
        expert_graph=_sealed_graph(),
        trusted=trusted,
        links=links,
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


def test_projection_matcher_uses_reference_source_identity_for_atomic_siblings() -> (
    None
):
    source = "IL-2 restores IL-5 production and TNF-alpha production."
    source_offset = 2100
    il5_process = _argument(
        "BIOLOGICAL_PROCESS",
        "THEME",
        "IL-5 production",
    )
    tnf_process = _argument(
        "BIOLOGICAL_PROCESS",
        "THEME",
        "TNF-alpha production",
    )
    trusted = bind_claim_inventory(
        (
            _item(
                exact_span=source,
                cue="restores",
                event_type="POSITIVE_REGULATION",
                arguments=[
                    _argument("GENE_OR_PROTEIN", "CAUSE", "IL-2"),
                    il5_process,
                ],
            ),
            _item(
                exact_span=source,
                cue="restores",
                event_type="POSITIVE_REGULATION",
                arguments=[
                    _argument("GENE_OR_PROTEIN", "CAUSE", "IL-2"),
                    tnf_process,
                ],
            ),
            _item(
                exact_span="IL-5 production",
                cue="production",
                event_type="EXPRESSION",
                arguments=[
                    _argument("BIOLOGICAL_PROCESS", "EFFECT", "IL-5 production"),
                    _argument("GENE_OR_PROTEIN", "THEME", "IL-5"),
                ],
            ),
            _item(
                exact_span="TNF-alpha production",
                cue="production",
                event_type="EXPRESSION",
                arguments=[
                    _argument(
                        "BIOLOGICAL_PROCESS",
                        "EFFECT",
                        "TNF-alpha production",
                    ),
                    _argument("GENE_OR_PROTEIN", "THEME", "TNF-alpha"),
                ],
            ),
        ),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        chunk_index=11,
        source_start_offset=source_offset,
    )
    link_result = link_controlled_events(trusted)
    assert link_result.ambiguities == ()
    assert len(link_result.links) == 2

    cause = SealedArgument(
        "CAUSE",
        "SOURCE-IL2",
        "GENE_OR_PROTEIN",
        "IL-2",
        2100,
        2104,
    )
    events = (
        SealedEvent(
            "OUTER-IL5",
            "POSITIVE_REGULATION",
            SealedTrigger("restores", 2105, 2113),
            (cause,),
        ),
        SealedEvent(
            "OUTER-TNF",
            "POSITIVE_REGULATION",
            SealedTrigger("restores", 2105, 2113),
            (cause,),
        ),
        SealedEvent(
            "INNER-IL5",
            "EXPRESSION",
            SealedTrigger("production", 2119, 2129),
            (
                SealedArgument(
                    "EFFECT",
                    "SOURCE-IL5-PROCESS",
                    "BIOLOGICAL_PROCESS",
                    "IL-5 production",
                    2114,
                    2129,
                ),
                SealedArgument(
                    "THEME",
                    "SOURCE-IL5",
                    "GENE_OR_PROTEIN",
                    "IL-5",
                    2114,
                    2118,
                ),
            ),
        ),
        SealedEvent(
            "INNER-TNF",
            "EXPRESSION",
            SealedTrigger("production", 2144, 2154),
            (
                SealedArgument(
                    "EFFECT",
                    "SOURCE-TNF-PROCESS",
                    "BIOLOGICAL_PROCESS",
                    "TNF-alpha production",
                    2134,
                    2154,
                ),
                SealedArgument(
                    "THEME",
                    "SOURCE-TNF",
                    "GENE_OR_PROTEIN",
                    "TNF-alpha",
                    2134,
                    2143,
                ),
            ),
        ),
    )
    graph = SealedNestedEventGraph(
        events=events,
        links=(
            SealedEventLink(
                "OUTER-IL5",
                "THEME",
                "INNER-IL5",
                SealedReferenceArgument(
                    "BIOLOGICAL_PROCESS",
                    "IL-5 production",
                    2114,
                    2129,
                ),
            ),
            SealedEventLink(
                "OUTER-TNF",
                "THEME",
                "INNER-TNF",
                SealedReferenceArgument(
                    "BIOLOGICAL_PROCESS",
                    "TNF-alpha production",
                    2134,
                    2154,
                ),
            ),
        ),
    )

    result = match_nested_event_graph(
        expert_graph=graph,
        trusted=trusted,
        links=link_result.links,
    )

    assert result.completely_recovered_once is True
    assert (
        dict(result.event_inventory_ids)["OUTER-IL5"]
        != dict(result.event_inventory_ids)["OUTER-TNF"]
    )


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
    accepted_alternative = SealedTrigger("resist", 863, 869)
    alternative_graph = replace(
        projection.graph,
        events=(
            projection.graph.events[0],
            replace(
                projection.graph.events[1],
                trigger_alternatives=(accepted_alternative,),
            ),
        ),
    )
    alternative_set = replace(
        valid,
        projections=(replace(projection, graph=alternative_graph),),
    )
    validate_sealed_projection_set(alternative_set, unit=_frozen_test_unit())
    assert alternative_set.as_json()["projections"][0]["graph"]["events"][1][
        "trigger_alternatives"
    ] == ({"exact_span": "resist", "source_start": 863, "source_end": 869},)
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
    duplicate_trigger_graph = replace(
        projection.graph,
        events=(
            replace(
                projection.graph.events[0],
                trigger_alternatives=(projection.graph.events[0].trigger,),
            ),
            projection.graph.events[1],
        ),
    )
    shifted_trigger_alternative_graph = replace(
        projection.graph,
        events=(
            projection.graph.events[0],
            replace(
                projection.graph.events[1],
                trigger_alternatives=(replace(accepted_alternative, source_start=862),),
            ),
        ),
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
        replace(
            valid,
            projections=(replace(projection, graph=duplicate_trigger_graph),),
        ),
        replace(
            valid,
            projections=(replace(projection, graph=shifted_trigger_alternative_graph),),
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
        {"fully_recovered_projection_count": 2},
        {"unmatched_trusted_candidate_count": 1},
        {"observed_binding_rejection_count": 1},
        {"schema_retry_count": 2},
        {"reported_schema_retry_count": 1},
        {"primary_extraction_attempt_count": 2},
        {"schema_retry_attempt_count": 1},
        {"weak_review_attempt_count": 2},
        {"controlled_event_link_count": 0},
        {"controlled_event_link_ambiguity_count": 1},
        {"unlinked_controlled_event_reference_count": 1},
        {"unlinked_controlled_target_count": 1},
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


def test_eighth_selection_freezes_complete_agent_expert_gold_before_luna() -> None:
    corpus = os.getenv("ARTANA_TG04_BIONLP_CORPUS_ROOT")
    if corpus is None:
        pytest.skip("set ARTANA_TG04_BIONLP_CORPUS_ROOT for corpus-integrity test")

    selection = select_eighth_nested_event_holdout(
        corpus_root=Path(corpus),
        archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
    )

    assert selection.trial_generation == 8
    assert selection.selection_seed == (
        "969619fd2b8faf60d81c34ba9b12c3f100d69f3af56dcda431072dd009156916"
    )
    assert selection.case_id == ("bionlp-ge-2011-holdout:PMC-2806624-04-RESULTS-03")
    assert selection.unit.index == 10
    assert selection.candidate_unit_count == 5
    assert selection.expert_graph_sha256 == (
        "2abda3dfab2fa4f2b35f321a7c603cf8f45c6adbb92ed63d7c69c7565dad7677"
    )
    assert selection.projection_set_sha256 == (
        "5c8e13c4eac5087d151c1b4b391b1215555ce401fdbb1c38a95b61853ed6cde6"
    )
    assert selection.expected_eligibility_category is (
        SourceUnitEligibilityCategory.MIXED_SCIENTIFIC
    )
    assert len(selection.projection_set.projections) == 2
    assert all(
        projection.provenance is ProjectionProvenance.AGENT_EXPERT_ADJUDICATED
        for projection in selection.projection_set.projections
    )
    for projection in selection.projection_set.projections:
        events = {event.event_id: event for event in projection.graph.events}
        assert set(events) == {
            "AGENT-EXPERT-TREND",
            "AGENT-EXPERT-SIGNIFICANCE-NULL",
        }
        assert all(
            event.event_type == "POSITIVE_REGULATION" for event in events.values()
        )
        assert events["AGENT-EXPERT-TREND"].trigger.exact_span == "trend"
        assert (
            events["AGENT-EXPERT-SIGNIFICANCE-NULL"].trigger.exact_span
            == "did not lead to statistically significant increase"
        )
        argument_identities = {
            (argument.participant_type, argument.event_role, argument.exact_span)
            for argument in events["AGENT-EXPERT-SIGNIFICANCE-NULL"].arguments
        }
        assert (
            "MEASUREMENT",
            "MEASURE",
            "statistically significant",
        ) in argument_identities
        assert ("POPULATION", "CONTEXT", "CD4+ T cells") in argument_identities
        assert ("GENE_OR_PROTEIN", "CAUSE", "RUNX3") in argument_identities
        assert ("GENE_OR_PROTEIN", "THEME", "FOXP3") in argument_identities
        semantics = {
            item.event_id: (item.polarity, item.epistemic_status)
            for item in projection.event_semantics
        }
        assert semantics == {
            "AGENT-EXPERT-TREND": (
                InventoryPolarity.SUPPORT,
                InventoryEpistemicStatus.PROVISIONAL,
            ),
            "AGENT-EXPERT-SIGNIFICANCE-NULL": (
                InventoryPolarity.NULL_RESULT,
                InventoryEpistemicStatus.ASSERTED,
            ),
        }

    agent_inputs = (
        _extraction_prompt(selection.unit),
        _verification_prompt(unit=selection.unit, candidates=()),
    )
    for hidden_value in (
        selection.expert_graph_sha256,
        selection.projection_set_sha256,
        *(item.projection_id for item in selection.projection_set.projections),
    ):
        assert all(hidden_value not in prompt for prompt in agent_inputs)


def test_ninth_selection_freezes_source_complete_projection_family_before_luna() -> (
    None
):
    corpus = os.getenv("ARTANA_TG04_BIONLP_CORPUS_ROOT")
    if corpus is None:
        pytest.skip("set ARTANA_TG04_BIONLP_CORPUS_ROOT for corpus-integrity test")

    selection = select_ninth_nested_event_holdout(
        corpus_root=Path(corpus),
        archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
    )

    assert selection.trial_generation == 9
    assert selection.selection_seed == (
        "b1498772852d13333a1201ddaa02c55098fdcc183bee01ef9da0915faf0ceafd"
    )
    assert selection.case_id == "bionlp-ge-2011-holdout:PMID-8622948"
    assert selection.unit.index == 7
    assert selection.candidate_unit_count == 4
    assert "PMC-2806624-04-RESULTS-03" in selection.excluded_document_ids
    assert selection.expert_graph_sha256 == (
        "d10955c29c243c95b7e089c10866d453bbf6992e79abd18753b2192b525e832a"
    )
    assert selection.projection_set_sha256 == (
        "9163b0d185bdafdc093d158ec0a5b4da0e37d950904d998d822084d04f455915"
    )
    assert selection.expected_eligibility_category is (
        SourceUnitEligibilityCategory.MIXED_SCIENTIFIC
    )
    assert len(selection.projection_set.projections) == 12
    assert sorted(
        (len(projection.graph.events), len(projection.graph.links))
        for projection in selection.projection_set.projections
    ) == [
        (6, 3),
        (6, 3),
        (7, 1),
        (7, 1),
        (7, 4),
        (7, 4),
        (8, 5),
        (8, 5),
        (9, 6),
        (9, 6),
        (12, 6),
        (12, 6),
    ]
    assert all(
        all(link.controller_argument is not None for link in projection.graph.links)
        for projection in selection.projection_set.projections
    )
    canonical = selection.projection_set.canonical_projection
    corpus_directory = Path(corpus)
    a1_lines = set(
        (corpus_directory / "PMID-8622948.a1").read_text(encoding="utf-8").splitlines()
    )
    a2_lines = set(
        (corpus_directory / "PMID-8622948.a2").read_text(encoding="utf-8").splitlines()
    )
    assert {
        "T25\tProtein 1277 1281\tIL-2",
        "T27\tProtein 1405 1409\tIL-5",
        "T28\tProtein 1411 1420\tTNF-alpha",
        "T29\tProtein 1426 1435\tIFN-gamma",
        "T30\tProtein 1445 1449\tIL-3",
        "T31\tProtein 1454 1460\tGM-CSF",
    } <= a1_lines
    assert {
        "T45\tPositive_regulation 1382 1390\trestores",
        "T46\tGene_expression 1391 1401\tproduction",
        "T47\tGene_expression 1461 1471\texpression",
        "E16\tPositive_regulation:T45 Theme:E23 Cause:T25",
        "E17\tPositive_regulation:T45 Theme:E21 Cause:T25",
        "E18\tPositive_regulation:T45 Theme:E25 Cause:T25",
        "E19\tPositive_regulation:T45 Theme:E22 Cause:T25",
        "E20\tPositive_regulation:T45 Theme:E24 Cause:T25",
        "E21\tGene_expression:T46 Theme:T28",
        "E22\tGene_expression:T46 Theme:T27",
        "E23\tGene_expression:T46 Theme:T29",
        "E24\tGene_expression:T47 Theme:T31",
        "E25\tGene_expression:T47 Theme:T30",
        "M1\tNegation E18",
        "M2\tNegation E20",
    } <= a2_lines
    semantics = {
        item.event_id: (
            item.assertion_scope.value,
            item.polarity.value,
            item.epistemic_status.value,
        )
        for item in canonical.event_semantics
    }
    assert semantics["V9-BIONLP-E18"] == (
        "SOURCE_ASSERTED",
        "NULL_RESULT",
        "ASSERTED",
    )
    assert semantics["V9-BIONLP-E20"] == (
        "SOURCE_ASSERTED",
        "NULL_RESULT",
        "ASSERTED",
    )
    controlled_target_ids = {
        "V9-PROLIFERATIVE-RESPONSE",
        "V9-BIONLP-E21",
        "V9-BIONLP-E22",
        "V9-BIONLP-E23",
        "V9-BIONLP-E24",
        "V9-BIONLP-E25",
    }
    assert all(
        semantics[event_id] == ("CONTROLLED_TARGET", "UNSCOPED", "UNASSERTED")
        for event_id in controlled_target_ids
    )
    assert all(
        semantics[event_id] == ("SOURCE_ASSERTED", "SUPPORT", "ASSERTED")
        for event_id in semantics.keys()
        - controlled_target_ids
        - {"V9-BIONLP-E18", "V9-BIONLP-E20"}
    )
    event_ids = {event.event_id for event in canonical.graph.events}
    assert event_ids == {
        "V9-PROLIFERATION-RESTORATION",
        "V9-PROLIFERATIVE-RESPONSE",
        "V9-BIONLP-E16",
        "V9-BIONLP-E17",
        "V9-BIONLP-E18",
        "V9-BIONLP-E19",
        "V9-BIONLP-E20",
        "V9-BIONLP-E21",
        "V9-BIONLP-E22",
        "V9-BIONLP-E23",
        "V9-BIONLP-E24",
        "V9-BIONLP-E25",
    }
    proliferation = next(
        event
        for event in canonical.graph.events
        if event.event_id == "V9-PROLIFERATIVE-RESPONSE"
    )
    assert proliferation.event_type == "PROLIFERATION"
    assert all(
        argument.exact_span != "the proliferative response of the anti-CD3- and "
        "anti-CD28-treated Rel-/- T cells"
        for argument in proliferation.arguments
    )
    relative_controller = next(
        event
        for event in canonical.graph.events
        if event.event_id == "V9-PROLIFERATION-RESTORATION"
    )
    which = next(
        argument
        for argument in relative_controller.arguments
        if argument.exact_span == "which"
    )
    assert tuple(referent.exact_span for referent in which.referents) == (
        "Exogenous IL-2",
    )
    assert all(event.argument_alternatives for event in canonical.graph.events)
    agent_inputs = (
        _extraction_prompt(selection.unit),
        _verification_prompt(unit=selection.unit, candidates=()),
    )
    for hidden_value in (
        selection.expert_graph_sha256,
        selection.projection_set_sha256,
        *(
            projection.projection_id
            for projection in selection.projection_set.projections
        ),
    ):
        assert all(hidden_value not in prompt for prompt in agent_inputs)


def test_ninth_projection_matcher_accepts_exact_graph_and_rejects_partial_graph() -> (
    None
):
    projection_set = ninth_projection_set()
    trusted = _v9_projection_inventory()
    links = link_controlled_events(trusted)

    complete = match_projection_set(
        projection_set=projection_set,
        trusted=trusted,
        links=links.links,
    )

    assert links.ambiguities == ()
    assert links.unlinked_references == ()
    assert len(links.links) == 6
    assert complete.fully_recovered_projection_ids == (
        "complete-proliferation-cue__atomic-supported-targets__atomic-null-targets",
    )

    partial_trusted = tuple(
        item for item in trusted if item.item.arguments[0].exact_span != "GM-CSF"
    )
    partial_links = link_controlled_events(partial_trusted)
    partial = match_projection_set(
        projection_set=projection_set,
        trusted=partial_trusted,
        links=partial_links.links,
    )

    assert partial.fully_recovered_projection_ids == ()
    assert len(partial_links.links) == 5


def test_ninth_projection_matcher_accepts_grouped_events_but_not_missing_theme() -> (
    None
):
    projection_set = ninth_projection_set()
    trusted = _v9_projection_inventory(projection_index=3)
    links = link_controlled_events(trusted)

    complete = match_projection_set(
        projection_set=projection_set,
        trusted=trusted,
        links=links.links,
    )

    assert links.ambiguities == ()
    assert links.unlinked_references == ()
    assert len(links.links) == 3
    assert complete.fully_recovered_projection_ids == (
        "complete-proliferation-cue__grouped-supported-target__grouped-null-target",
    )

    incomplete_trusted = _v9_projection_inventory(
        projection_index=3,
        omitted_argument_span="IFN-gamma",
    )
    incomplete_links = link_controlled_events(incomplete_trusted)
    incomplete = match_projection_set(
        projection_set=projection_set,
        trusted=incomplete_trusted,
        links=incomplete_links.links,
    )

    assert incomplete.fully_recovered_projection_ids == ()


@pytest.mark.parametrize("projection_index", range(12))
def test_ninth_projection_matcher_accepts_each_complete_representation_only(
    projection_index: int,
) -> None:
    projection_set = ninth_projection_set()
    projection = projection_set.projections[projection_index]
    trusted = _v9_projection_inventory(projection_index=projection_index)
    links = link_controlled_events(trusted)

    complete = match_projection_set(
        projection_set=projection_set,
        trusted=trusted,
        links=links.links,
    )

    assert links.ambiguities == ()
    assert links.unlinked_references == ()
    assert unlinked_controlled_target_ids(trusted, links.links) == ()
    assert complete.fully_recovered_projection_ids == (projection.projection_id,)
    assert len(links.links) == len(projection.graph.links)

    for cytokine in ("IL-5", "TNF-alpha", "IFN-gamma", "IL-3", "GM-CSF"):
        incomplete_trusted = _v9_projection_inventory(
            projection_index=projection_index,
            omitted_argument_span=cytokine,
        )
        incomplete_links = link_controlled_events(incomplete_trusted)
        incomplete = match_projection_set(
            projection_set=projection_set,
            trusted=incomplete_trusted,
            links=incomplete_links.links,
        )
        assert incomplete.fully_recovered_projection_ids == ()


def test_ninth_bionlp_projection_uses_explicit_shared_trigger_references() -> None:
    projection_set = ninth_projection_set()
    projection = projection_set.projections[10]
    trusted = _v9_projection_inventory(projection_index=10)

    links = link_controlled_events(trusted)
    match = match_projection_set(
        projection_set=projection_set,
        trusted=trusted,
        links=links.links,
    )

    expected_links = {
        (
            link.controlled_event_id,
            link.controller_event_id,
            link.controlled_event_id,
        )
        for link in projection.graph.links
    }
    observed_links = {
        (
            next(
                argument.controlled_event_ref
                for argument in controller.bound_arguments
                if argument.controlled_event_ref is not None
                and argument.argument.event_role.value
                == link.controller_event_role.value
            ),
            next(
                event.event_id
                for event, candidate in zip(
                    projection.graph.events,
                    trusted,
                    strict=True,
                )
                if candidate.inventory_id == link.controller_inventory_id
            ),
            next(
                event.event_id
                for event, candidate in zip(
                    projection.graph.events,
                    trusted,
                    strict=True,
                )
                if candidate.inventory_id == link.controlled_inventory_id
            ),
        )
        for link in links.links
        for controller in trusted
        if controller.inventory_id == link.controller_inventory_id
    }
    assert links.ambiguities == ()
    assert links.unlinked_references == ()
    assert len(links.links) == 6
    assert observed_links == expected_links
    assert match.fully_recovered_projection_ids == (projection.projection_id,)


def test_ninth_mixed_complete_representations_fail_unique_recovery() -> None:
    projection_set = ninth_projection_set()
    nested = _v9_projection_inventory(projection_index=0)
    direct = _v9_projection_inventory(projection_index=8)
    trusted_by_id = {
        candidate.inventory_id: candidate for candidate in (*nested, *direct)
    }
    trusted = tuple(trusted_by_id.values())
    links = link_controlled_events(trusted)

    match = match_projection_set(
        projection_set=projection_set,
        trusted=trusted,
        links=links.links,
    )

    assert set(match.fully_recovered_projection_ids) == {
        projection_set.projections[0].projection_id,
        projection_set.projections[8].projection_id,
    }
    assert match.fully_recovered_inventory_ids == ()
    gate = replace(
        _baseline_gate(),
        extracted_candidate_count=len(trusted),
        verification_decision_count=len(trusted),
        entailed_candidate_count=len(trusted),
        trusted_candidate_count=len(trusted),
        unmatched_trusted_candidate_count=len(trusted),
        controlled_event_link_count=len(links.links),
        hidden_expert_event_count=len(projection_set.canonical_projection.graph.events),
        hidden_expert_link_count=len(projection_set.canonical_projection.graph.links),
        acceptable_projection_count=len(projection_set.projections),
        fully_recovered_projection_count=len(match.fully_recovered_projection_ids),
        minimum_acceptable_projection_link_count=min(
            len(projection.graph.links) for projection in projection_set.projections
        ),
    )
    requirements = nested_holdout_gate_requirements(gate)
    assert requirements["single_representation_family_recovered"] is False
    assert requirements["unmatched_trusted_candidate_zero"] is False


def test_ninth_wrong_extra_link_is_not_credited_by_local_event_shape() -> None:
    projection_set = ninth_projection_set()
    canonical = _v9_projection_inventory(projection_index=10)
    e16 = next(
        item.item for item in canonical if item.item.local_event_id == "V9-BIONLP-E16"
    )
    wrong_payload = e16.model_dump(mode="json")
    wrong_payload["local_event_id"] = "wrong-e16-link"
    wrong_arguments = wrong_payload["arguments"]
    assert isinstance(wrong_arguments, list)
    controlled_argument = next(
        argument
        for argument in wrong_arguments
        if isinstance(argument, dict)
        and argument.get("controlled_event_ref") == "V9-BIONLP-E23"
    )
    assert isinstance(controlled_argument, dict)
    controlled_argument["controlled_event_ref"] = "V9-BIONLP-E21"
    wrong = ClaimInventoryItem.model_validate(wrong_payload)
    trusted = bind_claim_inventory(
        (*tuple(item.item for item in canonical), wrong),
        source_text=_V9_SOURCE,
        source_sha256=hashlib.sha256(_V9_SOURCE.encode()).hexdigest(),
        chunk_index=0,
        source_start_offset=_V9_SOURCE_OFFSET,
    )
    links = link_controlled_events(trusted)

    match = match_projection_set(
        projection_set=projection_set,
        trusted=trusted,
        links=links.links,
    )

    wrong_inventory_id = trusted[-1].inventory_id
    assert links.ambiguities == ()
    assert len(links.unlinked_references) == 1
    assert links.unlinked_references[0].controller_inventory_id == wrong_inventory_id
    assert len(links.links) == 6
    assert match.fully_recovered_projection_ids == (
        projection_set.projections[10].projection_id,
    )
    assert wrong_inventory_id not in match.fully_recovered_inventory_ids
    unmatched_count = len(
        {candidate.inventory_id for candidate in trusted}
        - set(match.fully_recovered_inventory_ids)
    )
    assert unmatched_count == 1
    gate = replace(
        _baseline_gate(),
        extracted_candidate_count=len(trusted),
        verification_decision_count=len(trusted),
        entailed_candidate_count=len(trusted),
        trusted_candidate_count=len(trusted),
        unmatched_trusted_candidate_count=unmatched_count,
        controlled_event_link_count=len(links.links),
        hidden_expert_event_count=len(projection_set.canonical_projection.graph.events),
        hidden_expert_link_count=len(projection_set.canonical_projection.graph.links),
        acceptable_projection_count=len(projection_set.projections),
        fully_recovered_projection_count=len(match.fully_recovered_projection_ids),
        minimum_acceptable_projection_link_count=min(
            len(projection.graph.links) for projection in projection_set.projections
        ),
    )
    assert (
        nested_holdout_gate_requirements(gate)["unmatched_trusted_candidate_zero"]
        is False
    )


def test_ninth_projection_does_not_trust_a_contradictory_unmatched_extra() -> None:
    projection_set = ninth_projection_set()
    trusted = _v9_projection_inventory()
    contradictory = ClaimInventoryItem.model_validate(
        {
            "exact_span": _V9_SOURCE,
            "relation_cue_span": "restores",
            "arguments": [
                _argument("GENE_OR_PROTEIN", "CAUSE", "IL-2"),
                _argument("GENE_OR_PROTEIN", "THEME", "IL-3"),
                _argument(
                    "COMPARATOR",
                    "MEASURE",
                    "approximately normal levels",
                ),
            ],
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "POSITIVE_REGULATION",
            "assertion_scope": "SOURCE_ASSERTED",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": (
                "Adversarially reverses the source's explicit null result."
            ),
        }
    )
    (bound_contradictory,) = bind_claim_inventory(
        (contradictory,),
        source_text=_V9_SOURCE,
        source_sha256=hashlib.sha256(_V9_SOURCE.encode()).hexdigest(),
        chunk_index=0,
        source_start_offset=_V9_SOURCE_OFFSET,
    )
    all_trusted = (*trusted, bound_contradictory)
    links = link_controlled_events(all_trusted)

    match = match_projection_set(
        projection_set=projection_set,
        trusted=all_trusted,
        links=links.links,
    )

    assert match.fully_recovered_projection_ids
    assert bound_contradictory.inventory_id not in (match.fully_recovered_inventory_ids)
    gate = replace(
        _baseline_gate(),
        extracted_candidate_count=len(all_trusted),
        verification_decision_count=len(all_trusted),
        entailed_candidate_count=len(all_trusted),
        trusted_candidate_count=len(all_trusted),
        unmatched_trusted_candidate_count=1,
        controlled_event_link_count=len(links.links),
        hidden_expert_event_count=len(projection_set.canonical_projection.graph.events),
        hidden_expert_link_count=len(projection_set.canonical_projection.graph.links),
        acceptable_projection_count=len(projection_set.projections),
        fully_recovered_projection_count=len(match.fully_recovered_projection_ids),
        minimum_acceptable_projection_link_count=min(
            len(projection.graph.links) for projection in projection_set.projections
        ),
    )
    assert not nested_holdout_gate_requirements(gate)[
        "unmatched_trusted_candidate_zero"
    ]


def test_eighth_lineage_freezes_blinded_reviews_and_lowest_rank_in_ci() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    lineage_path = (
        repository_root
        / "docs/validation/reports/2026-07-18-tg04-v8-agent-expert-lineage.json"
    )
    lineage = json.loads(
        lineage_path.read_text(encoding="utf-8"),
    )

    assert lineage["agent_execution_attempted"] is False
    assert lineage["artana_output_available_to_reviewers"] is False
    results = lineage["candidate_review"]["results"]
    assert len(results) == 5
    assert all(result["reviewer_a"] == "INCOMPLETE" for result in results)
    assert all(result["reviewer_b"] == "INCOMPLETE" for result in results)
    selection_seed = lineage["preselection"]["selection_seed"]
    for result in results:
        assert (
            result["selection_rank"]
            == hashlib.sha256(
                f"{selection_seed}:{result['unit_id']}".encode(),
            ).hexdigest()
        )
    selected_rank = lineage["preselection"]["selection_rank"]
    assert selected_rank == min(result["selection_rank"] for result in results)
    selected = lineage["selected_source"]
    selected_result = next(
        result for result in results if result["selection_rank"] == selected_rank
    )
    assert selected_result["unit_id"] == selected["unit_id"]
    v7_receipt = (
        repository_root
        / "docs/validation/reports/2026-07-18-tg04-v7-selection-preflight.json"
    )
    assert hashlib.sha256(v7_receipt.read_bytes()).hexdigest() == selection_seed
    tree_oid = subprocess.run(
        (
            "git",
            "-C",
            str(repository_root),
            "rev-parse",
            f"{lineage['preselection']['repository_commit']}^{{tree}}",
        ),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert tree_oid == lineage["preselection"]["repository_tree_oid"]
    frozen_unit = FrozenSourceUnit(
        unit_id=selected["unit_id"],
        index=selected["unit_index"],
        source_start=selected["source_start"],
        source_end=selected["source_end"],
        text=selected["text"],
        source_sha256=selected["source_sha256"],
    )
    assert frozen_unit.input_sha256 == selected["input_sha256"]
    projection_payload = eighth_projection_set().as_json()
    projection_hash = hashlib.sha256(
        json.dumps(
            projection_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode(),
    ).hexdigest()
    assert (
        projection_hash == lineage["source_gold_adjudication"]["projection_set_sha256"]
    )
    authoring_submissions = {
        item["submission_id"] for item in lineage["gold_authoring"]["reviewer_outputs"]
    }
    assert len(authoring_submissions) == 2
    hidden_values = (
        projection_hash,
        lineage["source_gold_adjudication"]["adjudicator_run_id"],
    )
    prompts = (
        _extraction_prompt(frozen_unit),
        _verification_prompt(unit=frozen_unit, candidates=()),
    )
    assert all(value not in prompt for value in hidden_values for prompt in prompts)
    assert lineage["source_gold_adjudication"]["decision"] == "COMPLETE"
    assert lineage["qualification_scope"]["human_expert_validation_proven"] is False
    assert lineage["qualification_scope"]["trusted_graph_promotion_authorized"] is False


def test_ninth_lineage_freezes_source_gold_before_agent_execution() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    lineage_path = (
        repository_root
        / "docs/validation/reports/2026-07-18-tg04-v9-source-gold-lineage.json"
    )
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))

    assert lineage["schema_version"] == "tg04_v9_source_gold_lineage.v1"
    assert lineage["agent_execution_attempted"] is False
    assert lineage["artana_output_available_to_reviewers"] is False
    assert lineage["selected_source"] == {
        **lineage["selected_source"],
        **ninth_unit_identity(),
    }
    assert lineage["projection_contract"]["projection_count"] == 12
    assert lineage["projection_contract"]["event_count"] == 12
    assert lineage["projection_contract"]["event_count_range"] == [6, 12]
    assert lineage["projection_contract"]["link_count"] == 6
    assert lineage["projection_contract"]["link_count_range"] == [1, 6]
    assert lineage["projection_contract"]["expert_graph_sha256"] == (
        "d10955c29c243c95b7e089c10866d453bbf6992e79abd18753b2192b525e832a"
    )
    assert lineage["projection_contract"]["projection_set_sha256"] == (
        "9163b0d185bdafdc093d158ec0a5b4da0e37d950904d998d822084d04f455915"
    )
    projection_set = ninth_projection_set()
    assert lineage["projection_contract"]["canonical_projection_id"] == (
        projection_set.canonical_projection_id
    )
    assert lineage["projection_contract"]["projection_ids"] == [
        projection.projection_id for projection in projection_set.projections
    ]
    assert (
        hashlib.sha256(
            json.dumps(
                projection_set.as_json(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
        ).hexdigest()
        == lineage["projection_contract"]["projection_set_sha256"]
    )
    assert len(lineage["reviewers"]) == 12
    assert [item["decision"] for item in lineage["reviewers"][-2:]] == [
        "GO_SCIENTIFIC_CONTRACT_SAFE_TO_FREEZE_FOR_ONE_LIVE_DIAGNOSTIC",
        "GO_EXECUTION_INTEGRITY_SAFE_TO_FREEZE_FOR_ONE_LIVE_DIAGNOSTIC",
    ]
    assert lineage["source_verification"]["pmid"] == "8622948"
    assert (
        lineage["source_verification"][
            "pubmed_correction_or_retraction_metadata_present"
        ]
        is False
    )
    assert lineage["qualification_scope"]["trusted_graph_promotion_authorized"] is False


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


def test_live_finite_prompts_require_trend_and_significance_null_siblings() -> None:
    unit = FrozenSourceUnit(
        unit_id="source-unit-significance-siblings",
        index=10,
        source_start=1909,
        source_end=2051,
        text=(
            "Although there was a trend, the transfection of CD4+ T cells with "
            "RUNX3 did not lead to statistically significant increase in FOXP3 "
            "(Fig. S5)."
        ),
        source_sha256=(
            "09a14c9ddcfd3ef03820e5fe7f3a62164fdf051f3a46335b8523c0681ed5fe35"
        ),
    )

    extraction_prompt = " ".join(_extraction_prompt(unit).casefold().split())
    verification_prompt = " ".join(
        _verification_prompt(unit=unit, candidates=()).casefold().split()
    )
    for prompt in (extraction_prompt, verification_prompt):
        assert "two sibling" in prompt
        assert "support" in prompt
        assert "provisional" in prompt
        assert "null_result" in prompt
        assert "statistical significance" in prompt
        assert "measurement" in prompt
        assert "complete negated significance phrase" in prompt
        assert "no change" in prompt
        assert "no effect" in prompt
        assert "p-value" in prompt


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
    assert eighth_nested_holdout_exit_code({"gate": {"passed": True}}) == 0
    assert eighth_nested_holdout_exit_code({"gate": {"passed": False}}) == 1
    assert eighth_nested_holdout_exit_code({}) == 1
