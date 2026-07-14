"""Atomic artifacts and human-readable reports for semantic model comparison."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from .contracts import (
    SemanticModelComparisonProtocol,
    SemanticModelComparisonReport,
)


def write_json_model(*, path: Path, model: BaseModel) -> None:
    """Atomically write one strict model as stable JSON."""

    content = json.dumps(model.model_dump(mode="json"), indent=2) + "\n"
    _write_atomic(path=path, content=content)


def write_text_artifact(*, path: Path, content: str) -> None:
    """Atomically write one human-readable evidence artifact."""

    _write_atomic(path=path, content=content)


def write_comparison_artifacts(
    *,
    output_dir: Path,
    report: SemanticModelComparisonReport,
) -> tuple[Path, Path]:
    """Write the final JSON and Markdown evidence artifacts atomically."""

    json_path = output_dir / "semantic_model_comparison_report.json"
    markdown_path = output_dir / "semantic_model_comparison_report.md"
    write_json_model(path=json_path, model=report)
    _write_atomic(path=markdown_path, content=render_comparison_markdown(report))
    return json_path, markdown_path


def render_protocol_markdown(protocol: SemanticModelComparisonProtocol) -> str:
    """Render the protocol frozen before live model execution."""

    thresholds = protocol.thresholds
    lines = [
        "# Semantic Model Comparison Protocol",
        "",
        f"- Evaluated commit: `{protocol.evaluated_commit}`",
        f"- Trusted mainline ref: `{protocol.trusted_mainline_ref}`",
        f"- Trusted mainline commit: `{protocol.trusted_mainline_commit}`",
        f"- Required integrated mainline commit: `{protocol.required_mainline_commit}`",
        f"- Current model: `{protocol.current_model_id}`",
        f"- Candidate model: `{protocol.candidate_model_id}`",
        f"- Runs per model: `{protocol.runs_per_model}`",
        f"- Fixture SHA-256: `{protocol.fixture_sha256}`",
        f"- Baseline SHA-256: `{protocol.baseline_report_sha256}`",
        f"- Repository source files: `{len(protocol.repository_source_files)}`",
        f"- Source lock SHA-256: `{protocol.source_lock_sha256}`",
        "- Evidence provenance: **AI-adjudicated diagnostic**",
        "- Production readiness claim: **NO**",
        "",
        "## Frozen Repository Sources",
        "",
        *(
            f"- `{source.role}`: `{source.relative_path}` (`{source.sha256}`)"
            for source in protocol.repository_source_files
        ),
        "",
        "## Deterministic Adoption Policy",
        "",
        f"- Policy: `{thresholds.policy_id}@{thresholds.policy_version}`",
        f"- Minimum worst-run precision: `{thresholds.minimum_worst_precision:.4f}`",
        f"- Minimum worst-run recall: `{thresholds.minimum_worst_recall:.4f}`",
        f"- Minimum per-case precision: `{thresholds.minimum_case_precision:.4f}`",
        f"- Minimum per-case recall: `{thresholds.minimum_case_recall:.4f}`",
        f"- Minimum worst-run coverage: `{thresholds.minimum_worst_decision_coverage:.4f}`",
        f"- Minimum per-case coverage: `{thresholds.minimum_case_decision_coverage:.4f}`",
        "- Variance-only model adoption: **FORBIDDEN**",
        "- Record-level instability allowed: `0`",
        "- Agent-authored confidence or numeric model preference: **FORBIDDEN**",
        f"- Absolute maximum candidate resource ratio: `{thresholds.maximum_candidate_resource_ratio:.2f}`",
        "",
    ]
    return "\n".join(lines)


def render_comparison_markdown(report: SemanticModelComparisonReport) -> str:
    """Render model quality, variance, runtime, and the derived decision."""

    current = report.current_summary
    candidate = report.candidate_summary
    decision = report.decision
    lines = [
        "# Semantic Selector Repeatability And Model Comparison",
        "",
        f"- Evaluated commit: `{report.protocol.evaluated_commit}`",
        f"- Protocol SHA-256: `{report.protocol_sha256}`",
        f"- Source lock SHA-256: `{report.protocol.source_lock_sha256}`",
        f"- Decision: **{decision.outcome.upper()}**",
        f"- Selected model: `{decision.selected_model_id or 'none'}`",
        "- Selected-model repeatability proof: "
        f"**{'PASS' if report.selected_model_repeatability_passed else 'FAIL'}**",
        "- Calibration: **UNAVAILABLE** (no independent held-out expert corpus)",
        "- Evidence provenance: **AI-adjudicated diagnostic**",
        "- Production readiness claim: **NO**",
        "",
        "## Repeated Quality",
        "",
        "| Metric | Current | Candidate |",
        "| --- | ---: | ---: |",
        f"| Runs | {current.run_count} | {candidate.run_count} |",
        f"| Quality gate | {'PASS' if current.quality_gate_passed else 'FAIL'} | {'PASS' if candidate.quality_gate_passed else 'FAIL'} |",
        f"| Worst precision | {current.worst_precision:.4f} | {candidate.worst_precision:.4f} |",
        f"| Worst recall | {current.worst_recall:.4f} | {candidate.worst_recall:.4f} |",
        f"| Minimum case precision | {current.minimum_case_precision:.4f} | {candidate.minimum_case_precision:.4f} |",
        f"| Minimum case recall | {current.minimum_case_recall:.4f} | {candidate.minimum_case_recall:.4f} |",
        f"| Worst decision coverage | {current.worst_decision_coverage:.4f} | {candidate.worst_decision_coverage:.4f} |",
        f"| Minimum case coverage | {current.minimum_case_decision_coverage:.4f} | {candidate.minimum_case_decision_coverage:.4f} |",
        f"| Mean abstention rate | {current.mean_abstention_rate:.4f} | {candidate.mean_abstention_rate:.4f} |",
        f"| Mean precision | {current.mean_precision:.4f} | {candidate.mean_precision:.4f} |",
        f"| Mean recall | {current.mean_recall:.4f} | {candidate.mean_recall:.4f} |",
        f"| Precision variance | {current.precision_variance:.6f} | {candidate.precision_variance:.6f} |",
        f"| Recall variance | {current.recall_variance:.6f} | {candidate.recall_variance:.6f} |",
        f"| Unstable records | {current.unstable_record_count} | {candidate.unstable_record_count} |",
        f"| Invalid-agent decisions | {current.invalid_agent_count} | {candidate.invalid_agent_count} |",
        "| Deterministic fallback | 0 | 0 |",
        "",
        "## Runtime Observations",
        "",
        "| Metric | Current | Candidate |",
        "| --- | ---: | ---: |",
        f"| Telemetry complete | {'yes' if current.telemetry_complete else 'no'} | {'yes' if candidate.telemetry_complete else 'no'} |",
        f"| Total tokens | {_optional_int(current.total_tokens)} | {_optional_int(candidate.total_tokens)} |",
        f"| Total cost USD | {_optional_float(current.total_cost_usd, 8)} | {_optional_float(candidate.total_cost_usd, 8)} |",
        f"| Model latency seconds | {_optional_float(current.total_model_latency_seconds, 6)} | {_optional_float(candidate.total_model_latency_seconds, 6)} |",
        f"| Wall latency seconds | {current.total_wall_latency_seconds:.6f} | {candidate.total_wall_latency_seconds:.6f} |",
        "",
        "## Decision Evidence",
        "",
    ]
    lines.extend(f"- Reason code: `{reason}`" for reason in decision.reason_codes)
    if decision.blocking_reasons:
        lines.extend(f"- {reason}" for reason in decision.blocking_reasons)
    lines.extend(
        [
            f"- Worst precision delta: `{decision.metric_deltas.worst_precision:.4f}`",
            f"- Worst recall delta: `{decision.metric_deltas.worst_recall:.4f}`",
            f"- Combined variance delta: `{decision.metric_deltas.combined_variance:.6f}`",
            f"- Cost ratio: `{_optional_float(decision.metric_deltas.cost_ratio, 4)}`",
            f"- Model latency ratio: `{_optional_float(decision.metric_deltas.model_latency_ratio, 4)}`",
            f"- Cross-model categorical disagreements: `{report.cross_model_disagreement_count}`",
            "",
            "This report compares categorical decisions over identical frozen source "
            "records. All quality and adoption numbers are deterministic computed "
            "metrics or runtime observations; neither model supplies a score used for "
            "adoption. This diagnostic cannot substitute for the independent expert "
            "pilot or trusted-relation proof.",
            "",
        ],
    )
    return "\n".join(lines)


def _write_atomic(*, path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _optional_int(value: int | None) -> str:
    return "unavailable" if value is None else str(value)


def _optional_float(value: float | None, precision: int) -> str:
    return "unavailable" if value is None else f"{value:.{precision}f}"


__all__ = [
    "render_comparison_markdown",
    "render_protocol_markdown",
    "write_comparison_artifacts",
    "write_json_model",
    "write_text_artifact",
]
