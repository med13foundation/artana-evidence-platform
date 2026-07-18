"""Tests for the pre-registered hidden nested-event trial."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimEventRole,
    ClaimInventoryItem,
    ClaimKind,
    InventoryEpistemicStatus,
    bind_claim_inventory,
    link_controlled_events,
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
    ProjectionProvenance,
    SealedArgument,
    SealedEvent,
    SealedEventLink,
    SealedGraphProjection,
    SealedNestedEventGraph,
    SealedProjectionSet,
    SealedTrigger,
    canonical_projection_set,
    select_nested_event_holdout,
    validate_sealed_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.third_selection import (
    select_third_nested_event_holdout,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)

_SOURCE = (
    "ZEB blocks the activity of c-Myb and Ets individually, but together the "
    "factors synergize to resist this repression."
)
_SOURCE_OFFSET = 770


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
        acceptable_projection_count=1,
        fully_recovered_projection_count=1,
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


def test_projection_set_requires_one_complete_projection_without_partial_credit() -> None:
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
                ).projections[0].event_semantics,
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
        events=(*projection.graph.events, replace(projection.graph.events[0], event_id="E4")),
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
        "all_candidates_structure_trusted"
    ]


def test_gate_fails_closed_on_each_nested_identity_boundary() -> None:
    baseline = _baseline_gate()
    mutations = (
        {"hidden_expert_event_count": 1},
        {"hidden_expert_link_count": 0},
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
    assert selection.case_id == (
        "bionlp-ge-2011-holdout:PMC-2806624-07-DISCUSSION"
    )
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
    assert selection.case_id == (
        "bionlp-ge-2011-holdout:PMC-2222968-08-Discussion"
    )
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
