"""Frozen protocol and run-envelope builders for semantic model comparison."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    EvidenceSelectionSemanticAgentEvaluation,
)

from .contracts import (
    SemanticModelComparisonProtocol,
    SemanticModelComparisonThresholds,
    SemanticModelEvaluationRun,
    SemanticModelRole,
    SemanticRecordDecision,
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
    baseline_report_path: Path,
    baseline_report_sha256: str,
    current_model_id: str,
    candidate_model_id: str,
    runs_per_model: int = 3,
    thresholds: SemanticModelComparisonThresholds | None = None,
) -> SemanticModelComparisonProtocol:
    """Freeze a source-locked comparison before any model call is made."""

    resolved_thresholds = thresholds or SemanticModelComparisonThresholds()
    source_lock_digest = source_lock_sha256(
        fixture_sha256=fixture_sha256,
        baseline_report_sha256=baseline_report_sha256,
    )
    return SemanticModelComparisonProtocol(
        schema_version="evidence_selection_semantic_model_protocol.v2",
        generated_at=generated_at,
        evaluated_commit=evaluated_commit,
        trusted_mainline_ref=trusted_mainline_ref,
        trusted_mainline_commit=trusted_mainline_commit,
        required_mainline_commit=required_mainline_commit,
        fixture_path=str(fixture_path),
        fixture_sha256=fixture_sha256,
        fixture_provenance="ai_adjudicated_diagnostic",
        baseline_report_path=str(baseline_report_path),
        baseline_report_sha256=baseline_report_sha256,
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
    evaluation: EvidenceSelectionSemanticAgentEvaluation,
    telemetry: SemanticRunTelemetry,
    agent_run_ids: tuple[str, ...] | None = None,
) -> SemanticModelEvaluationRun:
    """Bind one evaluation artifact to its categorical decisions and telemetry."""

    successful_agent_run_ids = tuple(
        sorted(
            {
                result.agent_run_id
                for result in evaluation.record_results
                if result.agent_run_id != "invalid_agent"
            },
        ),
    )
    bound_agent_run_ids = agent_run_ids or successful_agent_run_ids
    return SemanticModelEvaluationRun(
        model_role=role,
        run_index=run_index,
        evaluation_path=evaluation_reference or str(evaluation_path),
        evaluation_sha256=sha256_path(evaluation_path),
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
        agent_run_ids=bound_agent_run_ids,
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
    baseline_report_sha256: str,
) -> str:
    payload = json.dumps(
        {
            "baseline_report_sha256": baseline_report_sha256,
            "fixture_sha256": fixture_sha256,
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
