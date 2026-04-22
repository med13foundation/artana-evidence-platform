#!/usr/bin/env python3
"""Aggregate real-space canary reports into one rollout-review verdict."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

type JSONObject = dict[str, object]
CanaryVerdict = Literal["pass", "hold", "rollback_required"]

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INPUT_ROOT = _REPO_ROOT / "reports" / "full_ai_orchestrator_real_space_canary"
_DEFAULT_OUTPUT_ROOT = _REPO_ROOT / "reports" / "full_ai_orchestrator_rollout_review"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Review selected real-space guarded source+chase canary reports "
            "as one staged-rollout evidence pack."
        ),
    )
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        help="Path to a canary summary.json, summary.md sibling directory, or report directory.",
    )
    parser.add_argument(
        "--reports",
        default="",
        help="Comma-separated report paths. Useful for Makefile/env forwarding.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=_DEFAULT_INPUT_ROOT,
        help="Directory used by --latest-count. Defaults to real-space canary reports.",
    )
    parser.add_argument(
        "--latest-count",
        type=int,
        default=0,
        help="Select the latest N reports from --report-dir when no explicit reports are passed.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for the generated rollout review. Defaults to reports/full_ai_orchestrator_rollout_review/<timestamp>/.",
    )
    parser.add_argument(
        "--minimum-pass-reports",
        type=int,
        default=3,
        help="Minimum selected reports with canary verdict pass. Defaults to 3.",
    )
    parser.add_argument(
        "--minimum-passing-spaces",
        type=int,
        default=3,
        help="Minimum distinct spaces with per-space pass. Defaults to 3.",
    )
    parser.add_argument(
        "--minimum-authority-runs",
        type=int,
        default=3,
        help="Minimum source+chase runs where profile authority was exercised. Defaults to 3.",
    )
    parser.add_argument(
        "--minimum-source-interventions",
        type=int,
        default=3,
        help="Minimum source-selection interventions across selected reports. Defaults to 3.",
    )
    parser.add_argument(
        "--minimum-chase-stop-interventions",
        type=int,
        default=3,
        help="Minimum chase/stop interventions across selected reports. Defaults to 3.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    args = parse_args(argv)
    output_dir = _resolve_output_dir(args.output_dir)
    report_paths = _resolve_report_paths(args)
    review = build_rollout_review(
        report_paths=report_paths,
        minimum_pass_reports=_positive_int(
            args.minimum_pass_reports,
            "minimum_pass_reports",
        ),
        minimum_passing_spaces=_positive_int(
            args.minimum_passing_spaces,
            "minimum_passing_spaces",
        ),
        minimum_authority_runs=_positive_int(
            args.minimum_authority_runs,
            "minimum_authority_runs",
        ),
        minimum_source_interventions=_positive_int(
            args.minimum_source_interventions,
            "minimum_source_interventions",
        ),
        minimum_chase_stop_interventions=_positive_int(
            args.minimum_chase_stop_interventions,
            "minimum_chase_stop_interventions",
        ),
    )
    manifest = write_rollout_review(review=review, output_dir=output_dir)
    print(render_rollout_review_markdown(review))
    print()
    print(f"Summary JSON: {manifest['summary_json']}")
    print(f"Summary Markdown: {manifest['summary_markdown']}")
    return 0 if _dict_value(review.get("rollout_gate")).get("verdict") == "pass" else 1


def build_rollout_review(  # noqa: PLR0913
    *,
    report_paths: Sequence[Path],
    minimum_pass_reports: int,
    minimum_passing_spaces: int,
    minimum_authority_runs: int,
    minimum_source_interventions: int,
    minimum_chase_stop_interventions: int,
) -> JSONObject:
    """Build one rollout-review payload from selected real-space canary reports."""

    report_entries = [_load_report_entry(path) for path in report_paths]
    summary = _aggregate_report_entries(report_entries)
    thresholds: JSONObject = {
        "minimum_pass_reports": minimum_pass_reports,
        "minimum_passing_spaces": minimum_passing_spaces,
        "minimum_authority_runs": minimum_authority_runs,
        "minimum_source_interventions": minimum_source_interventions,
        "minimum_chase_stop_interventions": minimum_chase_stop_interventions,
    }
    gate = _build_rollout_gate(summary=summary, thresholds=thresholds)
    return {
        "report_name": "full_ai_orchestrator_rollout_review",
        "generated_at": datetime.now(UTC).isoformat(),
        "selected_report_paths": [str(path) for path in report_paths],
        "thresholds": thresholds,
        "summary": summary,
        "rollout_gate": gate,
        "reports": report_entries,
        "all_passed": _maybe_string(gate.get("verdict")) == "pass",
    }


def render_rollout_review_markdown(review: JSONObject) -> str:
    """Render a concise human-readable rollout review."""

    summary = _dict_value(review.get("summary"))
    gate = _dict_value(review.get("rollout_gate"))
    thresholds = _dict_value(review.get("thresholds"))
    lines = [
        "# Full AI Orchestrator Rollout Review",
        "",
        f"- Selected reports: `{_int_value(summary.get('selected_report_count'))}`",
        f"- Pass reports: `{_int_value(summary.get('pass_report_count'))}`",
        f"- Hold reports: `{_int_value(summary.get('hold_report_count'))}`",
        f"- Rollback reports: `{_int_value(summary.get('rollback_report_count'))}`",
        f"- Malformed reports: `{_int_value(summary.get('malformed_report_count'))}`",
        f"- Completed runs: `{_int_value(summary.get('completed_run_count'))}`",
        f"- Failed runs: `{_int_value(summary.get('failed_run_count'))}`",
        f"- Timed out runs: `{_int_value(summary.get('timed_out_run_count'))}`",
        f"- Source interventions: `{_int_value(summary.get('source_selection_intervention_count'))}`",
        f"- Chase/stop interventions: `{_int_value(summary.get('chase_or_stop_intervention_count'))}`",
        f"- Authority exercised runs: `{_int_value(summary.get('profile_authority_exercised_count'))}`",
        f"- Distinct spaces: `{_int_value(summary.get('distinct_space_count'))}`",
        f"- Passing spaces: `{_int_value(summary.get('passing_space_count'))}`",
        "",
        "## Thresholds",
        "",
        f"- Pass reports: `{_int_value(thresholds.get('minimum_pass_reports'))}`",
        f"- Passing spaces: `{_int_value(thresholds.get('minimum_passing_spaces'))}`",
        f"- Authority runs: `{_int_value(thresholds.get('minimum_authority_runs'))}`",
        f"- Source interventions: `{_int_value(thresholds.get('minimum_source_interventions'))}`",
        f"- Chase/stop interventions: `{_int_value(thresholds.get('minimum_chase_stop_interventions'))}`",
        "",
        f"## Rollout Verdict: `{_maybe_string(gate.get('verdict')) or 'unknown'}`",
        "",
        _maybe_string(gate.get("note")) or "No verdict note available.",
    ]
    rollback_reasons = _string_list(gate.get("rollback_reasons"))
    hold_reasons = _string_list(gate.get("hold_reasons"))
    if rollback_reasons:
        lines.extend(["", "### Rollback Reasons", ""])
        lines.extend(f"- {reason}" for reason in rollback_reasons)
    if hold_reasons:
        lines.extend(["", "### Hold Reasons", ""])
        lines.extend(f"- {reason}" for reason in hold_reasons)
    next_step = _maybe_string(gate.get("operator_next_step"))
    if next_step is not None:
        lines.extend(["", "### Next Step", "", f"- {next_step}"])
    lines.extend(["", "## Selected Reports", ""])
    for report in _list_of_dicts(review.get("reports")):
        lines.append(
            "- "
            f"`{_maybe_string(report.get('path')) or 'unknown'}`: "
            f"verdict `{_maybe_string(report.get('verdict')) or 'unknown'}`, "
            f"label `{_maybe_string(report.get('canary_label')) or 'none'}`, "
            f"spaces `{_int_value(report.get('distinct_space_count'))}`, "
            f"authority `{_int_value(report.get('profile_authority_exercised_count'))}`"
        )
    return "\n".join(lines)


def write_rollout_review(
    *,
    review: JSONObject,
    output_dir: Path,
) -> dict[str, str]:
    """Write rollout review JSON and Markdown files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_json = output_dir / "summary.json"
    summary_markdown = output_dir / "summary.md"
    summary_json.write_text(
        json.dumps(review, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_markdown.write_text(
        render_rollout_review_markdown(review) + "\n",
        encoding="utf-8",
    )
    return {
        "summary_json": str(summary_json),
        "summary_markdown": str(summary_markdown),
    }


def _load_report_entry(path: Path) -> JSONObject:
    resolved_path = _resolve_summary_path(path)
    if not resolved_path.exists():
        return {
            "path": str(resolved_path),
            "verdict": "rollback_required",
            "malformed": True,
            "errors": [f"report not found: {resolved_path}"],
        }
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "path": str(resolved_path),
            "verdict": "rollback_required",
            "malformed": True,
            "errors": [f"report JSON is invalid: {exc}"],
        }
    if not isinstance(payload, dict):
        return {
            "path": str(resolved_path),
            "verdict": "rollback_required",
            "malformed": True,
            "errors": ["report root must be a JSON object"],
        }
    return _report_entry_from_payload(path=resolved_path, payload=dict(payload))


def _report_entry_from_payload(*, path: Path, payload: JSONObject) -> JSONObject:
    summary = _dict_value(payload.get("summary"))
    canary_gate = _dict_value(payload.get("canary_gate"))
    automated_gates = _dict_value(payload.get("automated_gates"))
    errors: list[str] = []
    if not summary:
        errors.append("summary section missing")
    if not canary_gate:
        errors.append("canary_gate section missing")
    if not automated_gates:
        errors.append("automated_gates section missing")
    verdict = _normalize_verdict(canary_gate.get("verdict"))
    if errors:
        verdict = "rollback_required"
    space_rollout_summary = _dict_value(summary.get("space_rollout_summary"))
    passing_spaces = _space_ids_for_verdict(space_rollout_summary, "pass")
    held_spaces = _space_ids_for_verdict(space_rollout_summary, "hold")
    rollback_spaces = _space_ids_for_verdict(
        space_rollout_summary,
        "rollback_required",
    )
    return {
        "path": str(path),
        "report_name": _maybe_string(payload.get("report_name")),
        "canary_label": _maybe_string(payload.get("canary_label")),
        "generated_at": _maybe_string(payload.get("generated_at")),
        "verdict": verdict,
        "malformed": bool(errors),
        "errors": errors,
        "automated_gates_passed": automated_gates.get("all_passed") is True,
        "requested_run_count": _int_value(summary.get("requested_run_count")),
        "actual_run_count": _int_value(summary.get("actual_run_count")),
        "completed_run_count": _int_value(summary.get("completed_run_count")),
        "failed_run_count": _int_value(summary.get("failed_run_count")),
        "timed_out_run_count": _int_value(summary.get("timed_out_run_count")),
        "malformed_run_count": _int_value(summary.get("malformed_run_count")),
        "invalid_output_count": _int_value(summary.get("invalid_output_count")),
        "fallback_count": _int_value(summary.get("fallback_count")),
        "budget_violation_count": _int_value(summary.get("budget_violation_count")),
        "disabled_source_violation_count": _int_value(
            summary.get("disabled_source_violation_count"),
        ),
        "reserved_source_violation_count": _int_value(
            summary.get("reserved_source_violation_count"),
        ),
        "context_only_source_violation_count": _int_value(
            summary.get("context_only_source_violation_count"),
        ),
        "grounding_source_violation_count": _int_value(
            summary.get("grounding_source_violation_count"),
        ),
        "source_selection_intervention_count": _int_value(
            summary.get("source_selection_intervention_count"),
        ),
        "chase_or_stop_intervention_count": _int_value(
            summary.get("chase_or_stop_intervention_count"),
        ),
        "profile_authority_exercised_count": _int_value(
            summary.get("profile_authority_exercised_count"),
        ),
        "distinct_space_count": _int_value(canary_gate.get("distinct_space_count")),
        "passing_spaces": passing_spaces,
        "held_spaces": held_spaces,
        "rollback_spaces": rollback_spaces,
    }


def _aggregate_report_entries(report_entries: list[JSONObject]) -> JSONObject:
    passing_spaces: set[str] = set()
    held_spaces: set[str] = set()
    rollback_spaces: set[str] = set()
    distinct_spaces: set[str] = set()
    for entry in report_entries:
        entry_passing_spaces = set(_string_list(entry.get("passing_spaces")))
        entry_held_spaces = set(_string_list(entry.get("held_spaces")))
        entry_rollback_spaces = set(_string_list(entry.get("rollback_spaces")))
        passing_spaces.update(entry_passing_spaces)
        held_spaces.update(entry_held_spaces)
        rollback_spaces.update(entry_rollback_spaces)
        distinct_spaces.update(entry_passing_spaces)
        distinct_spaces.update(entry_held_spaces)
        distinct_spaces.update(entry_rollback_spaces)
    return {
        "selected_report_count": len(report_entries),
        "pass_report_count": sum(
            1 for entry in report_entries if entry.get("verdict") == "pass"
        ),
        "hold_report_count": sum(
            1 for entry in report_entries if entry.get("verdict") == "hold"
        ),
        "rollback_report_count": sum(
            1 for entry in report_entries if entry.get("verdict") == "rollback_required"
        ),
        "malformed_report_count": sum(
            1 for entry in report_entries if entry.get("malformed") is True
        ),
        "automated_gate_failure_count": sum(
            1
            for entry in report_entries
            if entry.get("automated_gates_passed") is not True
        ),
        "requested_run_count": _sum_field(report_entries, "requested_run_count"),
        "actual_run_count": _sum_field(report_entries, "actual_run_count"),
        "completed_run_count": _sum_field(report_entries, "completed_run_count"),
        "failed_run_count": _sum_field(report_entries, "failed_run_count"),
        "timed_out_run_count": _sum_field(report_entries, "timed_out_run_count"),
        "malformed_run_count": _sum_field(report_entries, "malformed_run_count"),
        "invalid_output_count": _sum_field(report_entries, "invalid_output_count"),
        "fallback_count": _sum_field(report_entries, "fallback_count"),
        "budget_violation_count": _sum_field(report_entries, "budget_violation_count"),
        "disabled_source_violation_count": _sum_field(
            report_entries,
            "disabled_source_violation_count",
        ),
        "reserved_source_violation_count": _sum_field(
            report_entries,
            "reserved_source_violation_count",
        ),
        "context_only_source_violation_count": _sum_field(
            report_entries,
            "context_only_source_violation_count",
        ),
        "grounding_source_violation_count": _sum_field(
            report_entries,
            "grounding_source_violation_count",
        ),
        "source_selection_intervention_count": _sum_field(
            report_entries,
            "source_selection_intervention_count",
        ),
        "chase_or_stop_intervention_count": _sum_field(
            report_entries,
            "chase_or_stop_intervention_count",
        ),
        "profile_authority_exercised_count": _sum_field(
            report_entries,
            "profile_authority_exercised_count",
        ),
        "distinct_space_count": len(distinct_spaces),
        "passing_space_count": len(passing_spaces),
        "held_space_count": len(held_spaces),
        "rollback_space_count": len(rollback_spaces),
        "passing_spaces": sorted(passing_spaces),
        "held_spaces": sorted(held_spaces),
        "rollback_spaces": sorted(rollback_spaces),
    }


def _build_rollout_gate(*, summary: JSONObject, thresholds: JSONObject) -> JSONObject:
    rollback_reasons = _rollout_rollback_reasons(summary)
    hold_reasons = _rollout_hold_reasons(summary=summary, thresholds=thresholds)
    verdict: CanaryVerdict
    note: str
    if rollback_reasons:
        verdict = "rollback_required"
        note = rollback_reasons[0]
    elif hold_reasons:
        verdict = "hold"
        note = hold_reasons[0]
    else:
        verdict = "pass"
        note = (
            "Selected real-space canary evidence is clean enough for cautious "
            "guarded_source_chase rollout review."
        )
    return {
        "verdict": verdict,
        "note": note,
        "rollback_reasons": rollback_reasons,
        "hold_reasons": hold_reasons,
        "operator_next_step": _operator_next_step(verdict),
    }


def _rollout_rollback_reasons(summary: JSONObject) -> list[str]:
    reasons: list[str] = []
    if _int_value(summary.get("malformed_report_count")) > 0:
        reasons.append("one or more selected reports were malformed")
    if _int_value(summary.get("rollback_report_count")) > 0:
        reasons.append("one or more selected canary reports required rollback")
    if _int_value(summary.get("automated_gate_failure_count")) > 0:
        reasons.append("one or more selected reports failed automated gates")
    if _int_value(summary.get("failed_run_count")) > 0:
        reasons.append("one or more selected runs failed")
    if _int_value(summary.get("timed_out_run_count")) > 0:
        reasons.append("one or more selected runs timed out")
    if _int_value(summary.get("malformed_run_count")) > 0:
        reasons.append("one or more selected runs had malformed payloads")
    if _int_value(summary.get("invalid_output_count")) > 0:
        reasons.append("invalid planner outputs were present")
    if _int_value(summary.get("fallback_count")) > 0:
        reasons.append("fallback planner outputs were present")
    if _int_value(summary.get("budget_violation_count")) > 0:
        reasons.append("budget violations were present")
    for field_name, label in (
        ("disabled_source_violation_count", "disabled"),
        ("reserved_source_violation_count", "reserved"),
        ("context_only_source_violation_count", "context_only"),
        ("grounding_source_violation_count", "grounding"),
    ):
        if _int_value(summary.get(field_name)) > 0:
            reasons.append(f"{label} source-policy violations were present")
    return reasons


def _rollout_hold_reasons(*, summary: JSONObject, thresholds: JSONObject) -> list[str]:
    reasons: list[str] = []
    minimum_pass_reports = _int_value(thresholds.get("minimum_pass_reports"))
    minimum_passing_spaces = _int_value(thresholds.get("minimum_passing_spaces"))
    minimum_authority_runs = _int_value(thresholds.get("minimum_authority_runs"))
    minimum_source_interventions = _int_value(
        thresholds.get("minimum_source_interventions"),
    )
    minimum_chase_stop_interventions = _int_value(
        thresholds.get("minimum_chase_stop_interventions"),
    )
    if _int_value(summary.get("pass_report_count")) < minimum_pass_reports:
        reasons.append(f"fewer than {minimum_pass_reports} selected reports passed")
    if _int_value(summary.get("passing_space_count")) < minimum_passing_spaces:
        reasons.append(f"fewer than {minimum_passing_spaces} distinct spaces passed")
    if (
        _int_value(summary.get("profile_authority_exercised_count"))
        < minimum_authority_runs
    ):
        reasons.append(
            f"fewer than {minimum_authority_runs} guarded_source_chase runs exercised authority",
        )
    if (
        _int_value(summary.get("source_selection_intervention_count"))
        < minimum_source_interventions
    ):
        reasons.append(
            f"fewer than {minimum_source_interventions} source-selection interventions were observed",
        )
    if (
        _int_value(summary.get("chase_or_stop_intervention_count"))
        < minimum_chase_stop_interventions
    ):
        reasons.append(
            f"fewer than {minimum_chase_stop_interventions} chase/stop interventions were observed",
        )
    return reasons


def _operator_next_step(verdict: CanaryVerdict) -> str:
    if verdict == "rollback_required":
        return "Keep affected spaces on deterministic mode and investigate the failed evidence pack."
    if verdict == "hold":
        return "Collect more clean low-risk canary evidence before widening guarded_source_chase."
    return "Review the evidence pack with an operator before widening guarded_source_chase to a small canary."


def _resolve_report_paths(args: argparse.Namespace) -> list[Path]:
    explicit_reports = [
        *_path_list(args.report),
        *_csv_path_list(_maybe_string(args.reports) or ""),
    ]
    if explicit_reports:
        return [_resolve_summary_path(path) for path in explicit_reports]
    latest_count = _positive_int(args.latest_count, "latest_count")
    if latest_count <= 0:
        raise SystemExit(
            "Provide --report/--reports, or pass --latest-count to select recent reports.",
        )
    report_dir = _resolve_path(args.report_dir)
    candidates = sorted(
        report_dir.glob("*/summary.json"),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    if not candidates:
        raise SystemExit(f"No summary.json reports found under {report_dir}.")
    return candidates[:latest_count]


def _resolve_summary_path(path: Path) -> Path:
    resolved = _resolve_path(path)
    if resolved.is_dir():
        return resolved / "summary.json"
    if resolved.name == "summary.md":
        return resolved.with_suffix(".json")
    return resolved


def _resolve_output_dir(output_dir: Path | None) -> Path:
    if output_dir is not None:
        return _resolve_path(output_dir)
    return _DEFAULT_OUTPUT_ROOT / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _resolve_path(path: Path) -> Path:
    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return expanded
    return (_REPO_ROOT / expanded).resolve()


def _path_list(values: Sequence[str]) -> list[Path]:
    return [Path(value.strip()) for value in values if value.strip()]


def _csv_path_list(value: str) -> list[Path]:
    return [Path(part.strip()) for part in value.split(",") if part.strip()]


def _space_ids_for_verdict(
    space_rollout_summary: JSONObject,
    verdict: CanaryVerdict,
) -> list[str]:
    return [
        space_id
        for space_id in sorted(space_rollout_summary)
        if _maybe_string(
            _dict_value(space_rollout_summary.get(space_id)).get("space_verdict"),
        )
        == verdict
    ]


def _sum_field(entries: Sequence[JSONObject], field_name: str) -> int:
    return sum(_int_value(entry.get(field_name)) for entry in entries)


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SystemExit(f"{name} must be an integer.")
    if value < 0:
        raise SystemExit(f"{name} must be >= 0.")
    return value


def _normalize_verdict(value: object) -> CanaryVerdict:
    text = _maybe_string(value)
    if text in {"pass", "hold", "rollback_required"}:
        return text
    return "rollback_required"


def _dict_value(value: object) -> JSONObject:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _list_of_dicts(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [_dict_value(item) for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _maybe_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
