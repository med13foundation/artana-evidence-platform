"""JSON and Markdown output for TG-03 benchmark reports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast


def write_reports(
    *,
    report: Mapping[str, object],
    json_path: Path,
    markdown_path: Path,
) -> None:
    """Write one report in machine-readable and reviewable formats."""

    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: Mapping[str, object]) -> str:
    """Render a concise deterministic audit report."""

    fixture = _object(report.get("fixture"))
    metrics = _object(report.get("metrics"))
    run_ids = report.get("run_ids") or [report.get("run_id", "")]
    model_ids = report.get("model_ids") or [report.get("model_id", "")]
    prompt_versions = report.get("prompt_versions") or [
        report.get("prompt_version", "")
    ]
    provider_receipts = _object(report.get("provider_receipts"))
    lines = [
        "# TG-03 ClaimFrame Feasibility Audit",
        "",
        f"- Report type: `{report.get('report_type', '')}`",
        f"- Run IDs: `{', '.join(_strings(run_ids))}`",
        f"- Model IDs: `{', '.join(_strings(model_ids))}`",
        f"- Prompt versions: `{', '.join(_strings(prompt_versions))}`",
        f"- Fixture SHA-256: `{fixture.get('sha256', '')}`",
        f"- Methodology complete: `{fixture.get('methodology_complete', False)}`",
        f"- Offline JSON authentication: `{report.get('offline_json_authentication', '')}`",
        f"- Provider receipt status: `{report.get('provider_receipt_status', '')}`",
        "- Provider receipts verified: "
        f"`{provider_receipts.get('verified_count', 0)}/"
        f"{provider_receipts.get('expected_count', 0)}`",
        f"- Repository commit: `{_object(report.get('repository_evidence')).get('commit', '')}`",
        f"- Clean tracked tree: `{_object(report.get('repository_evidence')).get('clean', False)}`",
        f"- Gate passed: **{str(report.get('gate_passed', False)).lower()}**",
        "",
        "## Decision",
        "",
        (
            "**TG-03 merge gate: PASS.**"
            if report.get("gate_passed") is True
            else "**TG-03 merge gate: FAIL. Trusted projection remains blocked.**"
        ),
        "",
        "## Deterministic Metrics",
        "",
    ]
    for key in (
        "expected_frame_count",
        "endpoint_source_match_count",
        "full_frame_correct_count",
        "quality_case_count",
        "quality_frame_count",
        "unresolved_case_count",
        "unresolved_frame_count",
        "unresolved_output_frame_count",
        "agent_invocation_completion_rate",
        "strict_usable_extraction_completion_rate",
        "explicit_polarity_concordance_rate",
        "epistemic_status_concordance_rate",
        "required_qualifier_completeness_rate",
        "qualifier_concordance_rate",
        "endpoint_source_match_precision",
        "endpoint_source_match_recall",
        "full_frame_precision",
        "full_frame_recall",
        "expected_inventory_claim_count",
        "inventory_claim_count",
        "inventory_boundary_match_count",
        "inventory_full_match_count",
        "inventory_boundary_precision",
        "inventory_boundary_recall",
        "inventory_full_precision",
        "inventory_full_recall",
        "unmatched_inventory_claim_count",
        "expected_source_measurement_count",
        "output_source_measurement_count",
        "matched_source_measurement_count",
        "source_measurement_precision",
        "source_measurement_recall",
        "unmatched_output_count",
        "unsupported_positive_output_count",
        "unsafe_assertive_upgrade_count",
        "positive_on_negative_or_null_count",
        "agent_authored_numeric_value_count",
        "model_invocation_failure_count",
        "source_measurement_without_span_count",
        "exact_semantic_frame_stability_rate",
        "canonical_semantic_frame_stability_rate",
    ):
        if key in metrics:
            lines.append(f"- {key}: `{metrics[key]}`")
    lines.extend(("", "## Gates", ""))
    gates = _object(report.get("gates"))
    for name, gate_value in gates.items():
        gate = _object(gate_value)
        lines.append(
            f"- {name}: **{str(gate.get('passed', False)).lower()}**"
            f" ({gate.get('rule', gate.get('status', ''))})",
        )
    lines.extend(("", "## Cases", ""))
    for raw_case in cast("list[object]", report.get("cases", [])):
        case = _object(raw_case)
        lines.extend(
            (
                f"### {case.get('case_id', '')}: {case.get('title', '')}",
                "",
                f"- Adjudication: `{case.get('adjudication_status', '')}`",
                f"- Quality-eligible frames: `{case.get('expected_frame_count', 0)}`",
                f"- Unresolved frames: `{case.get('unresolved_frame_count', 0)}`",
                "- Agent invocation completed: "
                f"`{case.get('agent_invocation_completed', False)}`",
                "- Strict usable extraction completed: "
                f"`{case.get('strict_usable_extraction_completed', False)}`",
                f"- Output frames: `{case.get('output_frame_count', 0)}`",
                "- Endpoint/source matches: "
                f"`{case.get('endpoint_source_match_count', 0)}`",
                f"- Full frames correct: `{case.get('full_frame_correct_count', 0)}`",
                f"- Polarity correct: `{case.get('polarity_correct_count', 0)}`",
                f"- Qualifier-concordant: `{case.get('qualifier_concordant_count', 0)}`",
            ),
        )
        run_results = case.get("run_results")
        if isinstance(run_results, list):
            for raw_run in run_results:
                run = _object(raw_run)
                lines.append(
                    "- "
                    f"`{run.get('run_id', '')}`: "
                    f"invocation={run.get('invocation_id', '')}, "
                    "agent_completed="
                    f"{run.get('agent_invocation_completed', False)}, "
                    "strict_usable="
                    f"{run.get('strict_usable_extraction_completed', False)}, "
                    f"output={run.get('output_frame_count', 0)}, "
                    f"endpoint_source={run.get('endpoint_source_match_count', 0)}, "
                    f"full_frame={run.get('full_frame_correct_count', 0)}, "
                    f"polarity={run.get('polarity_correct_count', 0)}, "
                    f"qualifiers={run.get('qualifier_concordant_count', 0)}"
                )
        elif case.get("output_sha256"):
            lines.append(
                f"- Model-boundary output SHA-256: `{case.get('output_sha256', '')}`"
            )
            lines.append(
                "- Postprocessed candidate SHA-256: "
                f"`{case.get('postprocessed_output_sha256', '')}`"
            )
        lines.append("")
    unresolved = report.get("unresolved_frames")
    if isinstance(unresolved, list) and unresolved:
        lines.extend(("## Unresolved Gold Frames", ""))
        for raw_case in unresolved:
            case = _object(raw_case)
            lines.append(
                f"- `{case.get('case_id', '')}/{case.get('frame_id', '')}`: "
                "excluded from quality denominators",
            )
        lines.append("")
    return "\n".join(lines)


def _object(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


__all__ = ["render_markdown", "write_reports"]
