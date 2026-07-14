"""Frozen protocol and run-envelope builders for semantic model comparison."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    EvidenceSelectionSemanticAgentEvaluation,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.contracts import (
    EvidenceSelectionBenchmarkEvaluation,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.scoring import (
    score_benchmark_v2,
)
from artana_evidence_api.evidence_selection.diagnostics.predictions import (
    EvidenceSelectionSemanticPrediction,
)

from .contracts import (
    SemanticModelComparisonProtocol,
    SemanticModelComparisonThresholds,
    SemanticModelEvaluationRun,
    SemanticModelRole,
    SemanticRecordDecision,
    SemanticRepositorySourceFile,
    SemanticRunTelemetry,
)


def build_semantic_model_comparison_protocol(
    *,
    generated_at: datetime,
    evaluated_commit: str,
    trusted_mainline_ref: str,
    trusted_mainline_commit: str,
    required_mainline_commit: str,
    fixture_path: Path,
    fixture_sha256: str,
    benchmark_fixture_path: Path,
    benchmark_fixture_sha256: str,
    benchmark_evaluation: EvidenceSelectionBenchmarkEvaluation,
    baseline_report_path: Path,
    baseline_report_sha256: str,
    repository_source_files: tuple[SemanticRepositorySourceFile, ...],
    current_model_id: str,
    candidate_model_id: str,
    runs_per_model: int = 3,
    thresholds: SemanticModelComparisonThresholds | None = None,
) -> SemanticModelComparisonProtocol:
    """Freeze a source-locked comparison before any model call is made."""

    resolved_thresholds = thresholds or SemanticModelComparisonThresholds()
    source_lock_digest = source_lock_sha256(
        fixture_sha256=fixture_sha256,
        benchmark_fixture_sha256=benchmark_fixture_sha256,
        baseline_report_sha256=baseline_report_sha256,
        repository_source_files=repository_source_files,
    )
    return SemanticModelComparisonProtocol(
        schema_version="evidence_selection_semantic_model_protocol.v4",
        generated_at=generated_at,
        evaluated_commit=evaluated_commit,
        trusted_mainline_ref=trusted_mainline_ref,
        trusted_mainline_commit=trusted_mainline_commit,
        required_mainline_commit=required_mainline_commit,
        fixture_path=str(fixture_path),
        fixture_sha256=fixture_sha256,
        fixture_provenance="ai_adjudicated_diagnostic",
        benchmark_fixture_path=str(benchmark_fixture_path),
        benchmark_fixture_sha256=benchmark_fixture_sha256,
        benchmark_evaluation=benchmark_evaluation,
        baseline_report_path=str(baseline_report_path),
        baseline_report_sha256=baseline_report_sha256,
        repository_source_files=repository_source_files,
        current_model_id=current_model_id,
        candidate_model_id=candidate_model_id,
        runs_per_model=runs_per_model,
        thresholds=resolved_thresholds,
        source_lock_sha256=source_lock_digest,
        production_readiness_claim=False,
    )


def build_semantic_model_evaluation_run(
    *,
    role: SemanticModelRole,
    run_index: int,
    evaluation_path: Path,
    evaluation_reference: str | None = None,
    attempt_manifest_path: Path,
    attempt_manifest_reference: str | None = None,
    evaluation: EvidenceSelectionSemanticAgentEvaluation,
    benchmark_evaluation: EvidenceSelectionBenchmarkEvaluation,
    telemetry: SemanticRunTelemetry,
) -> SemanticModelEvaluationRun:
    """Bind one evaluation artifact to its categorical decisions and telemetry."""

    adoption_score = score_benchmark_v2(
        evaluation=benchmark_evaluation,
        predictions=tuple(
            EvidenceSelectionSemanticPrediction(
                record_id=result.record_id,
                decision=result.prediction_decision,
                reason=result.failure_type or "categorical semantic selector output",
            )
            for result in evaluation.record_results
        ),
    )
    return SemanticModelEvaluationRun(
        model_role=role,
        run_index=run_index,
        evaluation_path=evaluation_reference or str(evaluation_path),
        evaluation_sha256=sha256_path(evaluation_path),
        attempt_manifest_path=(
            attempt_manifest_reference or str(attempt_manifest_path)
        ),
        attempt_manifest_sha256=sha256_path(attempt_manifest_path),
        generated_at=evaluation.generated_at,
        evaluated_commit=evaluation.evaluated_commit,
        model_id=evaluation.model_id,
        fixture_sha256=evaluation.fixture_sha256,
        baseline_report_sha256=evaluation.baseline_report_sha256,
        fixture_provenance=evaluation.fixture_provenance,
        deterministic_fallback_count=evaluation.deterministic_fallback_count,
        score=evaluation.score,
        canary_passed=evaluation.canary_passed,
        quality_gate_passed=evaluation.quality_gate_passed,
        adoption_score=adoption_score,
        record_decisions=tuple(
            SemanticRecordDecision(
                case_id=result.case_id,
                record_id=result.record_id,
                decision=result.prediction_decision,
            )
            for result in evaluation.record_results
        ),
        telemetry=telemetry,
        calibration_status="unavailable",
        calibration_ece=None,
        production_readiness_claim=False,
    )


def sha256_path(path: Path) -> str:
    """Return the SHA-256 digest of an artifact's exact bytes."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def protocol_sha256(protocol: SemanticModelComparisonProtocol) -> str:
    """Return the canonical digest of a frozen comparison protocol."""

    payload = json.dumps(
        protocol.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_lock_sha256(
    *,
    fixture_sha256: str,
    benchmark_fixture_sha256: str,
    baseline_report_sha256: str,
    repository_source_files: tuple[SemanticRepositorySourceFile, ...],
) -> str:
    payload = json.dumps(
        {
            "baseline_report_sha256": baseline_report_sha256,
            "fixture_sha256": fixture_sha256,
            "benchmark_fixture_sha256": benchmark_fixture_sha256,
            "repository_source_files": [
                source.model_dump(mode="json") for source in repository_source_files
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "build_semantic_model_comparison_protocol",
    "build_semantic_model_evaluation_run",
    "protocol_sha256",
    "sha256_path",
    "source_lock_sha256",
]
