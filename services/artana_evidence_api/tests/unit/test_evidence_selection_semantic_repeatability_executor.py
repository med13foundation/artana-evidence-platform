"""End-to-end local executor tests for semantic model repeatability."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from artana.events import EventType, ModelTerminalPayload
from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    EvidenceSelectionSemanticAgentEvaluation,
)
from artana_evidence_api.evidence_selection.repeatability.bundle import (
    digest_path,
    failure_path,
    verify_published_bundle,
)
from artana_evidence_api.evidence_selection.repeatability.executor import (
    execute_semantic_model_comparison,
)
from artana_evidence_api.evidence_selection.repeatability.protocol import sha256_path
from artana_evidence_api.evidence_selection.repeatability.verifier import (
    verify_semantic_comparison_bundle,
)
from artana_evidence_api.evidence_selection.semantic.contracts import (
    EvidenceSelectionSemanticBatchContract,
)
from artana_evidence_api.evidence_selection.semantic.model import (
    EvidenceSelectionSemanticContext,
    EvidenceSelectionSemanticModelRunner,
)

from .evidence_selection_semantic_repeatability_test_support import (
    ExpectedLabelRunner,
    comparison_protocol,
    load_fixture,
)


class _LedgerStore:
    async def get_events_for_run(self, execution_id: str) -> list[object]:
        return [
            SimpleNamespace(
                event_type=EventType.MODEL_TERMINAL,
                payload=ModelTerminalPayload(
                    outcome="completed",
                    model=execution_id.split("|", 1)[0],
                    model_cycle_id=f"cycle-{execution_id}",
                    source_model_requested_event_id=f"request-{execution_id}",
                    elapsed_ms=100,
                    prompt_tokens=50,
                    completion_tokens=10,
                    cost_usd=0.001,
                ),
            ),
        ]

    async def close(self) -> None:
        return None


class _RetryOnceRunner:
    def __init__(self, *, inner: ExpectedLabelRunner) -> None:
        self._inner = inner
        self._invalid_contract_returned = False

    async def assess(
        self,
        *,
        context: EvidenceSelectionSemanticContext,
    ) -> EvidenceSelectionSemanticBatchContract:
        contract = await self._inner.assess(context=context)
        if not self._invalid_contract_returned:
            self._invalid_contract_returned = True
            return contract.model_copy(update={"assessments": ()})
        return contract

    def model_id(self) -> str | None:
        return self._inner.model_id()

    def execution_ids(self) -> tuple[str, ...]:
        return self._inner.execution_ids()


@pytest.mark.asyncio
async def test_executor_writes_complete_source_locked_matrix(tmp_path) -> None:
    fixture = load_fixture()
    protocol = comparison_protocol()
    factory_calls = 0

    def runner_factory(model_id: str) -> EvidenceSelectionSemanticModelRunner:
        nonlocal factory_calls
        factory_calls += 1
        staging_dirs = tuple(tmp_path.glob(".comparison.*.staging"))
        assert len(staging_dirs) == 1
        assert (
            staging_dirs[0] / "semantic_model_comparison_protocol.json"
        ).is_file(), "protocol must be frozen before the first model call"
        return ExpectedLabelRunner(
            fixture=fixture,
            model_id=model_id,
            execution_prefix=f"{model_id}|execution-{factory_calls}",
        )

    output_dir = tmp_path / "comparison"
    report = await execute_semantic_model_comparison(
        protocol=protocol,
        output_dir=output_dir,
        runner_factory=runner_factory,
        store_factory=_LedgerStore,
    )

    assert report.decision.outcome == "keep_current"
    assert report.selected_model_repeatability_passed is True
    assert report.current_summary.telemetry_complete is True
    assert report.candidate_summary.telemetry_complete is True
    assert factory_calls == 6
    assert (output_dir / "semantic_model_comparison_protocol.json").exists()
    assert (output_dir / "semantic_model_comparison_report.json").exists()
    assert (output_dir / "semantic_model_comparison_report.md").exists()
    assert (output_dir / "semantic_model_comparison_manifest.json").exists()
    assert digest_path(output_dir).exists()
    assert len(tuple(output_dir.glob("current-run-*.json"))) == 3
    assert len(tuple(output_dir.glob("candidate-run-*.json"))) == 3
    assert [
        run.agent_run_ids[0].split("|", 1)[0]
        for run in (*report.current_runs, *report.candidate_runs)
    ] == [protocol.current_model_id] * 3 + [protocol.candidate_model_id] * 3
    assert [run.agent_run_ids[0].split("|", 1)[1].split("-batch", 1)[0] for run in report.current_runs] == [
        "execution-1",
        "execution-3",
        "execution-5",
    ]
    assert [run.agent_run_ids[0].split("|", 1)[1].split("-batch", 1)[0] for run in report.candidate_runs] == [
        "execution-2",
        "execution-4",
        "execution-6",
    ]
    verify_published_bundle(output_dir)
    verify_semantic_comparison_bundle(output_dir)


@pytest.mark.asyncio
async def test_executor_refuses_existing_output_directory(tmp_path) -> None:
    output_dir = tmp_path / "existing"
    output_dir.mkdir()

    with pytest.raises(ValueError, match="must not already exist"):
        await execute_semantic_model_comparison(
            protocol=comparison_protocol(),
            output_dir=output_dir,
        )


@pytest.mark.asyncio
async def test_executor_accounts_for_failed_validation_retry_executions(
    tmp_path,
) -> None:
    fixture = load_fixture()
    output_dir = tmp_path / "comparison"
    factory_calls = 0

    def runner_factory(model_id: str) -> EvidenceSelectionSemanticModelRunner:
        nonlocal factory_calls
        factory_calls += 1
        return _RetryOnceRunner(
            inner=ExpectedLabelRunner(
                fixture=fixture,
                model_id=model_id,
                execution_prefix=f"{model_id}|retry-{factory_calls}",
            ),
        )

    report = await execute_semantic_model_comparison(
        protocol=comparison_protocol(),
        output_dir=output_dir,
        runner_factory=runner_factory,
        store_factory=_LedgerStore,
    )

    first_run = report.current_runs[0]
    successful_ids = {
        result.agent_run_id
        for result in _evaluation(output_dir / first_run.evaluation_path).record_results
    }
    assert len(first_run.agent_run_ids) == len(successful_ids) + 1
    assert successful_ids.issubset(first_run.agent_run_ids)
    assert first_run.telemetry.ledger.model_terminal_count == len(
        first_run.agent_run_ids,
    )
    assert first_run.telemetry.ledger.total_tokens == 60 * len(
        first_run.agent_run_ids,
    )


@pytest.mark.asyncio
async def test_executor_failure_never_publishes_partial_evidence(tmp_path) -> None:
    output_dir = tmp_path / "comparison"

    def failing_runner_factory(_model_id: str):
        raise RuntimeError("synthetic execution failure")

    with pytest.raises(RuntimeError, match="synthetic execution failure"):
        await execute_semantic_model_comparison(
            protocol=comparison_protocol(),
            output_dir=output_dir,
            runner_factory=failing_runner_factory,
            store_factory=_LedgerStore,
        )

    assert not output_dir.exists()
    assert failure_path(output_dir).is_file()
    assert not tuple(tmp_path.glob(".comparison.*.staging"))


@pytest.mark.asyncio
async def test_executor_finalization_guard_blocks_source_or_repository_drift(
    tmp_path,
) -> None:
    fixture = load_fixture()
    output_dir = tmp_path / "comparison"
    factory_calls = 0

    def runner_factory(model_id: str) -> EvidenceSelectionSemanticModelRunner:
        nonlocal factory_calls
        factory_calls += 1
        return ExpectedLabelRunner(
            fixture=fixture,
            model_id=model_id,
            execution_prefix=f"{model_id}|execution-{factory_calls}",
        )

    def reject_finalization() -> None:
        raise ValueError("repository state changed during comparison")

    with pytest.raises(ValueError, match="repository state changed"):
        await execute_semantic_model_comparison(
            protocol=comparison_protocol(),
            output_dir=output_dir,
            runner_factory=runner_factory,
            store_factory=_LedgerStore,
            finalization_guard=reject_finalization,
        )

    assert not output_dir.exists()
    assert failure_path(output_dir).is_file()


@pytest.mark.asyncio
async def test_executor_rejects_fixture_label_drift_from_frozen_protocol(
    tmp_path,
) -> None:
    fixture_path = tmp_path / "fixture.json"
    baseline_path = tmp_path / "baseline.json"
    protocol = comparison_protocol()
    shutil.copyfile(protocol.fixture_path, fixture_path)
    shutil.copyfile(protocol.baseline_report_path, baseline_path)
    copied_protocol = protocol.model_copy(
        update={
            "fixture_path": str(fixture_path),
            "baseline_report_path": str(baseline_path),
        },
    )
    fixture_payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture_payload["cases"][0]["records"][0]["expected_label"] = "reject"
    fixture_path.write_text(json.dumps(fixture_payload), encoding="utf-8")

    with pytest.raises(ValueError, match="fixture bytes do not match"):
        await execute_semantic_model_comparison(
            protocol=copied_protocol,
            output_dir=tmp_path / "comparison",
        )


@pytest.mark.asyncio
async def test_bundle_verifier_rejects_artifact_tampering(tmp_path) -> None:
    fixture = load_fixture()
    output_dir = tmp_path / "comparison"
    factory_calls = 0

    def runner_factory(model_id: str) -> EvidenceSelectionSemanticModelRunner:
        nonlocal factory_calls
        factory_calls += 1
        return ExpectedLabelRunner(
            fixture=fixture,
            model_id=model_id,
            execution_prefix=f"{model_id}|execution-{factory_calls}",
        )

    await execute_semantic_model_comparison(
        protocol=comparison_protocol(),
        output_dir=output_dir,
        runner_factory=runner_factory,
        store_factory=_LedgerStore,
    )
    report_path = output_dir / "semantic_model_comparison_report.md"
    report_path.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact digest mismatch"):
        verify_published_bundle(output_dir)


@pytest.mark.asyncio
async def test_semantic_verifier_rejects_forged_derived_report(tmp_path) -> None:
    output_dir = await _build_bundle(tmp_path)
    report_path = output_dir / "semantic_model_comparison_report.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["selected_model_repeatability_passed"] = False
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _reanchor_artifact(output_dir=output_dir, artifact=report_path)

    verify_published_bundle(output_dir)
    with pytest.raises(ValueError, match="does not match recomputation"):
        verify_semantic_comparison_bundle(output_dir)


def _evaluation(path: Path) -> EvidenceSelectionSemanticAgentEvaluation:
    return EvidenceSelectionSemanticAgentEvaluation.model_validate_json(
        path.read_text(encoding="utf-8"),
    )


async def _build_bundle(tmp_path: Path) -> Path:
    fixture = load_fixture()
    output_dir = tmp_path / "comparison"
    factory_calls = 0

    def runner_factory(model_id: str) -> EvidenceSelectionSemanticModelRunner:
        nonlocal factory_calls
        factory_calls += 1
        return ExpectedLabelRunner(
            fixture=fixture,
            model_id=model_id,
            execution_prefix=f"{model_id}|execution-{factory_calls}",
        )

    await execute_semantic_model_comparison(
        protocol=comparison_protocol(),
        output_dir=output_dir,
        runner_factory=runner_factory,
        store_factory=_LedgerStore,
    )
    return output_dir


def _reanchor_artifact(*, output_dir: Path, artifact: Path) -> None:
    manifest_path = output_dir / "semantic_model_comparison_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    relative = artifact.relative_to(output_dir).as_posix()
    for entry in manifest["entries"]:
        if entry["relative_path"] == relative:
            entry["sha256"] = sha256_path(artifact)
            entry["size_bytes"] = artifact.stat().st_size
            break
    else:
        raise AssertionError(f"missing manifest entry for {relative}")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    digest_path(output_dir).write_text(
        f"{sha256_path(manifest_path)}\n",
        encoding="ascii",
    )
