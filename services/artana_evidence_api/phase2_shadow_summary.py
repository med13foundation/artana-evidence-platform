"""Summary aggregation helpers for Phase 2 shadow-planner evaluation."""

from __future__ import annotations

import re
from pathlib import Path

from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    orchestrator_action_registry,
)
from artana_evidence_api.types.common import (
    JSONObject,
    json_object,
    json_object_or_empty,
)

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




__all__ = [name for name in globals() if name.startswith("_")]
