"""Report contracts and rendering for semantic-selection diagnostics."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .fixture import EvidenceSelectionSemanticDiagnosticFixture
from .predictions import (
    EvidenceSelectionSemanticPredictionArtifact,
    EvidenceSelectionSemanticSourceArtifact,
)
from .scoring import EvidenceSelectionSemanticDiagnosticScore


class EvidenceSelectionSemanticDiagnosticReport(BaseModel):
    """Immutable diagnostic report that cannot claim production readiness."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_diagnostic_report.v1"]
    generated_at: datetime
    fixture_path: str
    fixture_sha256: str
    prediction_artifact_path: str
    prediction_artifact_sha256: str
    prediction_provenance: Literal["manually_transcribed_live_shadow_results"]
    fixture_provenance: Literal["ai_adjudicated_diagnostic"]
    production_readiness_claim: Literal[False]
    benchmark_name: str
    baseline_commit: str
    baseline_model: str
    adjudication_scope: str
    source_artifacts: tuple[EvidenceSelectionSemanticSourceArtifact, ...]
    score: EvidenceSelectionSemanticDiagnosticScore


def build_semantic_diagnostic_report(
    *,
    fixture_path: Path,
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    prediction_path: Path,
    prediction_artifact: EvidenceSelectionSemanticPredictionArtifact,
    score: EvidenceSelectionSemanticDiagnosticScore,
    generated_at: datetime,
) -> EvidenceSelectionSemanticDiagnosticReport:
    """Build one provenance-explicit baseline report."""

    return EvidenceSelectionSemanticDiagnosticReport(
        schema_version="evidence_selection_semantic_diagnostic_report.v1",
        generated_at=generated_at,
        fixture_path=str(fixture_path),
        fixture_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        prediction_artifact_path=str(prediction_path),
        prediction_artifact_sha256=hashlib.sha256(
            prediction_path.read_bytes()
        ).hexdigest(),
        prediction_provenance=prediction_artifact.provenance,
        fixture_provenance=fixture.provenance,
        production_readiness_claim=False,
        benchmark_name=fixture.benchmark_name,
        baseline_commit=fixture.baseline_commit,
        baseline_model=fixture.baseline_model,
        adjudication_scope=fixture.adjudication_scope,
        source_artifacts=tuple(prediction_artifact.source_artifacts),
        score=score,
    )


def render_semantic_diagnostic_markdown(
    report: EvidenceSelectionSemanticDiagnosticReport,
) -> str:
    """Render a human-readable baseline report from the typed JSON report."""

    lines = [
        "# Evidence Selection Semantic Diagnostic Baseline",
        "",
        f"- Benchmark: `{report.benchmark_name}`",
        "- Fixture provenance: **AI-adjudicated diagnostic**",
        "- Production readiness claim: **NO**",
        f"- Baseline commit: `{report.baseline_commit}`",
        f"- Baseline model: `{report.baseline_model}`",
        f"- Fixture SHA-256: `{report.fixture_sha256}`",
        f"- Prediction artifact SHA-256: `{report.prediction_artifact_sha256}`",
        "",
        "Expected labels are AI-adjudicated diagnostics, and predictions are manually "
        "transcribed from live shadow results. This is not independent human-expert evidence.",
        "",
        "## Case Results",
        "",
        "| Case | Role | Records | TP | FP | FN | TN | Precision | Expected + | End-to-end recall | Abstain | Invalid |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        (
            "| "
            f"{result.display_name} | {result.evaluation_role} | {result.record_count} | "
            f"{result.true_positive_count} | {result.false_positive_count} | "
            f"{result.false_negative_count} | {result.true_negative_count} | "
            f"{result.precision:.4f} | {result.expected_positive_count} | "
            f"{result.end_to_end_recall:.4f} | "
            f"{result.abstention_count} | {result.invalid_agent_count} |"
        )
        for result in report.score.case_results
    )
    micro = report.score.micro
    macro = report.score.macro
    lines.extend(
        [
            "",
            "## Source Artifacts",
            "",
            "| Case | Role | Source run | Sanitized snapshot | Snapshot SHA-256 | Upstream SHA-256 |",
            "| --- | --- | --- | --- | --- | --- |",
            *(
                f"| {artifact.case_id} | {artifact.evaluation_role} | "
                f"`{artifact.source_run_id}` | `{artifact.source_artifact_path}` | "
                f"`{artifact.source_artifact_sha256}` | "
                f"`{artifact.upstream_source_artifact_sha256}` |"
                for artifact in report.source_artifacts
            ),
            "",
            "## Aggregate Results",
            "",
            f"### Primary-only micro aggregate ({micro.record_count} records)",
            "",
            f"- Precision: `{micro.precision:.4f}`",
            f"- End-to-end recall: `{micro.end_to_end_recall:.4f}`",
            f"- Decision accuracy: `{micro.decision_accuracy:.4f}`",
            f"- Decision coverage: `{micro.decision_coverage:.4f}`",
            f"- Abstention rate: `{micro.abstention_rate:.4f}`",
            f"- Invalid-agent rate: `{micro.invalid_agent_rate:.4f}`",
            "",
            f"### Primary-only macro aggregate (unweighted mean across {report.score.scored_case_count} cases)",
            "",
            f"- Precision: `{macro.precision:.4f}`",
            f"- End-to-end recall: `{macro.end_to_end_recall:.4f}`",
            f"- Decision accuracy: `{macro.decision_accuracy:.4f}`",
            f"- Decision coverage: `{macro.decision_coverage:.4f}`",
            f"- Abstention rate: `{macro.abstention_rate:.4f}`",
            f"- Invalid-agent rate: `{macro.invalid_agent_rate:.4f}`",
            "",
            "Canary cases are shown above but excluded from both aggregates. Precision is "
            "reported as 0 when a case has no predicted selections.",
            "",
            "## Interpretation",
            "",
            "The baseline is intentionally RED. PR 1 freezes the failure and "
            "measurement contract; it does not change production selection behavior.",
            "",
        ],
    )
    return "\n".join(lines)


__all__ = [
    "EvidenceSelectionSemanticDiagnosticReport",
    "build_semantic_diagnostic_report",
    "render_semantic_diagnostic_markdown",
]
