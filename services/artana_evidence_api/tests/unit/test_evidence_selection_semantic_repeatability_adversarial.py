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
    SemanticRuntimeLedgerObservation,
    SemanticRuntimeModelAttempt,
)
from artana_evidence_api.evidence_selection.repeatability.runtime.ledger import (
    aggregate_semantic_model_attempts,
    semantic_ledger_status,
    semantic_model_attempts_sha256,
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
    for attempt in ledger["model_attempts"]:
        attempt["model_id"] = "openai:forged-model"
    normalized_attempts = tuple(
        SemanticRuntimeModelAttempt.model_validate(attempt)
        for attempt in ledger["model_attempts"]
    )
    ledger["model_attempts_sha256"] = semantic_model_attempts_sha256(
        normalized_attempts,
    )

    with pytest.raises(ValidationError, match="telemetry model must match"):
        SemanticModelEvaluationRun.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["omit", "insert"])
async def test_replay_rejects_attempt_manifest_drift_after_inner_rehash(
    tmp_path,
    operation: str,
) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    current_runs, candidate_runs = await _model_matrix(tmp_path)
    run = current_runs[0]
    attempts = list(run.telemetry.ledger.model_attempts)
    if operation == "omit":
        attempts.pop()
    else:
        source = attempts[-1]
        attempts.append(
            source.model_copy(
                update={
                    "execution_id": "injected-execution",
                    "attempt_sequence": len(attempts) + 1,
                    "batch_attempt_number": source.batch_attempt_number + 1,
                    "source_model_requested_event_id": "injected-request",
                    "model_requested_event_hash": "b" * 64,
                    "terminal_event_id": "injected-terminal",
                    "terminal_event_hash": "c" * 64,
                },
            ),
        )
    forged_run = _run_with_attempts(run, tuple(attempts))

    with pytest.raises(ValueError, match="does not exactly match runtime ledger"):
        build_semantic_model_comparison(
            protocol=protocol,
            fixture=fixture,
            current_runs=(forged_run, *current_runs[1:]),
            candidate_runs=candidate_runs,
            generated_at=datetime(2026, 7, 13, 8, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_runtime_ledger_rejects_duplicate_attempt_after_inner_rehash(tmp_path) -> None:
    current_runs, _candidate_runs = await _model_matrix(tmp_path)
    ledger = current_runs[0].telemetry.ledger
    attempts = (*ledger.model_attempts, ledger.model_attempts[-1])
    payload = ledger.model_dump(mode="python")
    payload["execution_ids"] = (*ledger.execution_ids, ledger.execution_ids[-1])
    payload["model_attempt_count"] = len(attempts)
    payload["model_terminal_count"] = len(attempts)
    payload["model_attempts"] = attempts
    payload["model_attempts_sha256"] = semantic_model_attempts_sha256(attempts)

    with pytest.raises(ValidationError, match="execution IDs must be unique"):
        SemanticRuntimeLedgerObservation.model_validate(payload)


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
async def test_materially_better_candidate_that_retries_every_batch_is_not_adopted(
    tmp_path,
) -> None:
    protocol = comparison_protocol()
    current, candidate = await _summaries(tmp_path)
    candidate = candidate.model_copy(
        update={
            "worst_precision": min(1.0, current.worst_precision + 0.1),
            "worst_recall": min(1.0, current.worst_recall + 0.1),
            "model_attempt_count": 24,
            "rejected_attempt_count": 12,
            "attempt_reliability_passed": False,
        },
    )

    decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current,
        candidate=candidate,
    )

    assert decision.outcome == "keep_current"
    assert decision.reason_codes == ("candidate_attempt_reliability_failed",)


@pytest.mark.asyncio
async def test_missing_candidate_telemetry_precedes_retry_reliability(tmp_path) -> None:
    protocol = comparison_protocol()
    current, candidate = await _summaries(tmp_path)
    candidate = candidate.model_copy(
        update={
            "telemetry_complete": False,
            "telemetry_unavailable_attempt_count": 1,
            "attempt_reliability_passed": False,
        },
    )

    decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current,
        candidate=candidate,
    )

    assert decision.outcome == "inconclusive"
    assert decision.selected_model_id is None
    assert decision.reason_codes == ("runtime_telemetry_incomplete",)


@pytest.mark.asyncio
async def test_unreliable_only_quality_candidate_is_not_adopted(tmp_path) -> None:
    protocol = comparison_protocol()
    current, candidate = await _summaries(tmp_path)
    current = current.model_copy(update={"quality_gate_passed": False})
    candidate = candidate.model_copy(update={"attempt_reliability_passed": False})

    decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current,
        candidate=candidate,
    )

    assert decision.outcome == "inconclusive"
    assert decision.selected_model_id is None
    assert decision.reason_codes == ("candidate_attempt_reliability_failed",)


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
        manifest_name = f"{run.model_role}-{run.run_index}-attempts.json"
        (bundle / name).symlink_to(run.evaluation_path)
        (bundle / manifest_name).symlink_to(run.attempt_manifest_path)
        escaped.append(
            run.model_copy(
                update={
                    "evaluation_path": name,
                    "attempt_manifest_path": manifest_name,
                },
            ),
        )
    return tuple(escaped)


def _run_with_attempts(
    run: SemanticModelEvaluationRun,
    attempts: tuple[SemanticRuntimeModelAttempt, ...],
) -> SemanticModelEvaluationRun:
    aggregate = aggregate_semantic_model_attempts(attempts)
    ledger = SemanticRuntimeLedgerObservation(
        status=semantic_ledger_status(attempts),
        expected_model_id=run.model_id,
        execution_ids=tuple(attempt.execution_id for attempt in attempts),
        model_attempt_count=len(attempts),
        model_terminal_count=sum(
            attempt.terminal_outcome is not None for attempt in attempts
        ),
        model_attempts=attempts,
        model_attempts_sha256=semantic_model_attempts_sha256(attempts),
        prompt_tokens=aggregate.prompt_tokens,
        completion_tokens=aggregate.completion_tokens,
        total_tokens=aggregate.total_tokens,
        cost_usd=aggregate.cost_usd,
        model_latency_seconds=aggregate.model_latency_seconds,
        token_usage_provenance=aggregate.token_usage_provenance,
        cost_usage_provenance=aggregate.cost_usage_provenance,
        unavailable_reasons=aggregate.unavailable_reasons,
    )
    return run.model_copy(
        update={
            "telemetry": run.telemetry.model_copy(
                update={
                    "ledger": ledger,
                    "wall_clock": run.telemetry.wall_clock.model_copy(
                        update={"execution_ids": ledger.execution_ids},
                    ),
                },
            ),
        },
    )
