"""Honest JSON and Markdown reporting for semantic benchmark v2."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.predictions import (
    EvidenceSelectionSemanticPredictionArtifact,
    verify_prediction_provenance,
)

from .contracts import (
    EvidenceSelectionBenchmarkEvaluation,
    EvidenceSelectionBenchmarkV2Report,
)
from .loader import load_benchmark_v2
from .scoring import score_benchmark_v2


def build_benchmark_v2_report(
    *,
    fixture_path: Path,
    prediction_path: Path,
    evaluation: EvidenceSelectionBenchmarkEvaluation,
    repository_root: Path,
    generated_at: datetime,
) -> EvidenceSelectionBenchmarkV2Report:
    """Load categorical predictions and recompute the exact reported score."""

    fixture_sha256 = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    if fixture_sha256 != evaluation.fixture_sha256:
        raise ValueError("report fixture bytes do not match evaluated fixture")
    prediction_bytes = prediction_path.read_bytes()
    prediction_artifact = (
        EvidenceSelectionSemanticPredictionArtifact.model_validate_json(
            prediction_bytes,
        )
    )
    loaded = load_benchmark_v2(
        fixture_path=fixture_path,
        repository_root=repository_root,
    )
    if loaded.fixture_sha256 != evaluation.fixture_sha256:
        raise ValueError("report evaluation does not match the loaded benchmark")
    verify_prediction_provenance(
        fixture=loaded.historical_v1,
        artifact=prediction_artifact,
        repository_root=repository_root,
    )
    score = score_benchmark_v2(
        evaluation=evaluation,
        predictions=prediction_artifact.predictions,
    )
    return EvidenceSelectionBenchmarkV2Report(
        schema_version="evidence_selection_semantic_benchmark_report.v3",
        generated_at=generated_at,
        fixture_path=str(fixture_path),
        fixture_sha256=fixture_sha256,
        prediction_path=str(prediction_path),
        prediction_sha256=hashlib.sha256(prediction_bytes).hexdigest(),
        fixture_provenance="ai_adjudicated_diagnostic",
        score_derivation="deterministic_from_bound_prediction_artifact",
        expert_study_status=evaluation.expert_study_status,
        production_readiness_claim=False,
        score=score,
    )


def render_benchmark_v2_markdown(report: EvidenceSelectionBenchmarkV2Report) -> str:
    """Render pending and ambiguous evidence without implying expert approval."""

    score = report.score
    lines = [
        "# Evidence Selection Semantic Benchmark V2 Integrity Report",
        "",
        "- Fixture provenance: **AI-adjudicated diagnostic**",
        "- Score derivation: **DETERMINISTIC FROM BOUND PREDICTION ARTIFACT**",
        f"- Existing expert-study gate status: **{report.expert_study_status.upper()}**",
        "- Human/expert approval claim: **NO**",
        "- Production readiness claim: **NO**",
        f"- Total visible records: `{score.total_record_count}`",
        f"- Score-eligible records: `{score.score_eligible_record_count}`",
        f"- Pending-expert records: `{score.pending_expert_record_count}`",
        f"- Ambiguous pending-expert records: `{score.ambiguous_record_count}`",
        f"- Canary gate: **{score.canary_gate_status.upper()}**",
        "",
        "AI diagnostic categories, rationales, and evidence spans remain visible but are "
        "excluded from adoption metrics. The existing real-shadow-review bundle and "
        "provenance gate are required but not sufficient: score eligibility also "
        "requires externally authenticated reviewer identity and independent per-record "
        "packet-sufficiency attestation bound to the verified source exports.",
        "",
        "## Adoption Metrics",
        "",
    ]
    metrics = score.adoption_metrics
    if metrics is None:
        lines.extend(
            [
                "**UNAVAILABLE**: no primary records have independently attested "
                "reviewer provenance and sufficient bounded source packets.",
            ],
        )
    else:
        lines.extend(
            [
                f"- Eligible primary records: `{metrics.record_count}`",
                f"- Precision: `{metrics.precision:.4f}`",
                f"- End-to-end recall: `{metrics.end_to_end_recall:.4f}`",
                f"- Decision coverage: `{metrics.decision_coverage:.4f}`",
            ],
        )
    lines.extend(
        [
            "",
            "## Record Inventory",
            "",
            "| Record | Role | AI diagnostic | Eligibility | Prediction |",
            "| --- | --- | --- | --- | --- |",
            *(
                f"| `{outcome.record_id}` | {outcome.evaluation_role} | "
                f"{outcome.diagnostic_decision} | {outcome.eligibility_status} | "
                f"{outcome.prediction_decision} |"
                for outcome in score.record_outcomes
            ),
            "",
            "The immutable v1 fixture remains historical diagnostic evidence. Benchmark "
            "v2 does not rewrite it, promote AI adjudication to expert gold, or treat "
            "unavailable metrics as zero or passing.",
            "",
        ],
    )
    return "\n".join(lines)


__all__ = ["build_benchmark_v2_report", "render_benchmark_v2_markdown"]
