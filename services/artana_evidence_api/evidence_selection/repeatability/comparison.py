"""Composition root for semantic selector repeatability evidence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    EvidenceSelectionSemanticDiagnosticFixture,
)

from .adoption import semantic_model_adoption_decision
from .contracts import (
    SemanticModelComparisonProtocol,
    SemanticModelComparisonReport,
    SemanticModelEvaluationRun,
)
from .integrity import validate_semantic_run_matrix
from .protocol import protocol_sha256
from .summary import cross_model_disagreement_count, summarize_semantic_model_runs


def build_semantic_model_comparison(
    *,
    protocol: SemanticModelComparisonProtocol,
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    current_runs: tuple[SemanticModelEvaluationRun, ...],
    candidate_runs: tuple[SemanticModelEvaluationRun, ...],
    generated_at: datetime,
    artifact_root: Path | None = None,
    fixture_source_path: Path | None = None,
) -> SemanticModelComparisonReport:
    """Validate one source-locked matrix and derive its categorical decision."""

    validate_semantic_run_matrix(
        protocol=protocol,
        fixture=fixture,
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        artifact_root=artifact_root,
        fixture_source_path=fixture_source_path,
    )
    current_summary = summarize_semantic_model_runs(
        runs=current_runs,
        protocol=protocol,
    )
    candidate_summary = summarize_semantic_model_runs(
        runs=candidate_runs,
        protocol=protocol,
    )
    decision = semantic_model_adoption_decision(
        protocol=protocol,
        current=current_summary,
        candidate=candidate_summary,
    )
    selected_summary = (
        candidate_summary if decision.outcome == "adopt_candidate" else current_summary
    )
    selected_model_repeatability_passed = (
        decision.outcome != "inconclusive"
        and selected_summary.quality_gate_passed
        and selected_summary.telemetry_complete
    )
    return SemanticModelComparisonReport(
        schema_version="evidence_selection_semantic_model_comparison.v3",
        generated_at=generated_at,
        protocol=protocol,
        protocol_sha256=protocol_sha256(protocol),
        current_runs=current_runs,
        candidate_runs=candidate_runs,
        current_summary=current_summary,
        candidate_summary=candidate_summary,
        cross_model_disagreement_count=cross_model_disagreement_count(
            current=current_summary,
            candidate=candidate_summary,
        ),
        decision=decision,
        selected_model_repeatability_passed=selected_model_repeatability_passed,
        calibration_status="unavailable",
        calibration_ece=None,
        evidence_provenance=protocol.fixture_provenance,
        production_readiness_claim=False,
    )


__all__ = ["build_semantic_model_comparison"]
