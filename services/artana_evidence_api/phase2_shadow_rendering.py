"""Markdown and file output helpers for Phase 2 shadow-planner evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from artana_evidence_api.phase2_shadow_summary import (
    _dict_value,
    _fixture_report_stem,
    _list_of_dicts,
    _string_list,
)
from artana_evidence_api.types.common import JSONObject

PHASE2_SHADOW_REPORT_VERSION = "phase2-shadow-v10"

def render_phase2_shadow_evaluation_markdown(report: JSONObject) -> str:
    """Render a concise Markdown summary for human review."""

    summary = _dict_value(report.get("summary"))
    automated_gates = _dict_value(report.get("automated_gates"))
    fixtures = _list_of_dicts(report.get("fixtures"))
    manual_review = _dict_value(report.get("manual_review"))
    cost_tracking = _dict_value(report.get("cost_tracking"))

    lines = [
        "# Phase 2 Shadow Planner Evaluation",
        "",
        f"- Generated: {report.get('generated_at', 'n/a')}",
        f"- Report version: {report.get('report_version', PHASE2_SHADOW_REPORT_VERSION)}",
        f"- Automated gates: {_status_label(bool(automated_gates.get('all_passed')))}",
        "",
        "## Overall Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Fixtures | {summary.get('fixture_count', 0)} |",
        f"| Runs | {summary.get('run_count', 0)} |",
        f"| Checkpoints | {summary.get('total_checkpoints', 0)} |",
        f"| Chase checkpoints | {summary.get('chase_checkpoint_count', 0)} |",
        f"| Checkpoints with filtered chase candidates | {summary.get('checkpoints_with_filtered_chase_candidates', 0)} |",
        f"| Filtered chase candidates | {summary.get('filtered_chase_candidate_total', 0)} |",
        f"| Action matches | {summary.get('action_matches', 0)} ({_percent_text(summary.get('action_match_rate'))}) |",
        f"| Chase action matches | {summary.get('chase_action_matches', 0)} ({_percent_text(summary.get('chase_action_match_rate'))}) |",
        f"| Source matches | {summary.get('source_matches', 0)} ({_percent_text(summary.get('source_match_rate'))}) |",
        f"| Stop matches | {summary.get('stop_matches', 0)} ({_percent_text(summary.get('stop_match_rate'))}) |",
        f"| Exact chase selection matches | {summary.get('exact_chase_selection_matches', 0)} / {summary.get('chase_selection_available_count', 0)} ({_percent_text(summary.get('exact_chase_selection_match_rate'))}) |",
        f"| Selected-entity overlap | {_int_text(summary.get('selected_entity_overlap_total'))} |",
        f"| Planner-only noisy expansions | {summary.get('planner_only_noisy_expansions', 0)} |",
        f"| Planner conservative stops | {summary.get('planner_conservative_stops', 0)} |",
        f"| Planner stopped while deterministic would continue | {summary.get('planner_stopped_while_deterministic_continue_count', 0)} |",
        f"| Planner continued when threshold stop | {summary.get('planner_continued_when_threshold_stop_count', 0)} |",
        f"| Planner continued while deterministic would stop | {summary.get('planner_continued_while_deterministic_stop_count', 0)} |",
        f"| Exact-match checkpoints | {summary.get('exact_match_expected_checkpoints', 0)} |",
        f"| Exact-match action rate | {_percent_text(summary.get('exact_match_expected_action_match_rate'))} |",
        f"| Exact-match source rate | {_percent_text(summary.get('exact_match_expected_source_match_rate'))} |",
        f"| Boundary mismatches | {summary.get('boundary_mismatches', 0)} |",
        f"| Source-improvement candidates | {summary.get('source_improvement_candidates', 0)} |",
        f"| Closure-improvement candidates | {summary.get('closure_improvement_candidates', 0)} |",
        f"| Cost telemetry | {cost_tracking.get('status', 'unknown')} |",
        f"| Deterministic baseline telemetry | {cost_tracking.get('deterministic_baseline_status', 'unknown')} |",
        f"| Planner total cost | {_usd_text(cost_tracking.get('planner_total_cost_usd'))} |",
        f"| Deterministic baseline cost | {_usd_text(cost_tracking.get('deterministic_total_cost_usd'))} |",
        f"| Planner / baseline ratio | {_ratio_text(cost_tracking.get('planner_vs_deterministic_cost_ratio'))} |",
        f"| Cost gate (<= 2x baseline) | {_gate_text(cost_tracking.get('gate_within_limit'))} |",
        f"| Planner total tokens | {_int_text(cost_tracking.get('planner_total_tokens'))} |",
        f"| Planner total latency | {_seconds_text(cost_tracking.get('planner_total_latency_seconds'))} |",
        f"| Invalid outputs | {summary.get('invalid_recommendations', 0)} |",
        f"| Fallback recommendations | {summary.get('fallback_recommendations', 0)} |",
        f"| Unavailable recommendations | {summary.get('unavailable_recommendations', 0)} |",
        f"| Disabled-source violations | {summary.get('disabled_source_violations', 0)} |",
        f"| Budget violations | {summary.get('budget_violations', 0)} |",
        f"| Qualitative rationale coverage | {_percent_text(summary.get('qualitative_rationale_coverage'))} |",
        "",
        "## Automated Gates",
        "",
        f"- Minimum fixture coverage met: {_status_label(bool(automated_gates.get('minimum_fixture_coverage_met')))}",
        f"- Minimum run coverage met: {_status_label(bool(automated_gates.get('minimum_run_coverage_met')))}",
        f"- No disabled-source violations: {_status_label(bool(automated_gates.get('no_disabled_source_violations')))}",
        f"- No budget violations: {_status_label(bool(automated_gates.get('no_budget_violations')))}",
        f"- No invalid outputs: {_status_label(bool(automated_gates.get('no_invalid_recommendations')))}",
        f"- No malformed fixture entries: {_status_label(bool(automated_gates.get('no_malformed_fixture_entries')))}",
        f"- Baseline telemetry expected count met: {_status_label(bool(automated_gates.get('deterministic_baseline_expected_count_met')))}",
        f"- No fallback or unavailable recommendations: {_status_label(bool(automated_gates.get('no_fallback_or_unavailable_recommendations')))}",
        f"- Qualitative rationale present everywhere: {_status_label(bool(automated_gates.get('qualitative_rationale_present_everywhere')))}",
        "",
        "## Fixture Summary",
        "",
        "| Fixture | Runs | Checkpoints | Action match | Source match | Source improve | Closure improve | Boundary | Invalid | Fallback | Priority review |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    priority_fixtures = {
        str(name) for name in _string_list(manual_review.get("priority_fixtures"))
    }
    source_improvement_fixtures = {
        str(name)
        for name in _string_list(
            manual_review.get("source_improvement_candidate_fixtures"),
        )
    }
    closure_improvement_fixtures = {
        str(name)
        for name in _string_list(
            manual_review.get("closure_improvement_candidate_fixtures"),
        )
    }
    boundary_fixtures = {
        str(name) for name in _string_list(manual_review.get("boundary_fixtures"))
    }
    for fixture_report in fixtures:
        fixture_summary = _dict_value(fixture_report.get("summary"))
        fixture_name = str(fixture_report.get("fixture_name", "unknown"))
        lines.append(
            "| "
            f"{fixture_name} | "
            f"{fixture_summary.get('run_count', 0)} | "
            f"{fixture_summary.get('total_checkpoints', 0)} | "
            f"{_percent_text(fixture_summary.get('action_match_rate'))} | "
            f"{_percent_text(fixture_summary.get('source_match_rate'))} | "
            f"{fixture_summary.get('source_improvement_candidates', 0)} | "
            f"{fixture_summary.get('closure_improvement_candidates', 0)} | "
            f"{fixture_summary.get('boundary_mismatches', 0)} | "
            f"{fixture_summary.get('invalid_recommendations', 0)} | "
            f"{fixture_summary.get('fallback_recommendations', 0)} | "
            f"{'yes' if fixture_name in priority_fixtures else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Manual Review",
            "",
            (
                "- Human review is required for all fixtures to judge relevance, "
                "rationale quality, and whether the planner avoids irrelevant sources."
            ),
            (
                "- Priority fixtures: "
                + (
                    ", ".join(sorted(priority_fixtures))
                    if priority_fixtures
                    else "none"
                )
            ),
            (
                "- Source-improvement candidate fixtures: "
                + (
                    ", ".join(sorted(source_improvement_fixtures))
                    if source_improvement_fixtures
                    else "none"
                )
            ),
            (
                "- Closure-improvement candidate fixtures: "
                + (
                    ", ".join(sorted(closure_improvement_fixtures))
                    if closure_improvement_fixtures
                    else "none"
                )
            ),
            (
                "- Boundary fixtures: "
                + (
                    ", ".join(sorted(boundary_fixtures))
                    if boundary_fixtures
                    else "none"
                )
            ),
            (
                "- Boundary mismatches mean the deterministic next action was "
                "not selectable by the shadow planner yet, so exact match was "
                "not expected at that checkpoint."
            ),
            "",
            "## Cost Tracking",
            "",
            f"- Status: {cost_tracking.get('status', 'unknown')}",
            (
                "- Deterministic baseline status: "
                f"{cost_tracking.get('deterministic_baseline_status', 'unknown')}"
            ),
            (
                "- Checkpoints with cost telemetry: "
                f"{cost_tracking.get('cost_available_checkpoints', 0)} / "
                f"{cost_tracking.get('total_checkpoints', 0)}"
            ),
            (
                "- Planner total cost: "
                f"{_usd_text(cost_tracking.get('planner_total_cost_usd'))}"
            ),
            (
                "- Deterministic baseline cost: "
                f"{_usd_text(cost_tracking.get('deterministic_total_cost_usd'))}"
            ),
            (
                "- Planner / baseline ratio: "
                f"{_ratio_text(cost_tracking.get('planner_vs_deterministic_cost_ratio'))}"
            ),
            (
                "- Cost gate (<= 2x baseline): "
                f"{_gate_text(cost_tracking.get('gate_within_limit'))}"
            ),
            (
                "- Planner total tokens: "
                f"{_int_text(cost_tracking.get('planner_total_tokens'))}"
            ),
            (
                "- Planner total latency: "
                f"{_seconds_text(cost_tracking.get('planner_total_latency_seconds'))}"
            ),
            f"- Notes: {cost_tracking.get('notes', 'n/a')}",
            "",
        ]
    )
    return "\n".join(lines)


def write_phase2_shadow_evaluation_report(
    report: JSONObject,
    *,
    output_dir: str | Path,
) -> JSONObject:
    """Write the aggregate report, per-fixture JSON, and Markdown summary."""

    _validate_phase2_shadow_report_payload(report)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    summary_json_path = output_dir_path / "summary.json"
    summary_markdown_path = output_dir_path / "summary.md"
    summary_json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_markdown_path.write_text(
        render_phase2_shadow_evaluation_markdown(report) + "\n",
        encoding="utf-8",
    )

    fixture_report_paths: JSONObject = {}
    for fixture_report in _list_of_dicts(report.get("fixtures")):
        fixture_name = str(fixture_report.get("fixture_name", "unknown"))
        fixture_path = output_dir_path / f"{_fixture_report_stem(fixture_name)}.json"
        fixture_path.write_text(
            json.dumps(fixture_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        fixture_report_paths[fixture_name] = str(fixture_path)

    manifest: JSONObject = {
        "output_dir": str(output_dir_path),
        "summary_json": str(summary_json_path),
        "summary_markdown": str(summary_markdown_path),
        "fixture_reports": fixture_report_paths,
    }
    (output_dir_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _validate_phase2_shadow_report_payload(report: object) -> None:
    if not isinstance(report, dict):
        msg = (
            "Phase 2 shadow evaluation report must be a JSON object, got "
            f"{type(report).__name__}."
        )
        raise TypeError(msg)
    missing_sections = [
        section
        for section in ("summary", "automated_gates")
        if not isinstance(report.get(section), dict)
    ]
    if missing_sections:
        msg = (
            "Phase 2 shadow evaluation report is malformed: missing object "
            f"section(s): {', '.join(missing_sections)}."
        )
        raise ValueError(msg)
    fixtures = report.get("fixtures")
    if not isinstance(fixtures, list):
        msg = "Phase 2 shadow evaluation report is malformed: fixtures must be a list."
        raise TypeError(msg)
    for index, fixture in enumerate(fixtures):
        if isinstance(fixture, dict):
            continue
        msg = (
            "Phase 2 shadow evaluation report is malformed: fixture entry "
            f"{index} must be an object, got {type(fixture).__name__}."
        )
        raise TypeError(msg)


def _percent_text(value: object) -> str:
    if isinstance(value, float):
        return f"{value * 100:.1f}%"
    return "n/a"


def _ratio_text(value: object) -> str:
    if isinstance(value, int):
        return f"{float(value):.2f}x"
    if isinstance(value, float):
        return f"{value:.2f}x"
    return "n/a"


def _usd_text(value: object) -> str:
    if isinstance(value, int):
        return f"${float(value):.4f}"
    if isinstance(value, float):
        return f"${value:.4f}"
    return "n/a"


def _seconds_text(value: object) -> str:
    if isinstance(value, int):
        return f"{float(value):.3f}s"
    if isinstance(value, float):
        return f"{value:.3f}s"
    return "n/a"


def _int_text(value: object) -> str:
    return str(value) if isinstance(value, int) else "n/a"


def _status_label(value: object) -> str:
    return "PASS" if bool(value) else "FAIL"


def _gate_text(value: object) -> str:
    if value is None:
        return "n/a"
    return _status_label(value)




__all__ = [
    "render_phase2_shadow_evaluation_markdown",
    "write_phase2_shadow_evaluation_report",
]
