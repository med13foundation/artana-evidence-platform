"""Regression tests for source-locked semantic selector model comparison."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    EvidenceSelectionSemanticAgentEvaluation,
)
from artana_evidence_api.evidence_selection.repeatability.adoption import (
    semantic_model_adoption_decision,
)
from artana_evidence_api.evidence_selection.repeatability.artifacts import (
    render_comparison_markdown,
    write_json_model,
)
from artana_evidence_api.evidence_selection.repeatability.comparison import (
    build_semantic_model_comparison,
)
from artana_evidence_api.evidence_selection.repeatability.contracts import (
    SemanticModelComparisonThresholds,
    SemanticModelEvaluationRun,
)
from artana_evidence_api.evidence_selection.repeatability.protocol import sha256_path
from pydantic import ValidationError

from .evidence_selection_semantic_repeatability_test_support import (
    build_model_runs,
    comparison_protocol,
    load_fixture,
)


@pytest.mark.asyncio
async def test_comparison_adopts_material_worst_run_improvement(
    tmp_path,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
        abstain_record_ids=frozenset({"brca1:pmid:40403695"}),
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
        cost_per_run=0.012,
        latency_per_run=1.1,
    )

    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )

    assert report.current_summary.worst_recall == pytest.approx(12 / 13)
    assert report.candidate_summary.worst_recall == 1.0
    assert report.decision.outcome == "adopt_candidate"
    assert report.decision.reason_codes == (
        "candidate_materially_improves_worst_run_quality",
    )
    assert report.cross_model_disagreement_count == 1
    assert report.selected_model_repeatability_passed is True
    assert report.calibration_status == "unavailable"
    assert report.calibration_ece is None
    assert report.production_readiness_claim is False


@pytest.mark.asyncio
async def test_comparison_recomputes_scores_from_categorical_decisions(
    tmp_path,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
        abstain_record_ids=frozenset({"brca1:pmid:40403695"}),
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
    )
    evaluation_path = Path(current_runs[0].evaluation_path)
    tampered_evaluation = EvidenceSelectionSemanticAgentEvaluation.model_validate_json(
        evaluation_path.read_text(encoding="utf-8"),
    ).model_copy(update={"score": candidate_runs[0].score})
    write_json_model(path=tmp_path / "current-run-1.json", model=tampered_evaluation)
    tampered_current = (
        current_runs[0].model_copy(
            update={
                "score": candidate_runs[0].score,
                "evaluation_sha256": sha256_path(tmp_path / "current-run-1.json"),
            },
        ),
        *current_runs[1:],
    )

    with pytest.raises(ValueError, match="numeric score does not match"):
        build_semantic_model_comparison(
            protocol=protocol,
            fixture=fixture,
            current_runs=tampered_current,
            candidate_runs=candidate_runs,
            generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_comparison_recomputes_protocol_source_lock(tmp_path) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
    )
    tampered_protocol = protocol.model_copy(update={"source_lock_sha256": "b" * 64})

    with pytest.raises(ValueError, match="source lock is invalid"):
        build_semantic_model_comparison(
            protocol=tampered_protocol,
            fixture=fixture,
            current_runs=current_runs,
            candidate_runs=candidate_runs,
            generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_comparison_rejects_replayed_agent_executions(tmp_path) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
    )
    replayed_second = current_runs[0].model_copy(
        update={
            "run_index": 2,
            "evaluation_path": "distinct-current-run-2.json",
            "evaluation_sha256": "b" * 64,
        },
    )

    with pytest.raises(ValueError, match="distinct agent executions"):
        build_semantic_model_comparison(
            protocol=protocol,
            fixture=fixture,
            current_runs=(current_runs[0], replayed_second, current_runs[2]),
            candidate_runs=candidate_runs,
            generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_comparison_is_inconclusive_without_complete_runtime_telemetry(
    tmp_path,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
        telemetry_status="partial",
    )

    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )

    assert report.decision.outcome == "inconclusive"
    assert report.decision.reason_codes == ("runtime_telemetry_incomplete",)
    assert report.selected_model_repeatability_passed is False


@pytest.mark.asyncio
async def test_per_case_floor_blocks_good_looking_micro_average(tmp_path) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    weak_record = frozenset({"egfr:pmid:27959700"})
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
        abstain_record_ids=weak_record,
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
        abstain_record_ids=weak_record,
    )

    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )

    assert report.current_summary.worst_recall == pytest.approx(12 / 13)
    assert report.current_summary.minimum_case_recall == pytest.approx(2 / 3)
    assert report.current_summary.quality_gate_passed is False
    assert report.decision.outcome == "inconclusive"
    assert report.decision.reason_codes == (
        "current_and_candidate_quality_gates_failed",
    )


@pytest.mark.asyncio
async def test_micro_coverage_gate_blocks_abstaining_on_every_negative(
    tmp_path,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    negative_record_ids = frozenset(
        record.record_id
        for case in fixture.cases
        for record in case.records
        if record.expected_label == "reject"
    )
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
        abstain_record_ids=negative_record_ids,
    )

    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )

    assert report.candidate_summary.worst_precision == 1.0
    assert report.candidate_summary.worst_recall == 1.0
    assert report.candidate_summary.worst_decision_coverage < 0.5
    assert report.candidate_summary.quality_gate_passed is False
    assert report.decision.outcome == "keep_current"
    assert report.decision.reason_codes == ("candidate_quality_gate_failed",)


@pytest.mark.asyncio
async def test_per_case_coverage_gate_blocks_localized_abstention_gaming(
    tmp_path,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    weak_case = next(case for case in fixture.cases if case.case_id.startswith("egfr"))
    weak_case_negative_ids = frozenset(
        record.record_id
        for record in weak_case.records
        if record.expected_label == "reject"
    )
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
        abstain_record_ids=weak_case_negative_ids,
    )

    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )

    assert report.candidate_summary.worst_decision_coverage >= 0.8
    assert report.candidate_summary.minimum_case_decision_coverage == pytest.approx(
        3 / 8,
    )
    assert report.candidate_summary.quality_gate_passed is False
    assert report.decision.outcome == "keep_current"


@pytest.mark.asyncio
async def test_record_instability_fails_quality_with_zero_aggregate_variance(
    tmp_path,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    unstable_positive_ids = (
        "brca1:pmid:40403695",
        "brca1:pmid:22889855",
        "brca1:pmid:26195121",
    )
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
        abstain_record_ids_by_run=tuple(
            frozenset({record_id}) for record_id in unstable_positive_ids
        ),
    )

    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )

    assert report.candidate_summary.recall_variance == 0.0
    assert report.candidate_summary.unstable_record_count == 3
    assert report.candidate_summary.quality_gate_passed is False
    assert report.decision.outcome == "keep_current"
    assert report.decision.reason_codes == ("candidate_quality_gate_failed",)


@pytest.mark.asyncio
async def test_identical_quality_keeps_current_without_model_self_score(
    tmp_path,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
    )

    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )

    assert report.decision.outcome == "keep_current"
    assert report.decision.reason_codes == ("candidate_has_no_material_benefit",)
    assert report.selected_model_repeatability_passed is True
    markdown = render_comparison_markdown(report)
    assert "Agent-authored" not in markdown
    assert "neither model supplies a score used for adoption" in markdown
    assert "Production readiness claim: **NO**" in markdown


@pytest.mark.asyncio
async def test_policy_does_not_adopt_variance_only_candidate(
    tmp_path,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
    )
    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )
    current = report.current_summary.model_copy(
        update={
            "precision_variance": 0.01,
            "recall_variance": 0.01,
            "total_cost_usd": 1.0,
            "total_model_latency_seconds": 10.0,
        },
    )
    candidate = report.candidate_summary.model_copy(
        update={
            "precision_variance": 0.002,
            "recall_variance": 0.002,
            "total_cost_usd": 1.2,
            "total_model_latency_seconds": 12.0,
        },
    )

    decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current,
        candidate=candidate,
    )

    assert decision.outcome == "keep_current"
    assert decision.reason_codes == ("candidate_has_no_material_benefit",)

    ten_run_decision = semantic_model_adoption_decision(
        protocol=protocol.model_copy(update={"runs_per_model": 10}),
        current=current.model_copy(update={"run_count": 10}),
        candidate=candidate.model_copy(update={"run_count": 10}),
    )
    assert ten_run_decision.outcome == "keep_current"
    assert ten_run_decision.reason_codes == ("candidate_has_no_material_benefit",)


@pytest.mark.parametrize(
    ("resource_field", "candidate_value"),
    [
        ("total_cost_usd", 100.0),
        ("total_model_latency_seconds", 100.0),
    ],
)
@pytest.mark.asyncio
async def test_positive_over_zero_resource_ratio_cannot_adopt_candidate(
    tmp_path,
    resource_field: str,
    candidate_value: float,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
        abstain_record_ids=frozenset({"brca1:pmid:40403695"}),
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
    )
    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )
    current = report.current_summary.model_copy(update={resource_field: 0.0})
    candidate = report.candidate_summary.model_copy(
        update={resource_field: candidate_value},
    )

    decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current,
        candidate=candidate,
    )

    assert decision.outcome == "keep_current"
    assert decision.selected_model_id == current.model_id
    assert decision.reason_codes == ("runtime_resource_ratio_undefined",)

    only_passing_candidate_decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current.model_copy(update={"quality_gate_passed": False}),
        candidate=candidate,
    )
    assert only_passing_candidate_decision.outcome == "inconclusive"
    assert only_passing_candidate_decision.selected_model_id is None
    assert only_passing_candidate_decision.reason_codes == (
        "runtime_resource_ratio_undefined",
    )


@pytest.mark.asyncio
async def test_policy_rejects_expensive_candidate_without_larger_improvement(
    tmp_path,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
    )
    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )
    current = report.current_summary.model_copy(
        update={
            "worst_recall": 0.90,
            "total_cost_usd": 1.0,
            "total_model_latency_seconds": 10.0,
        },
    )
    candidate = report.candidate_summary.model_copy(
        update={
            "worst_recall": 0.93,
            "total_cost_usd": 2.5,
            "total_model_latency_seconds": 25.0,
        },
    )

    decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current,
        candidate=candidate,
    )

    assert decision.outcome == "keep_current"
    assert decision.reason_codes == ("candidate_resource_cost_not_justified",)


@pytest.mark.asyncio
async def test_policy_adopts_only_model_passing_quality_gate(tmp_path) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
    )
    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )
    current = report.current_summary.model_copy(update={"quality_gate_passed": False})

    decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current,
        candidate=report.candidate_summary,
    )

    assert decision.outcome == "adopt_candidate"
    assert decision.selected_model_id == report.candidate_summary.model_id
    assert decision.reason_codes == ("candidate_is_only_model_passing_quality_gate",)


@pytest.mark.asyncio
async def test_policy_is_inconclusive_when_only_passing_model_is_too_expensive(
    tmp_path,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="current",
    )
    candidate_runs = await build_model_runs(
        tmp_path=tmp_path,
        fixture=fixture,
        protocol=protocol,
        role="candidate",
    )
    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )
    current = report.current_summary.model_copy(update={"quality_gate_passed": False})
    candidate = report.candidate_summary.model_copy(
        update={
            "total_cost_usd": current.total_cost_usd * 3,
            "total_model_latency_seconds": current.total_model_latency_seconds * 3,
        },
    )

    decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current,
        candidate=candidate,
    )

    assert decision.outcome == "inconclusive"
    assert decision.selected_model_id is None
    assert decision.reason_codes == ("candidate_resource_cost_not_justified",)


@pytest.mark.asyncio
async def test_run_contract_rejects_numeric_agent_self_score_alias(tmp_path) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    run = (
        await build_model_runs(
            tmp_path=tmp_path,
            fixture=fixture,
            protocol=protocol,
            role="current",
        )
    )[0]
    payload = run.model_dump(mode="json")
    payload["agent_confidence"] = 0.99

    with pytest.raises(ValidationError):
        SemanticModelEvaluationRun.model_validate(payload)

    payload.pop("agent_confidence")
    payload["calibration_status"] = "validated"
    with pytest.raises(ValidationError):
        SemanticModelEvaluationRun.model_validate(payload)


def test_threshold_contract_cannot_relax_production_floors() -> None:
    with pytest.raises(ValidationError):
        SemanticModelComparisonThresholds(minimum_worst_precision=0.79)
    with pytest.raises(ValidationError):
        SemanticModelComparisonThresholds(minimum_runs_per_model=2)
    with pytest.raises(ValidationError):
        SemanticModelComparisonThresholds(
            material_worst_metric_improvement=0.01,
        )
    with pytest.raises(ValidationError):
        SemanticModelComparisonThresholds(minimum_worst_decision_coverage=0.79)
    with pytest.raises(ValidationError):
        SemanticModelComparisonThresholds(minimum_case_decision_coverage=0.69)
