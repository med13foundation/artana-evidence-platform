"""Adversarial integrity regressions for semantic model comparisons."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from artana_evidence_api.evidence_selection.repeatability.adoption import (
    semantic_model_adoption_decision,
)
from artana_evidence_api.evidence_selection.repeatability.comparison import (
    build_semantic_model_comparison,
)
from artana_evidence_api.evidence_selection.repeatability.contracts import (
    SemanticModelEvaluationRun,
    SemanticRepositorySourceFile,
    SemanticRuntimeTerminalEvent,
    semantic_terminal_events_sha256,
)
from pydantic import ValidationError

from .evidence_selection_semantic_repeatability_test_support import (
    build_model_runs,
    comparison_protocol,
    load_fixture,
)


@pytest.mark.parametrize("path", ["/tmp/source.json", "../source.json"])
def test_repository_source_contract_rejects_path_escape(path: str) -> None:
    with pytest.raises(ValidationError, match="canonical and relative"):
        SemanticRepositorySourceFile(
            role="sanitized_source_snapshot",
            relative_path=path,
            sha256="a" * 64,
        )


@pytest.mark.asyncio
async def test_comparison_rejects_in_memory_fixture_drift(tmp_path) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs, candidate_runs = await _model_matrix(tmp_path)
    payload = fixture.model_dump(mode="python")
    first_record = payload["cases"][0]["records"][0]
    first_record["expected_label"] = (
        "reject" if first_record["expected_label"] == "select" else "select"
    )
    drifted_fixture = type(fixture).model_validate(payload)

    with pytest.raises(ValueError, match="fixture object drifted"):
        build_semantic_model_comparison(
            protocol=protocol,
            fixture=drifted_fixture,
            current_runs=current_runs,
            candidate_runs=candidate_runs,
            generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_bundle_context_rejects_absolute_artifact_paths(tmp_path) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs, candidate_runs = await _model_matrix(tmp_path)

    with pytest.raises(ValueError, match="must use relative paths"):
        build_semantic_model_comparison(
            protocol=protocol,
            fixture=fixture,
            current_runs=current_runs,
            candidate_runs=candidate_runs,
            generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
            artifact_root=tmp_path / "bundle",
        )


@pytest.mark.asyncio
async def test_bundle_context_rejects_symlink_artifact_escape(tmp_path) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs, candidate_runs = await _model_matrix(tmp_path)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    escaped_current = _symlink_run_group(bundle, current_runs)
    escaped_candidate = _symlink_run_group(bundle, candidate_runs)

    with pytest.raises(ValueError, match="escapes its artifact root"):
        build_semantic_model_comparison(
            protocol=protocol,
            fixture=fixture,
            current_runs=escaped_current,
            candidate_runs=escaped_candidate,
            generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
            artifact_root=bundle,
        )


@pytest.mark.asyncio
async def test_run_contract_rejects_telemetry_for_another_model(tmp_path) -> None:
    current_runs, _candidate_runs = await _model_matrix(tmp_path)
    run = current_runs[0]
    payload = run.model_dump(mode="python")
    ledger = payload["telemetry"]["ledger"]
    ledger["expected_model_id"] = "openai:forged-model"
    for event in ledger["terminal_events"]:
        event["model_id"] = "openai:forged-model"
    normalized_events = tuple(
        SemanticRuntimeTerminalEvent.model_validate(event)
        for event in ledger["terminal_events"]
    )
    ledger["terminal_events_sha256"] = semantic_terminal_events_sha256(
        normalized_events,
    )

    with pytest.raises(ValidationError, match="telemetry model must match"):
        SemanticModelEvaluationRun.model_validate(payload)


@pytest.mark.asyncio
async def test_material_gain_cannot_override_absolute_resource_cap(tmp_path) -> None:
    protocol = comparison_protocol()
    current, candidate = await _summaries(tmp_path)
    current = current.model_copy(
        update={
            "worst_recall": 0.80,
            "total_cost_usd": 1.0,
            "total_model_latency_seconds": 1.0,
        },
    )
    candidate = candidate.model_copy(
        update={
            "worst_recall": 0.90,
            "total_cost_usd": 10_000.0,
            "total_model_latency_seconds": 1_000.0,
        },
    )

    decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current,
        candidate=candidate,
    )

    assert decision.outcome == "keep_current"
    assert decision.reason_codes == ("candidate_exceeds_maximum_resource_ratio",)

    only_passing = semantic_model_adoption_decision(
        protocol=protocol,
        current=current.model_copy(update={"quality_gate_passed": False}),
        candidate=candidate,
    )
    assert only_passing.outcome == "inconclusive"
    assert only_passing.reason_codes == ("candidate_exceeds_maximum_resource_ratio",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resource_field",
    ["total_cost_usd", "total_model_latency_seconds"],
)
async def test_zero_over_zero_resource_ratio_fails_closed(
    tmp_path,
    resource_field: str,
) -> None:
    protocol = comparison_protocol()
    current, candidate = await _summaries(tmp_path)
    current = current.model_copy(update={resource_field: 0.0})
    candidate = candidate.model_copy(update={resource_field: 0.0})

    decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current,
        candidate=candidate,
    )

    assert decision.outcome == "keep_current"
    assert decision.reason_codes == ("runtime_resource_ratio_undefined",)


async def _model_matrix(tmp_path):
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
    return current_runs, candidate_runs


async def _summaries(tmp_path):
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs, candidate_runs = await _model_matrix(tmp_path)
    report = build_semantic_model_comparison(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
    )
    return report.current_summary, report.candidate_summary


def _symlink_run_group(bundle, runs):
    escaped = []
    for run in runs:
        name = f"{run.model_role}-{run.run_index}.json"
        (bundle / name).symlink_to(run.evaluation_path)
        escaped.append(run.model_copy(update={"evaluation_path": name}))
    return tuple(escaped)
