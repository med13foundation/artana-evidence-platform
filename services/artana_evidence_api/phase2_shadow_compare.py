"""Offline evaluation helpers for the Phase 2 shadow planner."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    orchestrator_action_registry,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner import (
    ShadowPlannerRecommendationResult,
    _planner_source_taxonomy,
    build_shadow_planner_comparison,
    recommend_shadow_planner_action,
    shadow_planner_prompt_version,
    shadow_planner_synthesis_readiness,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_object,
    json_object_or_empty,
)

PlannerCallable = Callable[[str, JSONObject, dict[str, bool]], Awaitable[JSONObject]]

DEFAULT_PHASE2_SHADOW_FIXTURE_DIR = (
    Path(__file__).resolve().parent / "tests" / "fixtures" / "shadow_planner"
)
PHASE2_SHADOW_REPORT_VERSION = "phase2-shadow-v10"
_MIN_FIXTURE_COUNT = 4
_MIN_RUN_COUNT = 8
_FIXTURE_REPORT_STEM_PATTERN = re.compile(r"[^a-z0-9]+")
_CHECKPOINT_BOOLEAN_TOTAL_KEYS: tuple[tuple[str, str], ...] = (
    ("action_match", "action_matches"),
    ("source_match", "source_matches"),
    ("stop_match", "stop_matches"),
    ("chase_selection_available", "chase_selection_available_count"),
    ("exact_selection_match", "exact_chase_selection_matches"),
    ("boundary_mismatch", "boundary_mismatches"),
    ("source_improvement_candidate", "source_improvement_candidates"),
    ("closure_improvement_candidate", "closure_improvement_candidates"),
    ("disabled_source_violation", "disabled_source_violations"),
    ("budget_violation", "budget_violations"),
    ("planner_failure", "planner_failures"),
    ("invalid_recommendation", "invalid_recommendations"),
    ("used_fallback", "fallback_recommendations"),
    ("unavailable_recommendation", "unavailable_recommendations"),
    ("planner_conservative_stop", "planner_conservative_stops"),
    (
        "planner_stopped_while_deterministic_continue",
        "planner_stopped_while_deterministic_continue_count",
    ),
    (
        "planner_continued_when_threshold_stop",
        "planner_continued_when_threshold_stop_count",
    ),
    (
        "planner_continued_while_deterministic_stop",
        "planner_continued_while_deterministic_stop_count",
    ),
    (
        "qualitative_rationale_present",
        "qualitative_rationale_present_count",
    ),
    ("malformed_fixture_error", "malformed_fixture_errors"),
)
_EXACT_MATCH_TOTAL_KEYS: tuple[tuple[str, str], ...] = (
    ("action_match", "exact_match_expected_action_matches"),
    ("source_match", "exact_match_expected_source_matches"),
)


class Phase2MalformedFixtureError(TypeError):
    """Raised when a Phase 2 fixture bundle has an invalid outer shape."""


def load_phase2_shadow_fixture(path: str | Path) -> JSONObject:
    """Load one serialized Phase 2 shadow-evaluation fixture bundle."""

    return json_object_or_empty(json.loads(Path(path).read_text(encoding="utf-8")))


def load_phase2_shadow_fixture_paths(
    fixture_dir: str | Path = DEFAULT_PHASE2_SHADOW_FIXTURE_DIR,
) -> list[Path]:
    """Return sorted fixture paths for the Phase 2 shadow evaluation set."""

    fixture_dir_path = Path(fixture_dir)
    if not fixture_dir_path.exists():
        msg = f"fixture directory does not exist: {fixture_dir_path}"
        raise FileNotFoundError(msg)
    return sorted(fixture_dir_path.glob("*.json"))


async def evaluate_phase2_shadow_fixture_bundle(
    fixture_bundle: object,
    *,
    planner_callable: PlannerCallable | None = None,
) -> JSONObject:
    """Replay the shadow planner against one serialized fixture bundle."""

    if not isinstance(fixture_bundle, dict):
        msg = (
            "fixture bundle must be a JSON object, got "
            f"{type(fixture_bundle).__name__}"
        )
        raise Phase2MalformedFixtureError(msg)
    fixture_name = str(fixture_bundle.get("fixture_name", "unknown"))
    runs = fixture_bundle.get("runs")
    if not isinstance(runs, list):
        msg = "fixture bundle must define a list of runs"
        raise Phase2MalformedFixtureError(msg)

    reports: list[JSONObject] = []
    totals = _empty_phase2_totals()
    selected_planner = planner_callable or _default_phase2_planner

    for run_index, run_payload in enumerate(runs):
        if not isinstance(run_payload, dict):
            run_report = _malformed_phase2_run_report(
                fixture_name=fixture_name,
                run_index=run_index,
                error_type="MalformedRunEntry",
                error_message=(
                    "Phase 2 fixture run entry must be an object, got "
                    f"{type(run_payload).__name__}."
                ),
            )
            reports.append(run_report)
            _accumulate_phase2_totals(
                totals=totals,
                checkpoint_reports=_checkpoint_reports_from_run(run_report),
            )
            continue
        run_report = await _evaluate_fixture_run(
            fixture_name=fixture_name,
            run_index=run_index,
            run_payload=run_payload,
            planner_callable=selected_planner,
            deterministic_baseline_telemetry=(
                _extract_deterministic_baseline_telemetry(run_payload)
                or _extract_deterministic_baseline_telemetry(fixture_bundle)
            ),
        )
        reports.append(run_report)
        _accumulate_phase2_totals(
            totals=totals,
            checkpoint_reports=_checkpoint_reports_from_run(run_report),
        )

    summary = _build_phase2_summary(
        fixture_count=1,
        fixture_names=[fixture_name],
        run_count=len(reports),
        totals=totals,
        deterministic_baseline_telemetry_payloads=(
            _deterministic_baseline_telemetry_payloads_from_reports(reports)
        ),
    )
    source_taxonomy = _dict_value(reports[0].get("source_taxonomy")) if reports else {}
    automated_gates = _build_fixture_automated_gates(summary=summary)
    return {
        "fixture_name": fixture_name,
        "report_version": PHASE2_SHADOW_REPORT_VERSION,
        "run_count": summary["run_count"],
        "total_checkpoints": summary["total_checkpoints"],
        "chase_checkpoint_count": summary["chase_checkpoint_count"],
        "source_taxonomy": source_taxonomy,
        "action_matches": summary["action_matches"],
        "chase_action_matches": summary["chase_action_matches"],
        "source_matches": summary["source_matches"],
        "stop_matches": summary["stop_matches"],
        "chase_selection_available_count": summary["chase_selection_available_count"],
        "exact_chase_selection_matches": summary["exact_chase_selection_matches"],
        "disabled_source_violations": summary["disabled_source_violations"],
        "budget_violations": summary["budget_violations"],
        "planner_failures": summary["planner_failures"],
        "invalid_recommendations": summary["invalid_recommendations"],
        "fallback_recommendations": summary["fallback_recommendations"],
        "unavailable_recommendations": summary["unavailable_recommendations"],
        "malformed_fixture_errors": summary["malformed_fixture_errors"],
        "qualitative_rationale_present_count": (
            summary["qualitative_rationale_present_count"]
        ),
        "summary": summary,
        "cost_tracking": _build_phase2_cost_tracking(summary=summary),
        "automated_gates": automated_gates,
        "reports": reports,
    }


async def evaluate_phase2_shadow_fixture_directory(
    fixture_dir: str | Path = DEFAULT_PHASE2_SHADOW_FIXTURE_DIR,
    *,
    planner_callable: PlannerCallable | None = None,
    deterministic_baseline_telemetry_payloads: list[JSONObject] | None = None,
    deterministic_baseline_expected_run_count: int | None = None,
) -> JSONObject:
    """Evaluate the full Phase 2 shadow fixture directory."""

    fixture_reports: list[JSONObject] = []
    fixture_names: list[str] = []
    totals = _empty_phase2_totals()
    run_count = 0

    for fixture_path in load_phase2_shadow_fixture_paths(fixture_dir):
        try:
            fixture_report = await evaluate_phase2_shadow_fixture_bundle(
                load_phase2_shadow_fixture(fixture_path),
                planner_callable=planner_callable,
            )
        except (json.JSONDecodeError, Phase2MalformedFixtureError) as exc:
            fixture_report = _malformed_phase2_fixture_report(
                fixture_path=fixture_path,
                exc=exc,
            )
        fixture_reports.append(fixture_report)
        fixture_name = str(fixture_report.get("fixture_name", fixture_path.stem))
        fixture_names.append(fixture_name)
        run_count += _json_int(fixture_report.get("run_count"))
        _accumulate_phase2_totals(
            totals=totals,
            checkpoint_reports=_checkpoint_reports_from_fixture(fixture_report),
        )

    summary = _build_phase2_summary(
        fixture_count=len(fixture_reports),
        fixture_names=fixture_names,
        run_count=run_count,
        totals=totals,
        deterministic_baseline_telemetry_payloads=(
            deterministic_baseline_telemetry_payloads
            if deterministic_baseline_telemetry_payloads is not None
            else _deterministic_baseline_telemetry_payloads_from_fixtures(
                fixture_reports,
            )
        ),
        deterministic_baseline_expected_run_count=(
            deterministic_baseline_expected_run_count
        ),
    )
    automated_gates = _build_directory_automated_gates(summary=summary)
    priority_review = [
        str(fixture_report.get("fixture_name", "unknown"))
        for fixture_report in fixture_reports
        if _fixture_needs_priority_review(fixture_report)
    ]
    source_improvement_fixtures = [
        str(fixture_report.get("fixture_name", "unknown"))
        for fixture_report in fixture_reports
        if _fixture_has_source_improvement_candidate(fixture_report)
    ]
    closure_improvement_fixtures = [
        str(fixture_report.get("fixture_name", "unknown"))
        for fixture_report in fixture_reports
        if _fixture_has_closure_improvement_candidate(fixture_report)
    ]
    boundary_fixtures = [
        str(fixture_report.get("fixture_name", "unknown"))
        for fixture_report in fixture_reports
        if _fixture_has_boundary_mismatch(fixture_report)
    ]
    source_taxonomy = _dict_value(
        fixture_reports[0].get("source_taxonomy") if fixture_reports else {}
    )
    return {
        "report_version": PHASE2_SHADOW_REPORT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_count": summary["fixture_count"],
        "run_count": summary["run_count"],
        "total_checkpoints": summary["total_checkpoints"],
        "source_taxonomy": source_taxonomy,
        "summary": summary,
        "automated_gates": automated_gates,
        "cost_tracking": _build_phase2_cost_tracking(summary=summary),
        "manual_review": {
            "required_fixtures": fixture_names,
            "priority_fixtures": priority_review,
            "source_improvement_candidate_fixtures": source_improvement_fixtures,
            "closure_improvement_candidate_fixtures": closure_improvement_fixtures,
            "boundary_fixtures": boundary_fixtures,
            "notes": [
                "Human review is still required for source relevance and rationale quality.",
                (
                    "Priority fixtures are those with automated gate failures or "
                    "non-boundary planner-vs-deterministic mismatches that were not "
                    "flagged as objective-shaped source-improvement candidates or "
                    "conservative closure-improvement candidates."
                ),
                (
                    "Boundary fixtures are those where the deterministic next step "
                    "was context_only or reserved, so exact planner match was not "
                    "expected in Phase 2 shadow mode."
                ),
                (
                    "Source-improvement candidates are checkpoints where the planner "
                    "picked a different structured source because the workspace "
                    "objective hints clearly ranked it ahead of the deterministic one."
                ),
                (
                    "Closure-improvement candidates are checkpoints where the planner "
                    "chose GENERATE_BRIEF instead of another chase round only after "
                    "the workspace showed grounded evidence, no pending structured "
                    "sources, and no open questions, gaps, contradictions, or errors."
                ),
            ],
        },
        "fixtures": fixture_reports,
    }


def evaluate_phase2_shadow_fixture_bundle_sync(
    fixture_bundle: JSONObject,
    *,
    planner_callable: PlannerCallable | None = None,
) -> JSONObject:
    """Synchronous wrapper for one fixture bundle."""

    return asyncio.run(
        evaluate_phase2_shadow_fixture_bundle(
            fixture_bundle,
            planner_callable=planner_callable,
        ),
    )


def evaluate_phase2_shadow_fixture_directory_sync(
    fixture_dir: str | Path = DEFAULT_PHASE2_SHADOW_FIXTURE_DIR,
    *,
    planner_callable: PlannerCallable | None = None,
    deterministic_baseline_telemetry_payloads: list[JSONObject] | None = None,
    deterministic_baseline_expected_run_count: int | None = None,
) -> JSONObject:
    """Synchronous wrapper for the whole fixture directory."""

    return asyncio.run(
        evaluate_phase2_shadow_fixture_directory(
            fixture_dir,
            planner_callable=planner_callable,
            deterministic_baseline_telemetry_payloads=(
                deterministic_baseline_telemetry_payloads
            ),
            deterministic_baseline_expected_run_count=(
                deterministic_baseline_expected_run_count
            ),
        ),
    )


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


async def _default_phase2_planner(
    checkpoint_key: str,
    workspace_summary: JSONObject,
    sources: dict[str, bool],
) -> JSONObject:
    result = await recommend_shadow_planner_action(
        checkpoint_key=checkpoint_key,
        objective=str(workspace_summary.get("objective", "")),
        workspace_summary=workspace_summary,
        sources=cast("ResearchSpaceSourcePreferences", sources),
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )
    return {
        "planner_status": result.planner_status,
        "used_fallback": result.used_fallback,
        "validation_error": result.validation_error,
        "initial_validation_error": result.initial_validation_error,
        "repair_attempted": result.repair_attempted,
        "repair_succeeded": result.repair_succeeded,
        "model_id": result.model_id,
        "agent_run_id": result.agent_run_id,
        "prompt_version": result.prompt_version,
        "telemetry": _planner_telemetry_payload(result=result),
        "decision": result.decision.model_dump(mode="json"),
    }


async def _evaluate_checkpoint(
    *,
    fixture_name: str,
    run_id: str,
    checkpoint: object,
    objective: str,
    sources: dict[str, bool],
    planner_callable: PlannerCallable,
) -> JSONObject | None:
    if not isinstance(checkpoint, dict):
        return None

    checkpoint_key = str(checkpoint.get("checkpoint_key", "unknown"))
    workspace_summary: JSONObject = {}
    raw_workspace_summary = checkpoint.get("workspace_summary")
    if isinstance(raw_workspace_summary, dict):
        workspace_summary = dict(raw_workspace_summary)
    workspace_summary.setdefault("objective", objective)
    source_taxonomy = _dict_value(workspace_summary.get("source_taxonomy"))
    if not source_taxonomy:
        source_taxonomy = _planner_source_taxonomy(enabled_sources=sources)

    planner_payload = await planner_callable(
        checkpoint_key,
        workspace_summary,
        sources,
    )
    decision_payload = _dict_value(planner_payload.get("decision"))

    deterministic_payload = _dict_value(checkpoint.get("deterministic_target"))
    comparison: JSONObject = {
        "checkpoint_key": checkpoint_key,
        "comparison_status": "no_target",
        "action_match": False,
        "source_match": False,
        "recommended_action_type": decision_payload.get("action_type"),
        "recommended_source_key": decision_payload.get("source_key"),
        "target_action_type": deterministic_payload.get("action_type"),
        "target_source_key": deterministic_payload.get("source_key"),
    }
    if deterministic_payload:
        comparison = build_shadow_planner_comparison(
            checkpoint_key=checkpoint_key,
            planner_result=_synthetic_planner_result(
                planner_payload=planner_payload,
                decision_payload=decision_payload,
            ),
            deterministic_target=_synthetic_target_decision(
                checkpoint_key=checkpoint_key,
                target_payload=deterministic_payload,
            ),
            workspace_summary=workspace_summary,
        )

    metadata = _dict_value(decision_payload.get("metadata"))
    fallback_reason = _maybe_string(decision_payload.get("fallback_reason"))
    used_fallback = bool(planner_payload.get("used_fallback")) or (
        fallback_reason is not None
    )
    planner_status = str(planner_payload.get("planner_status", "unknown"))
    validation_error = _maybe_string(planner_payload.get("validation_error"))
    initial_validation_error = _maybe_string(
        planner_payload.get("initial_validation_error"),
    )
    repair_attempted = bool(planner_payload.get("repair_attempted"))
    repair_succeeded = bool(planner_payload.get("repair_succeeded"))
    budget_violation = bool(comparison.get("budget_violation"))
    qualitative_rationale_present = bool(
        str(decision_payload.get("qualitative_rationale", "")).strip(),
    )
    invalid_recommendation = planner_status == "invalid" or (
        validation_error is not None
    )
    unavailable_recommendation = planner_status == "unavailable"
    deterministic_target_planner_state = _planner_state_for_action(
        comparison.get("target_action_type"),
    )
    recommended_source_taxonomy = _source_taxonomy_category(
        source_taxonomy=source_taxonomy,
        source_key=decision_payload.get("source_key"),
    )
    deterministic_source_taxonomy = _source_taxonomy_category(
        source_taxonomy=source_taxonomy,
        source_key=comparison.get("target_source_key"),
    )
    exact_match_expected = deterministic_target_planner_state == "live"
    boundary_mismatch = deterministic_target_planner_state in {
        "context_only",
        "reserved",
    } and (
        not bool(comparison.get("action_match"))
        or not bool(comparison.get("source_match"))
    )
    boundary_reason = (
        f"deterministic target action is {deterministic_target_planner_state}"
        if boundary_mismatch
        else None
    )
    source_improvement_candidate, source_improvement_reason = (
        _structured_source_improvement_candidate(
            workspace_summary=workspace_summary,
            planner_status=planner_status,
            recommended_action_type=decision_payload.get("action_type"),
            recommended_source_key=decision_payload.get("source_key"),
            deterministic_action_type=comparison.get("target_action_type"),
            deterministic_source_key=comparison.get("target_source_key"),
        )
    )
    closure_improvement_candidate, closure_improvement_reason = (
        _closure_improvement_candidate(
            workspace_summary=workspace_summary,
            planner_status=planner_status,
            recommended_action_type=decision_payload.get("action_type"),
            deterministic_action_type=comparison.get("target_action_type"),
        )
    )

    model_id = _maybe_string(metadata.get("model_id")) or _maybe_string(
        planner_payload.get("model_id"),
    )
    prompt_version = _maybe_string(metadata.get("prompt_version")) or _maybe_string(
        planner_payload.get("prompt_version"),
    )
    agent_run_id = _maybe_string(metadata.get("agent_run_id")) or _maybe_string(
        planner_payload.get("agent_run_id"),
    )
    telemetry = _planner_telemetry_dict(
        planner_payload=planner_payload,
        metadata=metadata,
    )
    planner_prompt_tokens = _optional_int(telemetry.get("prompt_tokens"))
    planner_completion_tokens = _optional_int(telemetry.get("completion_tokens"))
    planner_total_tokens = _optional_int(telemetry.get("total_tokens"))
    planner_cost_usd = _optional_float(telemetry.get("cost_usd"))
    planner_latency_seconds = _optional_float(telemetry.get("latency_seconds"))
    planner_model_terminal_count = _optional_int(
        telemetry.get("model_terminal_count"),
    )
    planner_tool_call_count = _optional_int(telemetry.get("tool_call_count"))

    return {
        "fixture_name": fixture_name,
        "run_id": run_id,
        "checkpoint_key": checkpoint_key,
        "checkpoint_name": checkpoint_key,
        "chase_checkpoint": checkpoint_key
        in {"after_bootstrap", "after_chase_round_1"},
        "decision_id": decision_payload.get("decision_id"),
        "planner_status": planner_status,
        "recommended_action_type": decision_payload.get("action_type"),
        "recommended_source_key": decision_payload.get("source_key"),
        "recommended_source_taxonomy": recommended_source_taxonomy,
        "recommended_step_key": decision_payload.get("step_key"),
        "deterministic_action_type": comparison.get("target_action_type"),
        "deterministic_source_key": comparison.get("target_source_key"),
        "deterministic_source_taxonomy": deterministic_source_taxonomy,
        "deterministic_step_key": comparison.get("target_step_key"),
        "comparison_status": comparison.get("comparison_status"),
        "source_taxonomy": source_taxonomy,
        "qualitative_rationale_present": qualitative_rationale_present,
        "rationale": decision_payload.get("qualitative_rationale"),
        "deterministic_target_planner_state": deterministic_target_planner_state,
        "exact_match_expected": exact_match_expected,
        "boundary_mismatch": boundary_mismatch,
        "boundary_reason": boundary_reason,
        "source_improvement_candidate": source_improvement_candidate,
        "source_improvement_reason": source_improvement_reason,
        "closure_improvement_candidate": closure_improvement_candidate,
        "closure_improvement_reason": closure_improvement_reason,
        "used_fallback": used_fallback,
        "fallback_reason": fallback_reason,
        "validation_error": validation_error,
        "initial_validation_error": initial_validation_error,
        "repair_attempted": repair_attempted,
        "repair_succeeded": repair_succeeded,
        "planner_failure": planner_status in {"failed", "invalid"},
        "invalid_recommendation": invalid_recommendation,
        "unavailable_recommendation": unavailable_recommendation,
        "disabled_source_violation": fallback_reason == "source_disabled",
        "budget_violation": budget_violation,
        "action_match": bool(comparison.get("action_match")),
        "source_match": bool(comparison.get("source_match")),
        "stop_match": bool(comparison.get("stop_match")),
        "chase_selection_available": bool(comparison.get("chase_selection_available")),
        "exact_selection_match": bool(comparison.get("exact_selection_match")),
        "deterministic_selected_entity_ids": _string_list(
            comparison.get("deterministic_selected_entity_ids"),
        ),
        "deterministic_selected_labels": _string_list(
            comparison.get("deterministic_selected_labels"),
        ),
        "recommended_selected_entity_ids": _string_list(
            comparison.get("recommended_selected_entity_ids"),
        ),
        "recommended_selected_labels": _string_list(
            comparison.get("recommended_selected_labels"),
        ),
        "filtered_chase_candidate_count": _optional_int(
            workspace_summary.get("filtered_chase_candidate_count"),
        ),
        "filtered_chase_filter_reason_counts": _dict_value(
            workspace_summary.get("filtered_chase_filter_reason_counts"),
        ),
        "filtered_chase_labels": [
            str(candidate.get("display_label"))
            for candidate in _list_of_dicts(
                workspace_summary.get("filtered_chase_candidates"),
            )
            if isinstance(candidate.get("display_label"), str)
        ],
        "selected_entity_overlap_count": _optional_int(
            comparison.get("selected_entity_overlap_count"),
        ),
        "deterministic_only_labels": _string_list(
            comparison.get("deterministic_only_labels"),
        ),
        "planner_only_labels": _string_list(comparison.get("planner_only_labels")),
        "planner_conservative_stop": bool(comparison.get("planner_conservative_stop")),
        "planner_stopped_while_deterministic_continue": bool(
            comparison.get("planner_conservative_stop")
        ),
        "planner_continued_when_threshold_stop": bool(
            comparison.get("planner_continued_when_threshold_stop")
        ),
        "planner_continued_while_deterministic_stop": bool(
            comparison.get("planner_continued_when_threshold_stop")
        ),
        "model_id": model_id,
        "prompt_version": (
            prompt_version
            if prompt_version is not None
            else shadow_planner_prompt_version()
        ),
        "telemetry_status": str(telemetry.get("status", "unavailable")),
        "planner_prompt_tokens": planner_prompt_tokens,
        "planner_completion_tokens": planner_completion_tokens,
        "planner_total_tokens": planner_total_tokens,
        "planner_cost_usd": planner_cost_usd,
        "planner_latency_seconds": planner_latency_seconds,
        "planner_model_terminal_count": planner_model_terminal_count,
        "planner_tool_call_count": planner_tool_call_count,
        "telemetry": telemetry,
        "agent_run_id": (
            agent_run_id
            if agent_run_id is not None
            else f"fixture:{fixture_name}:{run_id}:{checkpoint_key}"
        ),
        "comparison": comparison,
    }


async def _evaluate_fixture_run(
    *,
    fixture_name: str,
    run_index: int,
    run_payload: JSONObject,
    planner_callable: PlannerCallable,
    deterministic_baseline_telemetry: JSONObject | None = None,
) -> JSONObject:
    objective = str(run_payload.get("objective", ""))
    sources = {
        key: value
        for key, value in _dict_value(run_payload.get("sources")).items()
        if isinstance(key, str) and isinstance(value, bool)
    }
    checkpoints = run_payload.get("checkpoints")
    if not isinstance(checkpoints, list):
        return _malformed_phase2_run_report(
            fixture_name=fixture_name,
            run_index=run_index,
            run_id=_maybe_string(run_payload.get("run_id")),
            objective=objective,
            error_type="MalformedCheckpointList",
            error_message=(
                "Phase 2 fixture run checkpoints must be a list, got "
                f"{type(checkpoints).__name__}."
            ),
        )

    run_id = _maybe_string(run_payload.get("run_id"))
    if run_id is None:
        run_id = f"{_fixture_report_stem(fixture_name)}-run-{run_index + 1}"

    checkpoint_reports: list[JSONObject] = []
    for checkpoint_index, checkpoint in enumerate(checkpoints):
        if not isinstance(checkpoint, dict):
            checkpoint_reports.append(
                _malformed_phase2_checkpoint_report(
                    fixture_name=fixture_name,
                    run_id=run_id,
                    checkpoint_index=checkpoint_index,
                    objective=objective,
                    error_type="MalformedCheckpointEntry",
                    error_message=(
                        "Phase 2 fixture checkpoint entry must be an object, got "
                        f"{type(checkpoint).__name__}."
                    ),
                ),
            )
            continue
        checkpoint_report = await _evaluate_checkpoint(
            fixture_name=fixture_name,
            run_id=run_id,
            checkpoint=checkpoint,
            objective=objective,
            sources=sources,
            planner_callable=planner_callable,
        )
        if checkpoint_report is not None:
            checkpoint_reports.append(checkpoint_report)

    source_taxonomy = _dict_value(
        checkpoint_reports[0].get("source_taxonomy") if checkpoint_reports else {}
    )
    report: JSONObject = {
        "fixture_name": fixture_name,
        "run_id": run_id,
        "objective": objective,
        "source_taxonomy": source_taxonomy,
        "summary": _build_phase2_run_summary(checkpoint_reports=checkpoint_reports),
        "checkpoint_reports": checkpoint_reports,
    }
    if deterministic_baseline_telemetry is not None:
        report["deterministic_baseline_telemetry"] = deterministic_baseline_telemetry
    return report


def _malformed_phase2_fixture_report(
    *,
    fixture_path: Path,
    exc: BaseException,
) -> JSONObject:
    fixture_name = _fixture_name_from_malformed_path(fixture_path)
    run_report = _malformed_phase2_run_report(
        fixture_name=fixture_name,
        run_index=0,
        run_id=f"{_fixture_report_stem(fixture_name)}-malformed-fixture",
        error_type=type(exc).__name__,
        error_message=str(exc),
    )
    totals = _empty_phase2_totals()
    _accumulate_phase2_totals(
        totals=totals,
        checkpoint_reports=_checkpoint_reports_from_run(run_report),
    )
    summary = _build_phase2_summary(
        fixture_count=1,
        fixture_names=[fixture_name],
        run_count=1,
        totals=totals,
    )
    automated_gates = _build_fixture_automated_gates(summary=summary)
    return {
        "fixture_name": fixture_name,
        "fixture_status": "failed",
        "report_version": PHASE2_SHADOW_REPORT_VERSION,
        "run_count": summary["run_count"],
        "total_checkpoints": summary["total_checkpoints"],
        "chase_checkpoint_count": summary["chase_checkpoint_count"],
        "source_taxonomy": {},
        "action_matches": summary["action_matches"],
        "chase_action_matches": summary["chase_action_matches"],
        "source_matches": summary["source_matches"],
        "stop_matches": summary["stop_matches"],
        "chase_selection_available_count": summary["chase_selection_available_count"],
        "exact_chase_selection_matches": summary["exact_chase_selection_matches"],
        "disabled_source_violations": summary["disabled_source_violations"],
        "budget_violations": summary["budget_violations"],
        "planner_failures": summary["planner_failures"],
        "invalid_recommendations": summary["invalid_recommendations"],
        "fallback_recommendations": summary["fallback_recommendations"],
        "unavailable_recommendations": summary["unavailable_recommendations"],
        "malformed_fixture_errors": summary["malformed_fixture_errors"],
        "qualitative_rationale_present_count": summary[
            "qualitative_rationale_present_count"
        ],
        "summary": summary,
        "cost_tracking": _build_phase2_cost_tracking(summary=summary),
        "automated_gates": automated_gates,
        "fixture_error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "fixture_path": str(fixture_path),
        },
        "reports": [run_report],
    }


def _malformed_phase2_run_report(
    *,
    fixture_name: str,
    run_index: int,
    error_type: str,
    error_message: str,
    run_id: str | None = None,
    objective: str = "",
) -> JSONObject:
    resolved_run_id = (
        run_id
        if run_id is not None
        else f"{_fixture_report_stem(fixture_name)}-run-{run_index + 1}"
    )
    checkpoint_report = _malformed_phase2_checkpoint_report(
        fixture_name=fixture_name,
        run_id=resolved_run_id,
        checkpoint_index=0,
        objective=objective,
        error_type=error_type,
        error_message=error_message,
    )
    return {
        "fixture_name": fixture_name,
        "run_id": resolved_run_id,
        "run_status": "failed",
        "objective": objective,
        "source_taxonomy": {},
        "error": {
            "type": error_type,
            "message": error_message,
        },
        "summary": _build_phase2_run_summary(
            checkpoint_reports=[checkpoint_report],
        ),
        "checkpoint_reports": [checkpoint_report],
    }


def _malformed_phase2_checkpoint_report(
    *,
    fixture_name: str,
    run_id: str,
    checkpoint_index: int,
    objective: str,
    error_type: str,
    error_message: str,
) -> JSONObject:
    checkpoint_key = f"malformed_checkpoint_{checkpoint_index + 1}"
    return {
        "fixture_name": fixture_name,
        "run_id": run_id,
        "checkpoint_key": checkpoint_key,
        "checkpoint_name": checkpoint_key,
        "chase_checkpoint": False,
        "decision_id": None,
        "planner_status": "malformed_fixture",
        "recommended_action_type": None,
        "recommended_source_key": None,
        "recommended_source_taxonomy": None,
        "recommended_step_key": None,
        "deterministic_action_type": None,
        "deterministic_source_key": None,
        "deterministic_source_taxonomy": None,
        "deterministic_step_key": None,
        "comparison_status": "malformed_fixture",
        "source_taxonomy": {},
        "qualitative_rationale_present": False,
        "rationale": None,
        "deterministic_target_planner_state": "missing",
        "exact_match_expected": False,
        "boundary_mismatch": False,
        "boundary_reason": None,
        "source_improvement_candidate": False,
        "source_improvement_reason": None,
        "closure_improvement_candidate": False,
        "closure_improvement_reason": None,
        "used_fallback": False,
        "fallback_reason": None,
        "validation_error": error_message,
        "initial_validation_error": None,
        "repair_attempted": False,
        "repair_succeeded": False,
        "planner_failure": True,
        "invalid_recommendation": True,
        "unavailable_recommendation": False,
        "disabled_source_violation": False,
        "budget_violation": False,
        "action_match": False,
        "source_match": False,
        "stop_match": False,
        "chase_selection_available": False,
        "exact_selection_match": False,
        "deterministic_selected_entity_ids": [],
        "deterministic_selected_labels": [],
        "recommended_selected_entity_ids": [],
        "recommended_selected_labels": [],
        "filtered_chase_candidate_count": None,
        "filtered_chase_filter_reason_counts": {},
        "filtered_chase_labels": [],
        "selected_entity_overlap_count": None,
        "deterministic_only_labels": [],
        "planner_only_labels": [],
        "planner_conservative_stop": False,
        "planner_stopped_while_deterministic_continue": False,
        "planner_continued_when_threshold_stop": False,
        "planner_continued_while_deterministic_stop": False,
        "model_id": None,
        "prompt_version": shadow_planner_prompt_version(),
        "telemetry_status": "unavailable",
        "planner_prompt_tokens": None,
        "planner_completion_tokens": None,
        "planner_total_tokens": None,
        "planner_cost_usd": None,
        "planner_latency_seconds": None,
        "planner_model_terminal_count": None,
        "planner_tool_call_count": None,
        "telemetry": {},
        "agent_run_id": f"fixture:{fixture_name}:{run_id}:{checkpoint_key}",
        "malformed_fixture_error": True,
        "error": {
            "type": error_type,
            "message": error_message,
            "objective": objective,
        },
        "comparison": {
            "checkpoint_key": checkpoint_key,
            "comparison_status": "malformed_fixture",
            "action_match": False,
            "source_match": False,
            "target_action_type": None,
            "target_source_key": None,
            "error_type": error_type,
            "error_message": error_message,
        },
    }


def _structured_source_improvement_candidate(
    *,
    workspace_summary: JSONObject,
    planner_status: str,
    recommended_action_type: object,
    recommended_source_key: object,
    deterministic_action_type: object,
    deterministic_source_key: object,
) -> tuple[bool, str | None]:
    if planner_status != "completed":
        return False, None
    if (
        recommended_action_type
        != ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT.value
        or deterministic_action_type
        != ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT.value
    ):
        return False, None

    recommended_source = _maybe_string(recommended_source_key)
    deterministic_source = _maybe_string(deterministic_source_key)
    if (
        recommended_source is None
        or deterministic_source is None
        or recommended_source == deterministic_source
    ):
        return False, None

    objective_routing_hints = _dict_value(
        workspace_summary.get("objective_routing_hints"),
    )
    preferred_pending_sources = _string_list(
        objective_routing_hints.get("preferred_pending_structured_sources"),
    )
    if not preferred_pending_sources:
        return False, None

    recommended_rank = (
        preferred_pending_sources.index(recommended_source)
        if recommended_source in preferred_pending_sources
        else len(preferred_pending_sources)
    )
    deterministic_rank = (
        preferred_pending_sources.index(deterministic_source)
        if deterministic_source in preferred_pending_sources
        else len(preferred_pending_sources)
    )
    if recommended_rank >= deterministic_rank:
        return False, None

    objective_summary = _maybe_string(objective_routing_hints.get("summary")) or (
        "Objective routing hints preferred the recommended source."
    )
    return (
        True,
        (
            f"{objective_summary} Preferred {recommended_source} ahead of "
            f"{deterministic_source}."
        ),
    )


def _closure_improvement_candidate(
    *,
    workspace_summary: JSONObject,
    planner_status: str,
    recommended_action_type: object,
    deterministic_action_type: object,
) -> tuple[bool, str | None]:
    if planner_status != "completed":
        return False, None
    if (
        recommended_action_type != ResearchOrchestratorActionType.GENERATE_BRIEF.value
        or deterministic_action_type
        != ResearchOrchestratorActionType.RUN_CHASE_ROUND.value
    ):
        return False, None
    synthesis_readiness = shadow_planner_synthesis_readiness(
        workspace_summary=workspace_summary,
    )
    if synthesis_readiness["ready_for_brief"] is not True:
        return False, None
    return (
        True,
        (
            f"{synthesis_readiness['summary']} That makes GENERATE_BRIEF a plausible "
            "value improvement over another bounded chase round."
        ),
    )


def _synthetic_planner_result(
    *,
    planner_payload: JSONObject,
    decision_payload: JSONObject,
) -> ShadowPlannerRecommendationResult:
    normalized_payload = dict(decision_payload)
    action_type = normalized_payload.get("action_type")
    if isinstance(action_type, str):
        normalized_payload["action_type"] = ResearchOrchestratorActionType(action_type)
    decision = ResearchOrchestratorDecision.model_validate(normalized_payload)
    metadata = _dict_value(decision.metadata)
    agent_run_id = _maybe_string(metadata.get("agent_run_id")) or _maybe_string(
        planner_payload.get("agent_run_id"),
    )
    prompt_version = _maybe_string(metadata.get("prompt_version")) or _maybe_string(
        planner_payload.get("prompt_version"),
    )
    model_id = _maybe_string(metadata.get("model_id")) or _maybe_string(
        planner_payload.get("model_id"),
    )
    return ShadowPlannerRecommendationResult(
        decision=decision,
        planner_status=str(planner_payload.get("planner_status", "completed")),
        model_id=model_id,
        agent_run_id=(
            agent_run_id
            if agent_run_id is not None
            else f"fixture:{decision.decision_id}"
        ),
        prompt_version=(
            prompt_version
            if prompt_version is not None
            else shadow_planner_prompt_version()
        ),
        used_fallback=bool(decision.fallback_reason),
        validation_error=_maybe_string(planner_payload.get("validation_error")),
        error=None,
        initial_validation_error=_maybe_string(
            planner_payload.get("initial_validation_error"),
        ),
        repair_attempted=bool(planner_payload.get("repair_attempted")),
        repair_succeeded=bool(planner_payload.get("repair_succeeded")),
    )


def _synthetic_target_decision(
    *,
    checkpoint_key: str,
    target_payload: JSONObject,
) -> ResearchOrchestratorDecision | None:
    action_type = target_payload.get("action_type")
    if not isinstance(action_type, str):
        return None
    return ResearchOrchestratorDecision(
        decision_id=f"fixture-target:{checkpoint_key}",
        round_number=_json_int(target_payload.get("round_number")),
        action_type=ResearchOrchestratorActionType(action_type),
        action_input=_dict_value(target_payload.get("action_input")),
        source_key=(
            str(target_payload.get("source_key"))
            if isinstance(target_payload.get("source_key"), str)
            else None
        ),
        evidence_basis=str(
            target_payload.get("evidence_basis", "Fixture deterministic target.")
        ),
        stop_reason=_maybe_string(target_payload.get("stop_reason")),
        step_key=str(target_payload.get("step_key", f"fixture.{checkpoint_key}")),
        status=str(target_payload.get("status", "completed")),
        metadata=_dict_value(target_payload.get("metadata")),
    )


def _dict_value(value: object) -> JSONObject:
    return json_object_or_empty(value)


def _list_of_dicts(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [
        item_payload
        for item in value
        if (item_payload := json_object(item)) is not None
    ]


def _extract_deterministic_baseline_telemetry(
    value: object,
) -> JSONObject | None:
    if not isinstance(value, dict):
        return None
    direct_payload = value.get("deterministic_baseline_telemetry")
    if isinstance(direct_payload, dict):
        return dict(direct_payload)
    nested_payload = value.get("deterministic_baseline")
    if isinstance(nested_payload, dict):
        telemetry_payload = nested_payload.get("telemetry")
        if isinstance(telemetry_payload, dict):
            return dict(telemetry_payload)
    baseline_payload = value.get("baseline")
    if isinstance(baseline_payload, dict):
        telemetry_payload = baseline_payload.get("telemetry")
        if isinstance(telemetry_payload, dict):
            return dict(telemetry_payload)
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _maybe_string(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value.strip() else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, int):
        return float(value)
    return value if isinstance(value, float) else None


def _json_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _json_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return default


def _empty_phase2_totals() -> JSONObject:
    return {
        "total_checkpoints": 0,
        "chase_checkpoint_count": 0,
        "checkpoints_with_filtered_chase_candidates": 0,
        "filtered_chase_candidate_total": 0,
        "action_matches": 0,
        "chase_action_matches": 0,
        "source_matches": 0,
        "stop_matches": 0,
        "chase_selection_available_count": 0,
        "exact_chase_selection_matches": 0,
        "exact_match_expected_checkpoints": 0,
        "exact_match_expected_action_matches": 0,
        "exact_match_expected_source_matches": 0,
        "boundary_mismatches": 0,
        "source_improvement_candidates": 0,
        "closure_improvement_candidates": 0,
        "disabled_source_violations": 0,
        "budget_violations": 0,
        "planner_failures": 0,
        "invalid_recommendations": 0,
        "fallback_recommendations": 0,
        "unavailable_recommendations": 0,
        "malformed_fixture_errors": 0,
        "selected_entity_overlap_total": 0,
        "planner_only_noisy_expansions": 0,
        "planner_conservative_stops": 0,
        "planner_stopped_while_deterministic_continue_count": 0,
        "planner_continued_when_threshold_stop_count": 0,
        "planner_continued_while_deterministic_stop_count": 0,
        "qualitative_rationale_present_count": 0,
        "telemetry_available_checkpoints": 0,
        "cost_available_checkpoints": 0,
        "zero_cost_with_tokens_checkpoints": 0,
        "token_available_checkpoints": 0,
        "latency_available_checkpoints": 0,
        "planner_total_prompt_tokens": 0,
        "planner_total_completion_tokens": 0,
        "planner_total_cost_usd": 0.0,
        "planner_total_latency_seconds": 0.0,
    }


def _accumulate_chase_totals(
    *,
    totals: JSONObject,
    checkpoint_report: JSONObject,
) -> None:
    if checkpoint_report.get("chase_checkpoint") is not True:
        return
    _increment_total(totals, "chase_checkpoint_count")
    if checkpoint_report.get("action_match") is True:
        _increment_total(totals, "chase_action_matches")


def _accumulate_filtered_chase_totals(
    *,
    totals: JSONObject,
    checkpoint_report: JSONObject,
) -> None:
    filtered_chase_candidate_count = _optional_int(
        checkpoint_report.get("filtered_chase_candidate_count"),
    )
    if filtered_chase_candidate_count is None:
        return
    totals["filtered_chase_candidate_total"] = (
        _json_int(totals["filtered_chase_candidate_total"])
        + filtered_chase_candidate_count
    )
    if filtered_chase_candidate_count > 0:
        _increment_total(
            totals,
            "checkpoints_with_filtered_chase_candidates",
        )


def _accumulate_phase2_totals(
    *,
    totals: JSONObject,
    checkpoint_reports: list[JSONObject],
) -> None:
    for checkpoint_report in checkpoint_reports:
        _increment_total(totals, "total_checkpoints")
        _accumulate_chase_totals(
            totals=totals,
            checkpoint_report=checkpoint_report,
        )
        for checkpoint_key, total_key in _CHECKPOINT_BOOLEAN_TOTAL_KEYS:
            _increment_total_if_true(
                totals=totals,
                checkpoint_report=checkpoint_report,
                checkpoint_key=checkpoint_key,
                total_key=total_key,
            )
        selected_entity_overlap_count = _optional_int(
            checkpoint_report.get("selected_entity_overlap_count"),
        )
        if selected_entity_overlap_count is not None:
            totals["selected_entity_overlap_total"] = (
                _json_int(totals["selected_entity_overlap_total"])
                + selected_entity_overlap_count
            )
        _accumulate_filtered_chase_totals(
            totals=totals,
            checkpoint_report=checkpoint_report,
        )
        if _string_list(checkpoint_report.get("planner_only_labels")):
            _increment_total(totals, "planner_only_noisy_expansions")
        if checkpoint_report.get("exact_match_expected") is True:
            _increment_total(totals, "exact_match_expected_checkpoints")
            for checkpoint_key, total_key in _EXACT_MATCH_TOTAL_KEYS:
                _increment_total_if_true(
                    totals=totals,
                    checkpoint_report=checkpoint_report,
                    checkpoint_key=checkpoint_key,
                    total_key=total_key,
                )
        if checkpoint_report.get("telemetry_status") in {"available", "partial"}:
            _increment_total(totals, "telemetry_available_checkpoints")
        prompt_tokens = _optional_int(checkpoint_report.get("planner_prompt_tokens"))
        completion_tokens = _optional_int(
            checkpoint_report.get("planner_completion_tokens"),
        )
        cost_usd = _optional_float(checkpoint_report.get("planner_cost_usd"))
        latency_seconds = _optional_float(
            checkpoint_report.get("planner_latency_seconds"),
        )
        if prompt_tokens is not None and completion_tokens is not None:
            _increment_total(totals, "token_available_checkpoints")
            totals["planner_total_prompt_tokens"] = (
                _json_int(totals["planner_total_prompt_tokens"]) + prompt_tokens
            )
            totals["planner_total_completion_tokens"] = (
                _json_int(totals["planner_total_completion_tokens"])
                + completion_tokens
            )
        if (
            cost_usd is not None
            and cost_usd == 0.0
            and prompt_tokens is not None
            and completion_tokens is not None
        ):
            _increment_total(totals, "zero_cost_with_tokens_checkpoints")
        if cost_usd is not None and cost_usd > 0.0:
            _increment_total(totals, "cost_available_checkpoints")
            totals["planner_total_cost_usd"] = (
                _json_float(totals["planner_total_cost_usd"]) + cost_usd
            )
        if latency_seconds is not None:
            _increment_total(totals, "latency_available_checkpoints")
            totals["planner_total_latency_seconds"] = (
                _json_float(totals["planner_total_latency_seconds"])
                + latency_seconds
            )


def _checkpoint_reports_from_run(run_report: JSONObject) -> list[JSONObject]:
    return _list_of_dicts(run_report.get("checkpoint_reports"))


def _checkpoint_reports_from_fixture(fixture_report: JSONObject) -> list[JSONObject]:
    checkpoint_reports: list[JSONObject] = []
    for run_report in _list_of_dicts(fixture_report.get("reports")):
        checkpoint_reports.extend(_checkpoint_reports_from_run(run_report))
    return checkpoint_reports


def _deterministic_baseline_telemetry_payloads_from_reports(
    reports: list[JSONObject],
) -> list[JSONObject]:
    payloads: list[JSONObject] = []
    for run_report in reports:
        telemetry_payload = _extract_deterministic_baseline_telemetry(run_report)
        if telemetry_payload is not None:
            payloads.append(telemetry_payload)
    return payloads


def _deterministic_baseline_telemetry_payloads_from_fixtures(
    fixture_reports: list[JSONObject],
) -> list[JSONObject]:
    payloads: list[JSONObject] = []
    for fixture_report in fixture_reports:
        payloads.extend(
            _deterministic_baseline_telemetry_payloads_from_reports(
                _list_of_dicts(fixture_report.get("reports")),
            ),
        )
    return payloads


def _deterministic_baseline_summary(
    payloads: list[JSONObject],
    *,
    expected_run_count: int | None = None,
) -> JSONObject:
    deterministic_baseline_run_count = len(payloads)
    deterministic_baseline_runs_with_cost = 0
    deterministic_baseline_runs_with_tokens = 0
    deterministic_baseline_runs_with_latency = 0
    deterministic_total_prompt_tokens = 0
    deterministic_total_completion_tokens = 0
    deterministic_total_cost_usd = 0.0
    deterministic_total_latency_seconds = 0.0
    for telemetry_payload in payloads:
        prompt_tokens = _optional_int(telemetry_payload.get("prompt_tokens"))
        completion_tokens = _optional_int(telemetry_payload.get("completion_tokens"))
        cost_usd = _optional_float(telemetry_payload.get("cost_usd"))
        latency_seconds = _optional_float(telemetry_payload.get("latency_seconds"))
        if prompt_tokens is not None and completion_tokens is not None:
            deterministic_baseline_runs_with_tokens += 1
            deterministic_total_prompt_tokens += prompt_tokens
            deterministic_total_completion_tokens += completion_tokens
        if cost_usd is not None:
            deterministic_baseline_runs_with_cost += 1
            deterministic_total_cost_usd += cost_usd
        if latency_seconds is not None:
            deterministic_baseline_runs_with_latency += 1
            deterministic_total_latency_seconds += latency_seconds
    normalized_deterministic_prompt_tokens = (
        deterministic_total_prompt_tokens
        if deterministic_baseline_run_count > 0
        and deterministic_baseline_runs_with_tokens == deterministic_baseline_run_count
        else None
    )
    normalized_deterministic_completion_tokens = (
        deterministic_total_completion_tokens
        if deterministic_baseline_run_count > 0
        and deterministic_baseline_runs_with_tokens == deterministic_baseline_run_count
        else None
    )
    normalized_deterministic_total_tokens = None
    if (
        normalized_deterministic_prompt_tokens is not None
        and normalized_deterministic_completion_tokens is not None
    ):
        normalized_deterministic_total_tokens = (
            normalized_deterministic_prompt_tokens
            + normalized_deterministic_completion_tokens
        )
    return {
        "deterministic_baseline_run_count": deterministic_baseline_run_count,
        "deterministic_baseline_expected_run_count": (
            expected_run_count
            if expected_run_count is not None
            else deterministic_baseline_run_count
        ),
        "deterministic_baseline_runs_with_cost": deterministic_baseline_runs_with_cost,
        "deterministic_baseline_runs_with_tokens": (
            deterministic_baseline_runs_with_tokens
        ),
        "deterministic_baseline_runs_with_latency": (
            deterministic_baseline_runs_with_latency
        ),
        "deterministic_total_prompt_tokens": normalized_deterministic_prompt_tokens,
        "deterministic_total_completion_tokens": (
            normalized_deterministic_completion_tokens
        ),
        "deterministic_total_tokens": normalized_deterministic_total_tokens,
        "deterministic_total_cost_usd": deterministic_total_cost_usd,
        "deterministic_total_latency_seconds": deterministic_total_latency_seconds,
    }


def _deterministic_baseline_expected_count_met(summary: JSONObject) -> bool:
    expected_run_count = _optional_int(
        summary.get("deterministic_baseline_expected_run_count"),
    )
    if expected_run_count is None:
        return True
    return _json_int(summary.get("deterministic_baseline_run_count")) == expected_run_count


def _build_phase2_summary(
    *,
    fixture_count: int,
    fixture_names: list[str],
    run_count: int,
    totals: JSONObject,
    deterministic_baseline_telemetry_payloads: list[JSONObject] | None = None,
    deterministic_baseline_expected_run_count: int | None = None,
) -> JSONObject:
    total_checkpoints = _json_int(totals["total_checkpoints"])
    chase_checkpoint_count = _json_int(totals["chase_checkpoint_count"])
    checkpoints_with_filtered_chase_candidates = _json_int(
        totals["checkpoints_with_filtered_chase_candidates"],
    )
    filtered_chase_candidate_total = _json_int(totals["filtered_chase_candidate_total"])
    action_matches = _json_int(totals["action_matches"])
    chase_action_matches = _json_int(totals["chase_action_matches"])
    source_matches = _json_int(totals["source_matches"])
    stop_matches = _json_int(totals["stop_matches"])
    chase_selection_available_count = _json_int(totals["chase_selection_available_count"])
    exact_chase_selection_matches = _json_int(totals["exact_chase_selection_matches"])
    exact_match_expected_checkpoints = _json_int(totals["exact_match_expected_checkpoints"])
    exact_match_expected_action_matches = _json_int(
        totals["exact_match_expected_action_matches"],
    )
    exact_match_expected_source_matches = _json_int(
        totals["exact_match_expected_source_matches"],
    )
    qualitative_rationale_present_count = _json_int(
        totals["qualitative_rationale_present_count"],
    )
    token_available_checkpoints = _json_int(totals["token_available_checkpoints"])
    cost_available_checkpoints = _json_int(totals["cost_available_checkpoints"])
    zero_cost_with_tokens_checkpoints = _json_int(
        totals["zero_cost_with_tokens_checkpoints"],
    )
    latency_available_checkpoints = _json_int(totals["latency_available_checkpoints"])
    planner_total_prompt_tokens = (
        _json_int(totals["planner_total_prompt_tokens"])
        if token_available_checkpoints > 0
        else None
    )
    planner_total_completion_tokens = (
        _json_int(totals["planner_total_completion_tokens"])
        if token_available_checkpoints > 0
        else None
    )
    planner_total_tokens = None
    if (
        planner_total_prompt_tokens is not None
        and planner_total_completion_tokens is not None
    ):
        planner_total_tokens = (
            planner_total_prompt_tokens + planner_total_completion_tokens
        )
    deterministic_summary = _deterministic_baseline_summary(
        (
            deterministic_baseline_telemetry_payloads
            if deterministic_baseline_telemetry_payloads is not None
            else []
        ),
        expected_run_count=deterministic_baseline_expected_run_count,
    )
    return {
        "fixture_count": fixture_count,
        "fixture_names": sorted(fixture_names),
        "run_count": run_count,
        "total_checkpoints": total_checkpoints,
        "chase_checkpoint_count": chase_checkpoint_count,
        "checkpoints_with_filtered_chase_candidates": (
            checkpoints_with_filtered_chase_candidates
        ),
        "filtered_chase_candidate_total": filtered_chase_candidate_total,
        "action_matches": action_matches,
        "action_match_rate": _safe_rate(action_matches, total_checkpoints),
        "chase_action_matches": chase_action_matches,
        "chase_action_match_rate": _safe_rate(
            chase_action_matches,
            chase_checkpoint_count,
        ),
        "source_matches": source_matches,
        "source_match_rate": _safe_rate(source_matches, total_checkpoints),
        "stop_matches": stop_matches,
        "stop_match_rate": _safe_rate(stop_matches, chase_checkpoint_count),
        "chase_selection_available_count": chase_selection_available_count,
        "exact_chase_selection_matches": exact_chase_selection_matches,
        "exact_chase_selection_match_rate": _safe_rate(
            exact_chase_selection_matches,
            chase_selection_available_count,
        ),
        "exact_match_expected_checkpoints": exact_match_expected_checkpoints,
        "exact_match_expected_action_matches": exact_match_expected_action_matches,
        "exact_match_expected_action_match_rate": _safe_rate(
            exact_match_expected_action_matches,
            exact_match_expected_checkpoints,
        ),
        "exact_match_expected_source_matches": exact_match_expected_source_matches,
        "exact_match_expected_source_match_rate": _safe_rate(
            exact_match_expected_source_matches,
            exact_match_expected_checkpoints,
        ),
        "boundary_mismatches": _json_int(totals["boundary_mismatches"]),
        "source_improvement_candidates": _json_int(
            totals["source_improvement_candidates"],
        ),
        "closure_improvement_candidates": _json_int(
            totals["closure_improvement_candidates"],
        ),
        "disabled_source_violations": _json_int(totals["disabled_source_violations"]),
        "budget_violations": _json_int(totals["budget_violations"]),
        "planner_failures": _json_int(totals["planner_failures"]),
        "invalid_recommendations": _json_int(totals["invalid_recommendations"]),
        "fallback_recommendations": _json_int(totals["fallback_recommendations"]),
        "unavailable_recommendations": _json_int(totals["unavailable_recommendations"]),
        "malformed_fixture_errors": _json_int(totals["malformed_fixture_errors"]),
        "selected_entity_overlap_total": _json_int(totals["selected_entity_overlap_total"]),
        "planner_only_noisy_expansions": _json_int(totals["planner_only_noisy_expansions"]),
        "planner_conservative_stops": _json_int(totals["planner_conservative_stops"]),
        "planner_stopped_while_deterministic_continue_count": _json_int(
            totals["planner_stopped_while_deterministic_continue_count"]
        ),
        "planner_continued_when_threshold_stop_count": _json_int(
            totals["planner_continued_when_threshold_stop_count"]
        ),
        "planner_continued_while_deterministic_stop_count": _json_int(
            totals["planner_continued_while_deterministic_stop_count"]
        ),
        "qualitative_rationale_present_count": qualitative_rationale_present_count,
        "qualitative_rationale_coverage": _safe_rate(
            qualitative_rationale_present_count,
            total_checkpoints,
        ),
        "telemetry_available_checkpoints": _json_int(
            totals["telemetry_available_checkpoints"],
        ),
        "cost_available_checkpoints": cost_available_checkpoints,
        "zero_cost_with_tokens_checkpoints": zero_cost_with_tokens_checkpoints,
        "token_available_checkpoints": token_available_checkpoints,
        "latency_available_checkpoints": latency_available_checkpoints,
        "planner_total_prompt_tokens": planner_total_prompt_tokens,
        "planner_total_completion_tokens": planner_total_completion_tokens,
        "planner_total_tokens": planner_total_tokens,
        "planner_total_cost_usd": (
            round(_json_float(totals["planner_total_cost_usd"]), 8)
            if cost_available_checkpoints > 0
            else None
        ),
        "planner_total_latency_seconds": (
            round(_json_float(totals["planner_total_latency_seconds"]), 6)
            if latency_available_checkpoints > 0
            else None
        ),
        "deterministic_baseline_run_count": deterministic_summary[
            "deterministic_baseline_run_count"
        ],
        "deterministic_baseline_expected_run_count": deterministic_summary[
            "deterministic_baseline_expected_run_count"
        ],
        "deterministic_baseline_runs_with_cost": deterministic_summary[
            "deterministic_baseline_runs_with_cost"
        ],
        "deterministic_baseline_runs_with_tokens": deterministic_summary[
            "deterministic_baseline_runs_with_tokens"
        ],
        "deterministic_baseline_runs_with_latency": deterministic_summary[
            "deterministic_baseline_runs_with_latency"
        ],
        "deterministic_total_prompt_tokens": deterministic_summary[
            "deterministic_total_prompt_tokens"
        ],
        "deterministic_total_completion_tokens": deterministic_summary[
            "deterministic_total_completion_tokens"
        ],
        "deterministic_total_tokens": deterministic_summary[
            "deterministic_total_tokens"
        ],
        "deterministic_total_cost_usd": (
            round(_json_float(deterministic_summary["deterministic_total_cost_usd"]), 8)
            if _json_int(deterministic_summary["deterministic_baseline_run_count"]) > 0
            and _json_int(deterministic_summary["deterministic_baseline_runs_with_cost"])
            == _json_int(deterministic_summary["deterministic_baseline_run_count"])
            else None
        ),
        "deterministic_total_latency_seconds": (
            round(
                _json_float(deterministic_summary["deterministic_total_latency_seconds"]),
                6,
            )
            if _json_int(deterministic_summary["deterministic_baseline_run_count"]) > 0
            and _json_int(deterministic_summary["deterministic_baseline_runs_with_latency"])
            == _json_int(deterministic_summary["deterministic_baseline_run_count"])
            else None
        ),
    }


def _build_fixture_automated_gates(*, summary: JSONObject) -> JSONObject:
    total_checkpoints = _json_int(summary["total_checkpoints"])
    gates: JSONObject = {
        "has_checkpoints": total_checkpoints > 0,
        "no_disabled_source_violations": (
            _json_int(summary["disabled_source_violations"]) == 0
        ),
        "no_budget_violations": _json_int(summary["budget_violations"]) == 0,
        "no_invalid_recommendations": _json_int(summary["invalid_recommendations"]) == 0,
        "no_malformed_fixture_entries": (_json_int(summary["malformed_fixture_errors"]) == 0),
        "deterministic_baseline_expected_count_met": (
            _deterministic_baseline_expected_count_met(summary)
        ),
        "no_fallback_or_unavailable_recommendations": (
            _json_int(summary["fallback_recommendations"]) == 0
            and _json_int(summary["unavailable_recommendations"]) == 0
        ),
        "qualitative_rationale_present_everywhere": (
            total_checkpoints > 0
            and _json_int(summary["qualitative_rationale_present_count"]) == total_checkpoints
        ),
    }
    gates["all_passed"] = all(bool(value) for value in gates.values())
    return gates


def _build_directory_automated_gates(*, summary: JSONObject) -> JSONObject:
    total_checkpoints = _json_int(summary["total_checkpoints"])
    gates: JSONObject = {
        "minimum_fixture_coverage_met": _json_int(summary["fixture_count"])
        >= _MIN_FIXTURE_COUNT,
        "minimum_run_coverage_met": _json_int(summary["run_count"]) >= _MIN_RUN_COUNT,
        "no_disabled_source_violations": (
            _json_int(summary["disabled_source_violations"]) == 0
        ),
        "no_budget_violations": _json_int(summary["budget_violations"]) == 0,
        "no_invalid_recommendations": _json_int(summary["invalid_recommendations"]) == 0,
        "no_malformed_fixture_entries": (_json_int(summary["malformed_fixture_errors"]) == 0),
        "deterministic_baseline_expected_count_met": (
            _deterministic_baseline_expected_count_met(summary)
        ),
        "no_fallback_or_unavailable_recommendations": (
            _json_int(summary["fallback_recommendations"]) == 0
            and _json_int(summary["unavailable_recommendations"]) == 0
        ),
        "qualitative_rationale_present_everywhere": (
            total_checkpoints > 0
            and _json_int(summary["qualitative_rationale_present_count"]) == total_checkpoints
        ),
    }
    gates["all_passed"] = all(bool(value) for value in gates.values())
    return gates


def _build_phase2_run_summary(*, checkpoint_reports: list[JSONObject]) -> JSONObject:
    totals = _empty_phase2_totals()
    _accumulate_phase2_totals(totals=totals, checkpoint_reports=checkpoint_reports)
    return _build_phase2_summary(
        fixture_count=1,
        fixture_names=[],
        run_count=1,
        totals=totals,
    )


def _fixture_needs_priority_review(fixture_report: JSONObject) -> bool:
    automated_gates = _dict_value(fixture_report.get("automated_gates"))
    if automated_gates and not bool(automated_gates.get("all_passed")):
        return True
    return any(
        (
            checkpoint_report.get("action_match") is not True
            or checkpoint_report.get("source_match") is not True
        )
        and checkpoint_report.get("boundary_mismatch") is not True
        and checkpoint_report.get("source_improvement_candidate") is not True
        and checkpoint_report.get("closure_improvement_candidate") is not True
        for checkpoint_report in _checkpoint_reports_from_fixture(fixture_report)
    )


def _fixture_has_boundary_mismatch(fixture_report: JSONObject) -> bool:
    return any(
        checkpoint_report.get("boundary_mismatch") is True
        for checkpoint_report in _checkpoint_reports_from_fixture(fixture_report)
    )


def _fixture_has_source_improvement_candidate(fixture_report: JSONObject) -> bool:
    return any(
        checkpoint_report.get("source_improvement_candidate") is True
        for checkpoint_report in _checkpoint_reports_from_fixture(fixture_report)
    )


def _fixture_has_closure_improvement_candidate(fixture_report: JSONObject) -> bool:
    return any(
        checkpoint_report.get("closure_improvement_candidate") is True
        for checkpoint_report in _checkpoint_reports_from_fixture(fixture_report)
    )


def _planner_telemetry_payload(*, result: object) -> JSONObject:
    telemetry = getattr(result, "telemetry", None)
    if telemetry is None:
        return {}
    return {
        "status": getattr(telemetry, "status", "unavailable"),
        "model_terminal_count": getattr(telemetry, "model_terminal_count", 0),
        "prompt_tokens": getattr(telemetry, "prompt_tokens", None),
        "completion_tokens": getattr(telemetry, "completion_tokens", None),
        "total_tokens": getattr(telemetry, "total_tokens", None),
        "cost_usd": getattr(telemetry, "cost_usd", None),
        "latency_seconds": getattr(telemetry, "latency_seconds", None),
        "tool_call_count": getattr(telemetry, "tool_call_count", 0),
    }


def _planner_telemetry_dict(
    *,
    planner_payload: JSONObject,
    metadata: JSONObject,
) -> JSONObject:
    telemetry = planner_payload.get("telemetry")
    if isinstance(telemetry, dict):
        return dict(telemetry)
    metadata_telemetry = metadata.get("telemetry")
    if isinstance(metadata_telemetry, dict):
        return dict(metadata_telemetry)
    return {}


def _build_phase2_cost_tracking(*, summary: JSONObject) -> JSONObject:
    total_checkpoints = _json_int(summary.get("total_checkpoints"))
    cost_available_checkpoints = _json_int(summary.get("cost_available_checkpoints"))
    zero_cost_with_tokens_checkpoints = _json_int(
        summary.get("zero_cost_with_tokens_checkpoints", 0),
    )
    token_available_checkpoints = _json_int(summary.get("token_available_checkpoints"))
    latency_available_checkpoints = _json_int(
        summary.get("latency_available_checkpoints", 0),
    )
    telemetry_available_checkpoints = _json_int(
        summary.get("telemetry_available_checkpoints", 0),
    )
    deterministic_baseline_run_count = _json_int(
        summary.get("deterministic_baseline_run_count", 0),
    )
    deterministic_baseline_expected_run_count = _json_int(
        summary.get(
            "deterministic_baseline_expected_run_count",
            deterministic_baseline_run_count,
        ),
    )
    deterministic_baseline_runs_with_cost = _json_int(
        summary.get("deterministic_baseline_runs_with_cost", 0),
    )
    planner_total_cost_usd = _optional_float(summary.get("planner_total_cost_usd"))
    deterministic_total_cost_usd = _optional_float(
        summary.get("deterministic_total_cost_usd"),
    )
    planner_cost_trusted = (
        total_checkpoints > 0
        and cost_available_checkpoints == total_checkpoints
        and token_available_checkpoints == total_checkpoints
        and latency_available_checkpoints == total_checkpoints
    )
    status = "unavailable"
    deterministic_baseline_status = "unavailable"
    notes = "Planner telemetry is still missing, so cost review remains unavailable."
    if (
        total_checkpoints > 0
        and zero_cost_with_tokens_checkpoints == total_checkpoints
        and token_available_checkpoints == total_checkpoints
        and latency_available_checkpoints == total_checkpoints
    ):
        notes = (
            "Planner telemetry includes token and latency data for every checkpoint, "
            "but reported zero USD cost throughout. Treating planner cost as "
            "unavailable until provider billing telemetry is exposed in this path."
        )
    elif planner_cost_trusted:
        status = "available"
        notes = (
            "Planner telemetry is available for every checkpoint. Deterministic "
            "baseline cost instrumentation is still pending, so the cost gate is "
            "reported but not enforced yet."
        )
    elif (
        telemetry_available_checkpoints > 0
        or cost_available_checkpoints > 0
        or zero_cost_with_tokens_checkpoints > 0
        or token_available_checkpoints > 0
        or latency_available_checkpoints > 0
    ):
        status = "partial"
        notes = (
            "Planner telemetry is available for some checkpoints, but coverage is "
            "not complete enough to enforce a cost gate yet."
        )
    if (
        deterministic_baseline_expected_run_count > 0
        and deterministic_baseline_run_count
        == deterministic_baseline_expected_run_count
        and deterministic_baseline_runs_with_cost
        == deterministic_baseline_expected_run_count
    ):
        deterministic_baseline_status = "available"
    elif (
        deterministic_baseline_run_count > 0
        or deterministic_baseline_runs_with_cost > 0
    ):
        deterministic_baseline_status = "partial"

    evaluated = False
    gate_within_limit = None
    planner_vs_deterministic_cost_ratio = None
    if (
        planner_cost_trusted
        and deterministic_baseline_status == "available"
        and planner_total_cost_usd is not None
        and deterministic_total_cost_usd is not None
    ):
        evaluated = True
        if deterministic_total_cost_usd > 0:
            planner_vs_deterministic_cost_ratio = round(
                planner_total_cost_usd / deterministic_total_cost_usd,
                6,
            )
            gate_within_limit = (
                planner_total_cost_usd <= deterministic_total_cost_usd * 2.0
            )
            notes = (
                "Planner telemetry and deterministic baseline telemetry are both "
                "available, so the <=2x cost gate is computed from fixture "
                "baseline totals."
            )
        else:
            notes = (
                "Deterministic baseline telemetry is available, but its recorded "
                "cost is zero, so a planner-to-baseline ratio cannot be computed."
            )
    elif status == "available" and deterministic_baseline_status != "available":
        if (
            deterministic_baseline_expected_run_count > 0
            and deterministic_baseline_run_count
            == deterministic_baseline_expected_run_count
            and deterministic_baseline_runs_with_cost == 0
        ):
            notes = (
                "Planner telemetry is available, and deterministic baseline "
                "telemetry is attached to every fixture run, but the baseline "
                "cost fields are still missing."
            )
        else:
            notes = (
                "Planner telemetry is available, but deterministic baseline "
                "telemetry has not been attached to every fixture run yet."
            )
    return {
        "status": status,
        "deterministic_baseline_status": deterministic_baseline_status,
        "evaluated": evaluated,
        "gate_within_limit": gate_within_limit,
        "total_checkpoints": total_checkpoints,
        "telemetry_available_checkpoints": telemetry_available_checkpoints,
        "cost_available_checkpoints": cost_available_checkpoints,
        "zero_cost_with_tokens_checkpoints": zero_cost_with_tokens_checkpoints,
        "token_available_checkpoints": token_available_checkpoints,
        "latency_available_checkpoints": latency_available_checkpoints,
        "planner_total_prompt_tokens": summary.get("planner_total_prompt_tokens"),
        "planner_total_completion_tokens": summary.get(
            "planner_total_completion_tokens",
        ),
        "planner_total_tokens": summary.get("planner_total_tokens"),
        "planner_total_cost_usd": (
            planner_total_cost_usd if cost_available_checkpoints > 0 else None
        ),
        "planner_total_latency_seconds": summary.get(
            "planner_total_latency_seconds",
        ),
        "deterministic_baseline_run_count": deterministic_baseline_run_count,
        "deterministic_baseline_expected_run_count": (
            deterministic_baseline_expected_run_count
        ),
        "deterministic_baseline_runs_with_cost": (
            deterministic_baseline_runs_with_cost
        ),
        "deterministic_total_prompt_tokens": summary.get(
            "deterministic_total_prompt_tokens",
        ),
        "deterministic_total_completion_tokens": summary.get(
            "deterministic_total_completion_tokens",
        ),
        "deterministic_total_tokens": summary.get("deterministic_total_tokens"),
        "deterministic_total_cost_usd": deterministic_total_cost_usd,
        "deterministic_total_latency_seconds": summary.get(
            "deterministic_total_latency_seconds",
        ),
        "planner_vs_deterministic_cost_ratio": planner_vs_deterministic_cost_ratio,
        "notes": notes,
    }


def _planner_state_for_action(action_type: object) -> str:
    if not isinstance(action_type, str):
        return "missing"
    try:
        action_enum = ResearchOrchestratorActionType(action_type)
    except ValueError:
        return "not_allowlisted"
    for spec in orchestrator_action_registry():
        if spec.action_type == action_enum:
            return spec.planner_state
    return "not_allowlisted"


def _source_taxonomy_category(
    *,
    source_taxonomy: JSONObject,
    source_key: object,
) -> str | None:
    if not isinstance(source_key, str) or not source_key.strip():
        return None
    normalized_source_key = source_key.strip()
    for category in ("live_evidence", "context_only", "grounding", "reserved"):
        if normalized_source_key in _string_list(source_taxonomy.get(category)):
            return category
    return "unclassified"


def _fixture_report_stem(fixture_name: str) -> str:
    normalized = _FIXTURE_REPORT_STEM_PATTERN.sub("_", fixture_name.lower()).strip("_")
    return normalized or "fixture"


def _fixture_name_from_malformed_path(fixture_path: Path) -> str:
    normalized = fixture_path.stem.replace("-", "_").upper()
    return normalized or "UNKNOWN"


def _increment_total(totals: JSONObject, total_key: str) -> None:
    totals[total_key] = _json_int(totals[total_key]) + 1


def _increment_total_if_true(
    *,
    totals: JSONObject,
    checkpoint_report: JSONObject,
    checkpoint_key: str,
    total_key: str,
) -> None:
    if checkpoint_report.get(checkpoint_key) is True:
        _increment_total(totals, total_key)


def _safe_rate(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(count / total, 4)


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
    "DEFAULT_PHASE2_SHADOW_FIXTURE_DIR",
    "Phase2MalformedFixtureError",
    "PHASE2_SHADOW_REPORT_VERSION",
    "evaluate_phase2_shadow_fixture_bundle",
    "evaluate_phase2_shadow_fixture_bundle_sync",
    "evaluate_phase2_shadow_fixture_directory",
    "evaluate_phase2_shadow_fixture_directory_sync",
    "load_phase2_shadow_fixture",
    "load_phase2_shadow_fixture_paths",
    "render_phase2_shadow_evaluation_markdown",
    "write_phase2_shadow_evaluation_report",
]
