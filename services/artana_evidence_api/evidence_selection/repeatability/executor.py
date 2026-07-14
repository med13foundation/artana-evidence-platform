"""Live execution of a frozen semantic-selector model comparison protocol."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    evaluate_semantic_selection_agent,
    render_semantic_agent_evaluation_markdown,
)
from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    EvidenceSelectionSemanticDiagnosticFixture,
    load_semantic_diagnostic_fixture,
)
from artana_evidence_api.evidence_selection.diagnostics.report import (
    EvidenceSelectionSemanticDiagnosticReport,
)
from artana_evidence_api.evidence_selection.semantic.model import (
    ArtanaEvidenceSelectionSemanticModelRunner,
    EvidenceSelectionSemanticModelRunner,
)
from artana_evidence_api.runtime import create_artana_postgres_store

from .artifacts import (
    render_protocol_markdown,
    write_comparison_artifacts,
    write_json_model,
    write_text_artifact,
)
from .bundle import (
    discard_staging,
    prepare_staging_directory,
    promote_bundle,
    write_bundle_manifest,
    write_failure_receipt,
)
from .comparison import build_semantic_model_comparison
from .contracts import (
    SemanticModelComparisonProtocol,
    SemanticModelComparisonReport,
    SemanticModelEvaluationRun,
    SemanticModelRole,
)
from .protocol import (
    build_semantic_model_evaluation_run,
    protocol_sha256,
    sha256_path,
)
from .source_provenance import (
    BUNDLED_REPOSITORY_ROOT,
    copy_repository_source_files,
    verify_repository_source_provenance,
)
from .telemetry import SemanticTelemetryStore, collect_semantic_run_telemetry
from .verifier import verify_semantic_comparison_bundle

RunnerFactory = Callable[[str], EvidenceSelectionSemanticModelRunner]
StoreFactory = Callable[[], SemanticTelemetryStore]
FinalizationGuard = Callable[[], None]


async def execute_semantic_model_comparison(
    *,
    protocol: SemanticModelComparisonProtocol,
    output_dir: Path,
    runner_factory: RunnerFactory | None = None,
    store_factory: StoreFactory | None = None,
    finalization_guard: FinalizationGuard | None = None,
    repository_root: Path | None = None,
) -> SemanticModelComparisonReport:
    """Execute every predeclared run and atomically publish verified evidence."""

    staging_dir = prepare_staging_directory(output_dir)
    resolved_repository_root = (repository_root or Path.cwd()).resolve()
    try:
        fixture, baseline_report = _load_and_freeze_sources(
            protocol=protocol,
            staging_dir=staging_dir,
            repository_root=resolved_repository_root,
        )
        write_json_model(
            path=staging_dir / "semantic_model_comparison_protocol.json",
            model=protocol,
        )
        write_text_artifact(
            path=staging_dir / "semantic_model_comparison_protocol.md",
            content=render_protocol_markdown(protocol),
        )
        current_runs, candidate_runs = await _execute_interleaved_runs(
            protocol=protocol,
            fixture=fixture,
            baseline_report=baseline_report,
            output_dir=staging_dir,
            runner_factory=runner_factory or _default_runner_factory,
            store_factory=store_factory or _default_store_factory,
            repository_root=resolved_repository_root,
        )
        _verify_protocol_source_files(
            protocol,
            repository_root=resolved_repository_root,
        )
        if finalization_guard is not None:
            finalization_guard()
        generated_at = datetime.now(UTC)
        report = build_semantic_model_comparison(
            protocol=protocol,
            fixture=fixture,
            current_runs=current_runs,
            candidate_runs=candidate_runs,
            generated_at=generated_at,
            artifact_root=staging_dir,
            fixture_source_path=Path(protocol.fixture_path),
        )
        write_comparison_artifacts(output_dir=staging_dir, report=report)
        write_bundle_manifest(
            staging_dir=staging_dir,
            protocol_sha256=protocol_sha256(protocol),
            generated_at=generated_at,
        )
        verify_semantic_comparison_bundle(staging_dir)
        promote_bundle(staging_dir=staging_dir, output_dir=output_dir)
    except BaseException as exc:
        discard_staging(staging_dir)
        write_failure_receipt(output_dir=output_dir, error=exc)
        raise
    else:
        return report


async def _execute_interleaved_runs(
    *,
    protocol: SemanticModelComparisonProtocol,
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    baseline_report: EvidenceSelectionSemanticDiagnosticReport,
    output_dir: Path,
    runner_factory: RunnerFactory,
    store_factory: StoreFactory,
    repository_root: Path,
) -> tuple[
    tuple[SemanticModelEvaluationRun, ...],
    tuple[SemanticModelEvaluationRun, ...],
]:
    runs: dict[SemanticModelRole, list[SemanticModelEvaluationRun]] = {
        "current": [],
        "candidate": [],
    }
    schedule: tuple[tuple[SemanticModelRole, str], ...] = (
        ("current", protocol.current_model_id),
        ("candidate", protocol.candidate_model_id),
    )
    for run_index in range(1, protocol.runs_per_model + 1):
        for role, model_id in schedule:
            runs[role].append(
                await _execute_model_run(
                    role=role,
                    model_id=model_id,
                    run_index=run_index,
                    protocol=protocol,
                    fixture=fixture,
                    baseline_report=baseline_report,
                    output_dir=output_dir,
                    runner_factory=runner_factory,
                    store_factory=store_factory,
                    repository_root=repository_root,
                ),
            )
    return tuple(runs["current"]), tuple(runs["candidate"])


async def _execute_model_run(
    *,
    role: SemanticModelRole,
    model_id: str,
    run_index: int,
    protocol: SemanticModelComparisonProtocol,
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    baseline_report: EvidenceSelectionSemanticDiagnosticReport,
    output_dir: Path,
    runner_factory: RunnerFactory,
    store_factory: StoreFactory,
    repository_root: Path,
) -> SemanticModelEvaluationRun:
    _verify_protocol_source_files(protocol, repository_root=repository_root)
    runner = runner_factory(model_id)
    if runner.model_id() != model_id:
        raise ValueError(f"{role} runner did not resolve the frozen model ID")
    started_at = time.perf_counter()
    evaluation = await evaluate_semantic_selection_agent(
        fixture_path=Path(protocol.fixture_path),
        fixture=fixture,
        runner=runner,
        evaluated_commit=protocol.evaluated_commit,
        generated_at=datetime.now(UTC),
        baseline_report_path=Path(protocol.baseline_report_path),
        baseline_precision=baseline_report.score.micro.precision,
        baseline_end_to_end_recall=baseline_report.score.micro.end_to_end_recall,
        minimum_precision=protocol.thresholds.minimum_worst_precision,
        minimum_end_to_end_recall=protocol.thresholds.minimum_worst_recall,
    )
    wall_elapsed = time.perf_counter() - started_at
    evaluation_path = output_dir / f"{role}-run-{run_index}.json"
    write_json_model(path=evaluation_path, model=evaluation)
    write_text_artifact(
        path=output_dir / f"{role}-run-{run_index}.md",
        content=render_semantic_agent_evaluation_markdown(evaluation),
    )
    execution_ids = runner.execution_ids()
    if not execution_ids:
        raise ValueError("comparison runner did not expose its execution trace")
    store = store_factory()
    try:
        telemetry = await collect_semantic_run_telemetry(
            store=store,
            execution_ids=execution_ids,
            expected_model_id=model_id,
            wall_elapsed_seconds=wall_elapsed,
        )
    finally:
        await store.close()
    return build_semantic_model_evaluation_run(
        role=role,
        run_index=run_index,
        evaluation_path=evaluation_path,
        evaluation_reference=evaluation_path.name,
        evaluation=evaluation,
        telemetry=telemetry,
        agent_run_ids=execution_ids,
    )


def _load_and_freeze_sources(
    *,
    protocol: SemanticModelComparisonProtocol,
    staging_dir: Path,
    repository_root: Path,
) -> tuple[
    EvidenceSelectionSemanticDiagnosticFixture,
    EvidenceSelectionSemanticDiagnosticReport,
]:
    _verify_protocol_source_files(protocol, repository_root=repository_root)
    fixture_path = Path(protocol.fixture_path)
    baseline_path = Path(protocol.baseline_report_path)
    source_dir = staging_dir / "sources"
    source_dir.mkdir()
    bundled_fixture_path = source_dir / "fixture.json"
    bundled_baseline_path = source_dir / "baseline_report.json"
    shutil.copyfile(fixture_path, bundled_fixture_path)
    shutil.copyfile(baseline_path, bundled_baseline_path)
    fixture = load_semantic_diagnostic_fixture(bundled_fixture_path)
    baseline = EvidenceSelectionSemanticDiagnosticReport.model_validate_json(
        bundled_baseline_path.read_text(encoding="utf-8"),
    )
    if baseline.fixture_sha256 != protocol.fixture_sha256:
        raise ValueError("comparison baseline does not describe the frozen fixture")
    copy_repository_source_files(
        source_files=protocol.repository_source_files,
        repository_root=repository_root,
        destination_root=staging_dir / BUNDLED_REPOSITORY_ROOT,
    )
    verify_repository_source_provenance(
        expected_files=protocol.repository_source_files,
        fixture=fixture,
        baseline=baseline,
        repository_root=staging_dir / BUNDLED_REPOSITORY_ROOT,
    )
    return fixture, baseline


def _verify_protocol_source_files(
    protocol: SemanticModelComparisonProtocol,
    *,
    repository_root: Path,
) -> None:
    fixture_path = Path(protocol.fixture_path)
    baseline_path = Path(protocol.baseline_report_path)
    if (
        not fixture_path.is_file()
        or sha256_path(fixture_path) != protocol.fixture_sha256
    ):
        raise ValueError("comparison fixture bytes do not match the frozen protocol")
    if (
        not baseline_path.is_file()
        or sha256_path(baseline_path) != protocol.baseline_report_sha256
    ):
        raise ValueError("comparison baseline bytes do not match the frozen protocol")
    fixture = load_semantic_diagnostic_fixture(fixture_path)
    baseline = EvidenceSelectionSemanticDiagnosticReport.model_validate_json(
        baseline_path.read_text(encoding="utf-8"),
    )
    verify_repository_source_provenance(
        expected_files=protocol.repository_source_files,
        fixture=fixture,
        baseline=baseline,
        repository_root=repository_root,
    )


def _default_runner_factory(model_id: str) -> EvidenceSelectionSemanticModelRunner:
    return ArtanaEvidenceSelectionSemanticModelRunner(model_id=model_id)


def _default_store_factory() -> SemanticTelemetryStore:
    return cast("SemanticTelemetryStore", create_artana_postgres_store())


__all__ = ["execute_semantic_model_comparison"]
