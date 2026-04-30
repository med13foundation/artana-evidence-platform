"""Offline evaluation helpers for the Phase 2 shadow planner."""

from __future__ import annotations

import asyncio
import json
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
from artana_evidence_api.phase2_shadow_rendering import (
    render_phase2_shadow_evaluation_markdown,
    write_phase2_shadow_evaluation_report,
)
from artana_evidence_api.phase2_shadow_summary import (
    _accumulate_phase2_totals,
    _build_directory_automated_gates,
    _build_fixture_automated_gates,
    _build_phase2_cost_tracking,
    _build_phase2_run_summary,
    _build_phase2_summary,
    _checkpoint_reports_from_fixture,
    _checkpoint_reports_from_run,
    _deterministic_baseline_telemetry_payloads_from_fixtures,
    _deterministic_baseline_telemetry_payloads_from_reports,
    _dict_value,
    _empty_phase2_totals,
    _extract_deterministic_baseline_telemetry,
    _fixture_has_boundary_mismatch,
    _fixture_has_closure_improvement_candidate,
    _fixture_has_source_improvement_candidate,
    _fixture_name_from_malformed_path,
    _fixture_needs_priority_review,
    _fixture_report_stem,
    _json_int,
    _list_of_dicts,
    _maybe_string,
    _optional_float,
    _optional_int,
    _planner_state_for_action,
    _planner_telemetry_dict,
    _planner_telemetry_payload,
    _source_taxonomy_category,
    _string_list,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_object_or_empty,
)

PlannerCallable = Callable[[str, JSONObject, dict[str, bool]], Awaitable[JSONObject]]

DEFAULT_PHASE2_SHADOW_FIXTURE_DIR = (
    Path(__file__).resolve().parent / "tests" / "fixtures" / "shadow_planner"
)
PHASE2_SHADOW_REPORT_VERSION = "phase2-shadow-v10"


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
