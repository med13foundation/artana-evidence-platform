"""Focused V13 nested source-semantic evaluator regressions."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from pydantic import TypeAdapter

from scripts.validation.public_gold.staged_event.generalization import (
    panel as panel_module,
)
from scripts.validation.public_gold.staged_event.generalization.anchors import (
    resolve_evidence,
)
from scripts.validation.public_gold.staged_event.generalization.contracts import (
    StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS as GRADING_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
    FrozenCasePolicy,
    FrozenDualLanePolicy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
    GeneralizationReference,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.contracts import (
    V12TwoLaneContract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.evaluation import (
    V12CaseMetrics,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13 import (
    evaluation as v13_evaluation,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    V13NestedTwoLaneContract,
    build_contract,
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.evaluation import (
    V13CaseMetrics,
    evaluate_v13_case,
    resolve_focus_local_occurrence,
)
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    resolve_unique_span,
    token_bounded_spans,
)

REPO = Path(__file__).resolve().parents[2]
ADJUDICATION = REPO / (
    "docs/validation/adjudications/"
    "2026-07-23-pmid-7966592-nested-two-lane-adjudication-v1.json"
)
PANEL_FIXTURE = REPO / (
    "docs/validation/fixtures/2026-07-22-staged-generalization-panel-v9.json"
)
PANEL_SHA256 = "00dad3d580755a1c2268e1db32e8ccd1d50771b4a8861138eb18f6593e8e188e"
V12_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v12-exposed-run-v1-"
    "generalization-explicit-nested-cause-raw.json"
)
V12_DRUG_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v12-exposed-run-v1-"
    "generalization-drug-sensitivity-raw.json"
)

_OBJECT = TypeAdapter(dict[str, object])
_OBJECT_LIST = TypeAdapter(list[dict[str, object]])


def _case(
    case_id: str = "generalization-explicit-nested-cause",
) -> GeneralizationCase:
    payload = _OBJECT.validate_json(PANEL_FIXTURE.read_text(encoding="utf-8"))
    records = _OBJECT_LIST.validate_python(payload.get("cases"))
    record = next(item for item in records if item.get("case_id") == case_id)
    reference = _reference(case_id)
    return GeneralizationCase(
        case_id=_string(record, "case_id"),
        family=_string(record, "family"),
        source_id=_string(record, "source_id"),
        source_sha256=_string(record, "source_sha256"),
        source=_string(record, "source"),
        context_start=_integer(record, "context_start"),
        context_end=_integer(record, "context_end"),
        local_context=_string(record, "local_context"),
        focus_start=_integer(record, "focus_start"),
        focus_end=_integer(record, "focus_end"),
        focus_passage=_string(record, "focus_passage"),
        reference=reference,
    )


def _reference(case_id: str) -> GeneralizationReference:
    builders = {
        "generalization-comparison-canary": panel_module._comparison_reference,
        "generalization-null-statistics": panel_module._null_reference,
        "generalization-negated-association": (panel_module._no_association_reference),
        "generalization-uncertainty": panel_module._uncertainty_reference,
        "generalization-drug-sensitivity": panel_module._sensitivity_reference,
        "generalization-explicit-nested-cause": (panel_module._nested_cause_reference),
    }
    return builders[case_id]()


def _output() -> V9StagedGeneralizationOutput:
    return V9StagedGeneralizationOutput.model_validate_json(
        V12_RAW.read_text(encoding="utf-8")
    )


def _contract() -> V13NestedTwoLaneContract:
    return build_contract(ADJUDICATION)


def _policy() -> FrozenCasePolicy:
    return cast("FrozenCasePolicy", object())


def _corrected_output() -> V9StagedGeneralizationOutput:
    return _output().model_copy(update={"root_event_id": "E1"})


def _cg_chain_output() -> V9StagedGeneralizationOutput:
    output = _corrected_output()
    elevating = next(item for item in output.inventory if item.event_id == "E2")
    levels = elevating.model_copy(
        update={
            "event_id": "E3",
            "event_type": "GENE_EXPRESSION",
            "trigger_text": "levels",
            "explanation": "CG projection event for the stated p53 levels.",
        }
    )
    responsible_links = next(item for item in output.links if item.event_id == "E1")
    elevating_links = next(item for item in output.links if item.event_id == "E2")
    affected = next(
        item for item in elevating_links.arguments if item.role == "AFFECTED_ENTITY"
    )
    context = next(
        item
        for item in elevating_links.arguments
        if item.role == "CONTEXTUAL_PARTICIPANT"
    )
    effect = next(
        item for item in responsible_links.arguments if item.role == "EFFECT_EVENT"
    ).model_copy(
        update={
            "target_id": "E3",
            "explanation": "The CG elevation event targets the levels event.",
        }
    )
    changed_elevating_links = elevating_links.model_copy(
        update={"arguments": (effect, context)}
    )
    levels_links = elevating_links.model_copy(
        update={"event_id": "E3", "arguments": (affected,)}
    )
    levels_axes = next(
        item for item in output.semantic_axes if item.event_id == "E2"
    ).model_copy(
        update={
            "event_id": "E3",
            "direction": "OBSERVED",
            "explanation": "CG-only levels event axes.",
        }
    )
    candidate = output.model_copy(
        update={
            "inventory": (*output.inventory, levels),
            "links": (
                responsible_links,
                changed_elevating_links,
                levels_links,
            ),
            "semantic_axes": (*output.semantic_axes, levels_axes),
        }
    )
    return V9StagedGeneralizationOutput.model_validate_json(
        json.dumps(candidate.model_dump(mode="json"))
    )


def _metrics(
    output: StagedGeneralizationOutput | None = None,
    contract: V13NestedTwoLaneContract | None = None,
) -> V13CaseMetrics:
    return evaluate_v13_case(
        _case(),
        output or _output(),
        _policy(),
        contract or _contract(),
    )


def test_contract_is_deterministically_derived_and_hash_bound(
    tmp_path: Path,
) -> None:
    expected = _contract()
    path = tmp_path / "v13-contract.json"
    path.write_text(
        json.dumps(
            expected.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_contract(path, adjudication_path=ADJUDICATION)

    assert sha256(PANEL_FIXTURE.read_bytes()).hexdigest() == PANEL_SHA256
    assert loaded == expected
    assert loaded.drug_case_policy == (
        "V12_DRUG_METRICS_REUSED_SOURCE_LANE_AUTHORITATIVE_CG_NONBLOCKING"
    )
    assert loaded.other_exposed_cases_policy == "UNCHANGED_FROZEN_GRADER"
    assert loaded.historical_replay_credit is False
    assert loaded.cg_root_dependency_chain.review_only is True
    assert loaded.cg_root_dependency_chain.qualification_credit is False
    assert (
        loaded.cg_full_focus_projection.measurement_status
        == "NOT_MEASURED_UNREPRESENTABLE"
    )


def test_sealed_v12_raw_fails_only_the_compositional_root() -> None:
    metrics = _metrics()

    assert metrics.passed is False
    assert metrics.focus_event_passed is False
    assert metrics.source_semantic_status == "FAIL"
    assert metrics.benchmark_projection_status == "FAIL"
    assert metrics.benchmark_projection is None
    assert metrics.root_selection_status == "FAIL"
    assert metrics.source_dimensions_except_root_passed is True
    assert metrics.root_only_failure is True
    assert metrics.mandatory_participants_passed is True
    assert metrics.participant_roles_passed is True
    assert metrics.semantic_axes_passed is True
    assert metrics.exact_evidence_grounding is True
    assert metrics.unsupported_extraction_count == 0
    assert metrics.failure_reasons == (
        "source root is not the outer responsible event",
    )


def test_changing_only_root_to_responsible_passes_source_lane() -> None:
    metrics = _metrics(_corrected_output())

    assert metrics.passed is True
    assert metrics.focus_event_passed is True
    assert metrics.source_semantic_status == "PASS"
    assert metrics.benchmark_projection_status == "FAIL"
    assert metrics.benchmark_projection is None
    assert metrics.root_selection_status == "PASS"
    assert metrics.root_only_failure is False
    assert metrics.failure_reasons == ()


def test_focus_local_p53_resolves_and_later_occurrence_cannot_substitute() -> None:
    case = _case()
    evidence = _contract().source_lane.exact_evidence
    occurrences = token_bounded_spans(
        source=case.source,
        scope_start=case.context_start,
        scope_end=case.context_end,
        exact_text="p53",
    )

    resolved = resolve_focus_local_occurrence(
        case,
        exact_evidence=evidence,
        exact_text="p53",
    )

    assert len(occurrences) == 2
    assert resolved.start == 1172
    assert resolved == occurrences[0]
    wrong_focus = replace(
        case,
        focus_start=occurrences[1].start,
        focus_end=occurrences[1].end,
    )
    wrong_metrics = evaluate_v13_case(
        wrong_focus,
        _corrected_output(),
        _policy(),
        _contract(),
    )
    assert wrong_metrics.passed is False
    assert wrong_metrics.exact_evidence_grounding is False


def test_infected_fibroblasts_is_required_and_accepted_context() -> None:
    metrics = _metrics(_corrected_output())

    assert metrics.mandatory_participants_passed is True
    assert metrics.participant_roles_passed is True
    assert metrics.permitted_context_count == 1
    assert metrics.unsupported_extraction_count == 0


def test_exact_cg_failure_is_separate_and_nonblocking_for_source_score() -> None:
    metrics = _metrics(_corrected_output())

    assert metrics.passed is True
    assert metrics.source_semantic_status == "PASS"
    assert metrics.benchmark_projection_status == "FAIL"
    assert metrics.benchmark_projection is None
    assert metrics.failure_reasons == ()


def test_actual_three_event_cg_chain_passes_projection_independently() -> None:
    metrics = _metrics(_cg_chain_output())

    assert metrics.passed is False
    assert metrics.source_semantic_status == "FAIL"
    assert metrics.benchmark_projection_status == "PASS"
    assert metrics.benchmark_projection_scope == "EXACT_CG_ROOT_DEPENDENCY_CHAIN"
    assert metrics.full_focus_cg_status == "NOT_MEASURED_UNREPRESENTABLE"
    projected = metrics.benchmark_projection
    assert projected is not None
    assert projected["review_only"] is True
    assert projected["qualification_blocking"] is False
    assert projected["qualification_credit"] is False
    assert len(cast("list[object]", projected["events"])) == 3
    assert projected["artana_mapping"] == {
        "events": {
            "responsible": "E1",
            "elevating": "E2",
            "levels": "E3",
        },
        "participants": {
            "cause": "P1",
            "theme": "P2",
            "dropped_source_context": ["P3"],
        },
    }


def test_broad_containment_cannot_masquerade_as_exact_cg_chain() -> None:
    output = _cg_chain_output()
    broad_triggers = {
        "E1": "shown to be responsible",
        "E2": "for elevating",
        "E3": "p53 levels",
    }
    trigger_abuse = output.model_copy(
        update={
            "inventory": tuple(
                item.model_copy(update={"trigger_text": broad_triggers[item.event_id]})
                for item in output.inventory
            )
        }
    )
    broad_participants = {
        "P1": ("HCMV immediate-early proteins were clearly shown to be responsible"),
        "P2": "elevating p53 levels",
    }
    participant_abuse = output.model_copy(
        update={
            "participants": tuple(
                item.model_copy(
                    update={
                        "exact_text": broad_participants.get(
                            item.participant_id,
                            item.exact_text,
                        )
                    }
                )
                for item in output.participants
            )
        }
    )

    trigger_metrics = _metrics(trigger_abuse)
    participant_metrics = _metrics(participant_abuse)

    assert trigger_metrics.benchmark_projection_status == "FAIL"
    assert trigger_metrics.benchmark_projection is None
    assert participant_metrics.benchmark_projection_status == "FAIL"
    assert participant_metrics.benchmark_projection is None


def test_canonical_contract_is_realizable_without_a_levels_source_event() -> None:
    output = _corrected_output()
    metrics = _metrics(output)

    assert len(output.inventory) == 2
    assert all(event.trigger_text != "levels" for event in output.inventory)
    assert metrics.passed is True
    assert metrics.benchmark_projection_status == "FAIL"
    assert metrics.benchmark_projection is None
    assert metrics.qualification_credit is False
    assert metrics.graph_writes == 0
    assert metrics.trusted_promotion is False


def test_non_complete_output_does_not_score_transport_root_anchor() -> None:
    output = _output().model_copy(update={"completeness": "ABSTAIN"})

    metrics = _metrics(output)

    assert metrics.passed is False
    assert metrics.completeness == "ABSTAIN"
    assert metrics.root_selection_status == "NOT_APPLICABLE"
    assert metrics.focus_event_passed is False
    assert metrics.root_only_failure is False
    assert metrics.source_dimensions_except_root_passed is False
    assert "source root is not the outer responsible event" not in (
        metrics.failure_reasons
    )
    assert "output completeness is ABSTAIN" in metrics.failure_reasons


def test_extra_event_and_participant_fail_the_source_contract() -> None:
    extra_event = _metrics(_cg_chain_output())
    output = _corrected_output()
    invented = output.participants[0].model_copy(update={"participant_id": "P4"})
    extra_participant = _metrics(
        output.model_copy(update={"participants": (*output.participants, invented)})
    )

    assert extra_event.source_semantic_status == "FAIL"
    assert extra_event.unsupported_extraction_count > 0
    assert extra_event.root_only_failure is False
    assert extra_participant.source_semantic_status == "FAIL"
    assert extra_participant.unsupported_extraction_count > 0
    assert extra_participant.root_only_failure is False


def test_missing_required_context_and_link_role_mutation_fail_source() -> None:
    output = _corrected_output()
    elevating_links = next(item for item in output.links if item.event_id == "E2")
    affected = next(
        item for item in elevating_links.arguments if item.role == "AFFECTED_ENTITY"
    )
    without_context_links = elevating_links.model_copy(
        update={"arguments": (affected,)}
    )
    without_context = output.model_copy(
        update={
            "participants": tuple(
                item for item in output.participants if item.participant_id != "P3"
            ),
            "links": tuple(
                without_context_links if item.event_id == "E2" else item
                for item in output.links
            ),
        }
    )
    wrong_role = affected.model_copy(update={"role": "OUTCOME"})
    wrong_role_links = elevating_links.model_copy(
        update={
            "arguments": tuple(
                wrong_role if item == affected else item
                for item in elevating_links.arguments
            )
        }
    )
    mutated_links = output.model_copy(
        update={
            "links": tuple(
                wrong_role_links if item.event_id == "E2" else item
                for item in output.links
            )
        }
    )

    missing_metrics = _metrics(without_context)
    link_metrics = _metrics(mutated_links)

    assert missing_metrics.source_semantic_status == "FAIL"
    assert missing_metrics.mandatory_participants_passed is False
    assert missing_metrics.participant_roles_passed is False
    assert link_metrics.source_semantic_status == "FAIL"
    assert link_metrics.participant_roles_passed is False
    assert link_metrics.root_only_failure is False


def test_axes_mutation_and_duplicate_stage_rows_fail_exact_cardinality() -> None:
    output = _corrected_output()
    elevating_axes = next(
        item for item in output.semantic_axes if item.event_id == "E2"
    )
    wrong_axes = elevating_axes.model_copy(update={"direction": "DECREASED"})
    axes_mutation = output.model_copy(
        update={
            "semantic_axes": tuple(
                wrong_axes if item.event_id == "E2" else item
                for item in output.semantic_axes
            )
        }
    )
    duplicate_axes = output.model_copy(
        update={"semantic_axes": (*output.semantic_axes, output.semantic_axes[0])}
    )
    duplicate_empty_link = output.links[0].model_copy(update={"arguments": ()})
    duplicate_links = output.model_copy(
        update={"links": (*output.links, duplicate_empty_link)}
    )

    mutation_metrics = _metrics(axes_mutation)
    duplicate_axes_metrics = _metrics(duplicate_axes)
    duplicate_link_metrics = _metrics(duplicate_links)

    assert mutation_metrics.semantic_axes_passed is False
    assert mutation_metrics.source_semantic_status == "FAIL"
    assert duplicate_axes_metrics.semantic_axes_passed is False
    assert "semantic axes stage cardinality or coverage differs" in (
        duplicate_axes_metrics.failure_reasons
    )
    assert duplicate_link_metrics.participant_roles_passed is False
    assert "event link stage cardinality or coverage differs" in (
        duplicate_link_metrics.failure_reasons
    )


def test_v13_composed_regression_table_preserves_all_repaired_source_lanes() -> None:
    raw_outputs = {
        case_id: REPO / "docs/validation/results/"
        f"2026-07-23-staged-generalization-v11-exposed-run-v2-{case_id}-raw.json"
        for case_id in (
            "generalization-comparison-canary",
            "generalization-uncertainty",
            "generalization-negated-association",
            "generalization-null-statistics",
        )
    }
    raw_outputs["generalization-drug-sensitivity"] = V12_DRUG_RAW
    policy = FrozenDualLanePolicy.model_validate_json(
        GRADING_PATHS.grading.policy.read_text(encoding="utf-8")
    )
    contract = _contract()
    rows: dict[str, V13CaseMetrics] = {}
    outputs: dict[str, V9StagedGeneralizationOutput] = {}
    for case_id, path in raw_outputs.items():
        case = _case(case_id)
        output = V9StagedGeneralizationOutput.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        outputs[case_id] = output
        rows[case_id] = evaluate_v13_case(
            case,
            output,
            case_policy(policy, case_id),
            contract,
        )
    nested_case = _case()
    nested = _corrected_output()
    rows[nested_case.case_id] = evaluate_v13_case(
        nested_case,
        nested,
        case_policy(policy, nested_case.case_id),
        contract,
    )

    assert set(rows) == {
        "generalization-comparison-canary",
        "generalization-uncertainty",
        "generalization-negated-association",
        "generalization-null-statistics",
        "generalization-drug-sensitivity",
        "generalization-explicit-nested-cause",
    }
    assert all(item.source_semantic_status == "PASS" for item in rows.values())
    assert all(item.passed for item in rows.values())

    uncertainty_case = _case("generalization-uncertainty")
    uncertainty = outputs["generalization-uncertainty"]
    gene = next(
        item
        for item in uncertainty.participants
        if item.entity_type == "GENE_OR_PROTEIN"
    )
    evidence = resolve_evidence(
        source=uncertainty_case.source,
        context_start=uncertainty_case.context_start,
        context_end=uncertainty_case.context_end,
        exact_text=gene.exact_evidence,
    )
    gene_span = resolve_unique_span(
        source=uncertainty_case.source,
        scope_start=evidence.start,
        scope_end=evidence.end,
        exact_text=gene.exact_text,
    )
    assert gene.exact_text == "SLC12A3"
    assert uncertainty_case.source[gene_span.start : gene_span.end] == "SLC12A3"
    assert all(
        tuple(item.evidence_items) == (gene.exact_evidence,)
        for item in uncertainty.semantic_axes
    )

    nested_links = {
        item.event_id: {
            (argument.role, argument.target_kind, argument.target_id)
            for argument in item.arguments
        }
        for item in nested.links
    }
    assert ("EFFECT_EVENT", "EVENT", "E2") in nested_links["E1"]
    assert ("AFFECTED_ENTITY", "PARTICIPANT", "P2") in nested_links["E2"]
    assert (
        "CONTEXTUAL_PARTICIPANT",
        "PARTICIPANT",
        "P3",
    ) in nested_links["E2"]


def test_non_target_case_delegates_unchanged_to_v12(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    legacy = V12CaseMetrics(
        case_id="generalization-drug-sensitivity",
        passed=False,
        focus_event_passed=True,
        source_semantic_status="PASS",
        cg_projection_status="FAIL",
        mandatory_participants_passed=True,
        participant_roles_passed=True,
        semantic_axes_passed=True,
        exact_evidence_grounding=True,
        unsupported_extraction_count=0,
        permitted_context_count=0,
        cg_projection=None,
        failure_reasons=("exact CG focus projection is unavailable",),
        historical_grader_passed=None,
    )

    def fake_v12(
        case: GeneralizationCase,
        output: StagedGeneralizationOutput,
        policy: FrozenCasePolicy,
        contract: V12TwoLaneContract,
    ) -> V12CaseMetrics:
        del output, policy, contract
        calls.append(case.case_id)
        return legacy

    monkeypatch.setattr(v13_evaluation, "evaluate_v12_case", fake_v12)
    delegated_case = replace(
        _case(),
        case_id="generalization-drug-sensitivity",
    )

    metrics = evaluate_v13_case(
        delegated_case,
        _output(),
        _policy(),
        _contract(),
    )

    assert calls == ["generalization-drug-sensitivity"]
    assert metrics.passed is True
    assert metrics.source_semantic_status == "PASS"
    assert metrics.benchmark_projection_status == "FAIL"
    assert metrics.benchmark_projection_scope == "DRUG_FOCUS_EVENT"
    assert metrics.benchmark_projection is None
    assert metrics.full_focus_cg_status == "NOT_APPLICABLE"
    assert metrics.failure_reasons == ()


def _string(record: dict[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _integer(record: dict[str, object], key: str) -> int:
    value = record.get(key)
    if not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value
