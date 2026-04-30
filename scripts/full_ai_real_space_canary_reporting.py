"""Summary, gate, and Markdown helpers for the live full-AI canary script."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from scripts.full_ai_real_space_canary_utils import (
    _artifact_contents_by_key,
    _build_run_matrix,
    _dict_value,
    _display_float,
    _int_value,
    _is_int_value,
    _list_of_dicts,
    _maybe_string,
    _optional_float,
    _output_list,
    _proof_source_policy_violation_category,
    _research_init_request_payload,
    _round_float,
    _run_label,
    _safe_filename,
    _string_list,
    _working_state_snapshot,
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject

    from scripts.run_full_ai_real_space_canary import (
        LiveCanaryMode,
        RealSpaceCanaryConfig,
    )

CanaryVerdict = Literal["pass", "hold", "rollback_required"]
_MINIMUM_COHORT_SPACE_COUNT = 2
_SUCCESS_RUN_STATUS = "completed"
_GUARDED_READINESS_ARTIFACT_KEY = "full_ai_orchestrator_guarded_readiness"
_GUARDED_DECISION_PROOFS_ARTIFACT_KEY = "full_ai_orchestrator_guarded_decision_proofs"
_SOURCE_POLICY_CATEGORIES = (
    "disabled",
    "reserved",
    "context_only",
    "grounding",
)
_DEFAULT_REPORT_SUBDIR = "full_ai_orchestrator_real_space_canary"

def _summarize_live_run(  # noqa: PLR0913
    *,
    config: RealSpaceCanaryConfig,
    space_id: str,
    repeat_index: int,
    mode: LiveCanaryMode,
    queued_response: JSONObject | None,
    run_payload: JSONObject | None,
    progress_payload: JSONObject | None,
    workspace_payload: JSONObject | None,
    artifacts_payload: JSONObject | None,
    runtime_seconds: float | None,
    timeout_reached: bool,
    completed_during_timeout_grace: bool,
    errors: list[str],
    run_id: str | None,
) -> JSONObject:
    workspace_snapshot = _working_state_snapshot(workspace_payload)
    artifact_list = _output_list(artifacts_payload)
    artifacts_by_key = _artifact_contents_by_key(artifact_list)
    payload_errors: list[str] = []
    if run_payload is None:
        payload_errors.append("run payload missing")
    elif not run_payload:
        payload_errors.append("run payload empty")
    if workspace_payload is None:
        payload_errors.append("workspace payload missing")
    elif not workspace_snapshot:
        payload_errors.append("workspace snapshot missing")
    if artifacts_payload is None:
        payload_errors.append("artifacts payload missing")
    guarded_readiness, guarded_decision_proofs, proof_list, guarded_payload_errors = (
        _extract_guarded_payloads(
            mode=mode,
            workspace_snapshot=workspace_snapshot,
            artifacts_by_key=artifacts_by_key,
        )
    )
    payload_errors.extend(guarded_payload_errors)
    proof_metrics = _proof_metrics(guarded_decision_proofs, proof_list)
    readiness_metrics = _readiness_metrics(guarded_readiness)
    final_run_status = _maybe_string(_dict_value(run_payload).get("status"))
    result_status = "completed"
    if timeout_reached:
        result_status = "timed_out"
    elif errors or final_run_status not in {None, _SUCCESS_RUN_STATUS}:
        result_status = "failed"
    elif payload_errors:
        result_status = "malformed"
    all_errors = [*errors, *payload_errors]
    per_run_report = {
        "space_id": space_id,
        "repeat_index": repeat_index,
        "requested_mode": mode.key,
        "requested_orchestration_mode": mode.orchestration_mode,
        "guarded_rollout_profile": mode.guarded_rollout_profile,
        "result_status": result_status,
        "run_id": run_id,
        "queued_response_present": queued_response is not None,
        "run_status": final_run_status,
        "progress_status": _maybe_string(_dict_value(progress_payload).get("status")),
        "progress_phase": _maybe_string(_dict_value(progress_payload).get("phase")),
        "progress_message": _maybe_string(_dict_value(progress_payload).get("message")),
        "progress_percent": _optional_float(
            _dict_value(progress_payload).get("progress_percent"),
        ),
        "resume_point": _maybe_string(
            _dict_value(progress_payload).get("resume_point")
        ),
        "runtime_seconds": _round_float(runtime_seconds),
        "timeout_reached": timeout_reached,
        "completed_during_timeout_grace": completed_during_timeout_grace,
        "workspace_present": workspace_payload is not None,
        "artifact_count": len(artifact_list),
        "payload_status": "valid" if not payload_errors else "malformed",
        "guarded_readiness_present": guarded_readiness is not None,
        "guarded_decision_proofs_present": guarded_decision_proofs is not None,
        "proof_receipts_present_and_verified": (
            proof_metrics["proof_summary_present"]
            and proof_metrics["proof_count"] > 0
            and proof_metrics["blocked_count"] == 0
            and proof_metrics["ignored_count"] == 0
            and proof_metrics["verification_failed_count"] == 0
            and proof_metrics["pending_verification_count"] == 0
        ),
        "errors": all_errors,
        "request_payload": _research_init_request_payload(
            config=config,
            mode=mode,
            repeat_index=repeat_index,
        ),
        "run": run_payload,
        "progress": progress_payload,
        "workspace": workspace_payload,
        "artifacts": artifact_list,
        "guarded_readiness": guarded_readiness,
        "guarded_decision_proofs": guarded_decision_proofs,
    }
    per_run_report.update(proof_metrics)
    per_run_report.update(readiness_metrics)
    return per_run_report


def _extract_guarded_payloads(  # noqa: PLR0912
    *,
    mode: LiveCanaryMode,
    workspace_snapshot: JSONObject,
    artifacts_by_key: dict[str, JSONObject],
) -> tuple[JSONObject | None, JSONObject | None, list[JSONObject], list[str]]:
    errors: list[str] = []
    guarded_readiness = _dict_value(workspace_snapshot.get("guarded_readiness"))
    if not guarded_readiness:
        guarded_readiness = _dict_value(
            artifacts_by_key.get(_GUARDED_READINESS_ARTIFACT_KEY),
        )
    guarded_decision_proofs = _dict_value(
        workspace_snapshot.get("guarded_decision_proofs"),
    )
    if not guarded_decision_proofs:
        guarded_decision_proofs = _dict_value(
            artifacts_by_key.get(_GUARDED_DECISION_PROOFS_ARTIFACT_KEY),
        )
    proof_list = _list_of_dicts(guarded_decision_proofs.get("proofs"))

    if not mode.expects_guarded_artifacts:
        return (
            guarded_readiness or None,
            guarded_decision_proofs or None,
            proof_list,
            errors,
        )

    if not guarded_readiness:
        errors.append("guarded_readiness missing from guarded run payloads")
    else:
        if _maybe_string(guarded_readiness.get("status")) is None:
            errors.append("guarded_readiness.status missing")
        intervention_counts = _dict_value(guarded_readiness.get("intervention_counts"))
        if not intervention_counts:
            errors.append("guarded_readiness.intervention_counts missing")
        else:
            for key in ("source_selection", "chase_or_stop", "brief_generation"):
                if not _is_int_value(intervention_counts.get(key)):
                    errors.append(
                        f"guarded_readiness.intervention_counts.{key} missing",
                    )
        if mode.key == "guarded_source_chase" and not isinstance(
            guarded_readiness.get("profile_authority_exercised"),
            bool,
        ):
            errors.append(
                "guarded_readiness.profile_authority_exercised missing for guarded_source_chase",
            )

    if not guarded_decision_proofs:
        errors.append("guarded_decision_proofs missing from guarded run payloads")
    else:
        required_keys = (
            "proof_count",
            "allowed_count",
            "blocked_count",
            "ignored_count",
            "verified_count",
            "verification_failed_count",
            "pending_verification_count",
        )
        for key in required_keys:
            if not _is_int_value(guarded_decision_proofs.get(key)):
                errors.append(f"guarded_decision_proofs.{key} missing")
        if not isinstance(guarded_decision_proofs.get("proofs"), list):
            errors.append("guarded_decision_proofs.proofs missing")

    return (
        guarded_readiness or None,
        guarded_decision_proofs or None,
        proof_list,
        errors,
    )


def _proof_metrics(
    guarded_decision_proofs: JSONObject | None,
    proof_list: list[JSONObject],
) -> JSONObject:
    violation_counts: dict[str, int] = {
        "disabled": 0,
        "reserved": 0,
        "context_only": 0,
        "grounding": 0,
    }
    invalid_output_count = 0
    fallback_count = 0
    budget_violation_count = 0
    for proof in proof_list:
        if _maybe_string(proof.get("validation_error")) is not None or _maybe_string(
            proof.get("planner_status"),
        ) in {"failed", "invalid"}:
            invalid_output_count += 1
        if proof.get("used_fallback") is True:
            fallback_count += 1
        if proof.get("budget_violation") is True:
            budget_violation_count += 1
        category = _proof_source_policy_violation_category(proof)
        if category is not None:
            violation_counts[category] += 1
    proof_summary = guarded_decision_proofs or {}
    return {
        "proof_summary_present": guarded_decision_proofs is not None,
        "proof_count": _int_value(proof_summary.get("proof_count")),
        "allowed_count": _int_value(proof_summary.get("allowed_count")),
        "blocked_count": _int_value(proof_summary.get("blocked_count")),
        "ignored_count": _int_value(proof_summary.get("ignored_count")),
        "verified_count": _int_value(proof_summary.get("verified_count")),
        "verification_failed_count": _int_value(
            proof_summary.get("verification_failed_count"),
        ),
        "pending_verification_count": _int_value(
            proof_summary.get("pending_verification_count"),
        ),
        "invalid_output_count": invalid_output_count,
        "fallback_count": fallback_count,
        "budget_violation_count": budget_violation_count,
        "disabled_source_violation_count": violation_counts["disabled"],
        "reserved_source_violation_count": violation_counts["reserved"],
        "context_only_source_violation_count": violation_counts["context_only"],
        "grounding_source_violation_count": violation_counts["grounding"],
        "source_policy_violation_counts": violation_counts,
    }


def _readiness_metrics(guarded_readiness: JSONObject | None) -> JSONObject:
    readiness = guarded_readiness or {}
    intervention_counts = _dict_value(readiness.get("intervention_counts"))
    return {
        "guarded_readiness_status": _maybe_string(readiness.get("status")),
        "profile_authority_exercised": (
            readiness.get("profile_authority_exercised")
            if isinstance(readiness.get("profile_authority_exercised"), bool)
            else None
        ),
        "source_selection_intervention_count": _int_value(
            intervention_counts.get("source_selection"),
        ),
        "chase_or_stop_intervention_count": _int_value(
            intervention_counts.get("chase_or_stop"),
        ),
        "brief_generation_intervention_count": _int_value(
            intervention_counts.get("brief_generation"),
        ),
    }


def _build_real_space_canary_report(
    *,
    config: RealSpaceCanaryConfig,
    requested_run_count: int,
    run_reports: list[JSONObject],
) -> JSONObject:
    queued_run_count = sum(
        1 for run in run_reports if _maybe_string(run.get("run_id")) is not None
    )
    completed_runs = [
        run for run in run_reports if run.get("result_status") == "completed"
    ]
    failed_runs = [run for run in run_reports if run.get("result_status") == "failed"]
    timed_out_runs = [
        run for run in run_reports if run.get("result_status") == "timed_out"
    ]
    malformed_runs = [
        run for run in run_reports if run.get("result_status") == "malformed"
    ]
    source_chase_runs = [
        run
        for run in run_reports
        if run.get("requested_mode") == "guarded_source_chase"
    ]
    clean_source_chase_runs = [
        run for run in source_chase_runs if _source_chase_run_is_clean(run)
    ]
    unclean_source_chase_runs = [
        _run_label(run)
        for run in source_chase_runs
        if not _source_chase_run_is_clean(run)
    ]
    total_runtime_seconds = sum(
        runtime
        for runtime in (
            _optional_float(run.get("runtime_seconds")) for run in run_reports
        )
        if runtime is not None
    )
    completed_during_timeout_grace_count = sum(
        1 for run in run_reports if run.get("completed_during_timeout_grace") is True
    )
    invalid_output_count = sum(
        _int_value(run.get("invalid_output_count")) for run in run_reports
    )
    fallback_count = sum(_int_value(run.get("fallback_count")) for run in run_reports)
    budget_violation_count = sum(
        _int_value(run.get("budget_violation_count")) for run in run_reports
    )
    disabled_source_violation_count = sum(
        _int_value(run.get("disabled_source_violation_count")) for run in run_reports
    )
    reserved_source_violation_count = sum(
        _int_value(run.get("reserved_source_violation_count")) for run in run_reports
    )
    context_only_source_violation_count = sum(
        _int_value(run.get("context_only_source_violation_count"))
        for run in run_reports
    )
    grounding_source_violation_count = sum(
        _int_value(run.get("grounding_source_violation_count")) for run in run_reports
    )
    source_selection_intervention_count = sum(
        _int_value(run.get("source_selection_intervention_count"))
        for run in source_chase_runs
    )
    chase_or_stop_intervention_count = sum(
        _int_value(run.get("chase_or_stop_intervention_count"))
        for run in source_chase_runs
    )
    profile_authority_exercised_count = sum(
        1 for run in source_chase_runs if run.get("profile_authority_exercised") is True
    )
    source_chase_missing_proof_runs = [
        _run_label(run)
        for run in source_chase_runs
        if run.get("proof_summary_present") is not True
        or run.get("guarded_decision_proofs_present") is not True
        or run.get("guarded_readiness_present") is not True
    ]
    source_chase_unverified_proof_runs = [
        _run_label(run)
        for run in source_chase_runs
        if run.get("proof_summary_present") is True
        and (
            _int_value(run.get("verification_failed_count")) > 0
            or _int_value(run.get("pending_verification_count")) > 0
        )
    ]
    run_matrix = _build_run_matrix(run_reports)
    space_rollout_summary = _build_space_rollout_summary(run_reports)
    automated_gates = {
        "no_failed_runs": len(failed_runs) == 0,
        "no_timed_out_runs": len(timed_out_runs) == 0,
        "no_malformed_runs": len(malformed_runs) == 0,
        "no_invalid_outputs": invalid_output_count == 0,
        "no_fallback_outputs": fallback_count == 0,
        "no_budget_violations": budget_violation_count == 0,
        "no_disabled_source_violations": disabled_source_violation_count == 0,
        "no_reserved_source_violations": reserved_source_violation_count == 0,
        "no_context_only_source_violations": context_only_source_violation_count == 0,
        "no_grounding_source_violations": grounding_source_violation_count == 0,
        "source_chase_proof_receipts_present": len(source_chase_missing_proof_runs)
        == 0,
        "source_chase_proof_receipts_verified": len(source_chase_unverified_proof_runs)
        == 0,
        "all_guarded_source_chase_runs_clean": len(unclean_source_chase_runs) == 0,
    }
    automated_gates["all_passed"] = all(automated_gates.values())
    summary: JSONObject = {
        "requested_run_count": requested_run_count,
        "actual_run_count": queued_run_count,
        "report_entry_count": len(run_reports),
        "space_count": len(config.space_ids),
        "repeat_count": config.repeat_count,
        "completed_run_count": len(completed_runs),
        "failed_run_count": len(failed_runs),
        "timed_out_run_count": len(timed_out_runs),
        "malformed_run_count": len(malformed_runs),
        "timed_out_runs": [_run_label(run) for run in timed_out_runs],
        "failed_runs": [_run_label(run) for run in failed_runs],
        "malformed_runs": [_run_label(run) for run in malformed_runs],
        "source_selection_intervention_count": source_selection_intervention_count,
        "chase_or_stop_intervention_count": chase_or_stop_intervention_count,
        "profile_authority_exercised_count": profile_authority_exercised_count,
        "clean_source_chase_run_count": len(clean_source_chase_runs),
        "unclean_source_chase_runs": unclean_source_chase_runs,
        "invalid_output_count": invalid_output_count,
        "fallback_count": fallback_count,
        "budget_violation_count": budget_violation_count,
        "disabled_source_violation_count": disabled_source_violation_count,
        "reserved_source_violation_count": reserved_source_violation_count,
        "context_only_source_violation_count": context_only_source_violation_count,
        "grounding_source_violation_count": grounding_source_violation_count,
        "source_chase_missing_proof_runs": source_chase_missing_proof_runs,
        "source_chase_unverified_proof_runs": source_chase_unverified_proof_runs,
        "total_runtime_seconds": _round_float(total_runtime_seconds),
        "average_runtime_seconds": _round_float(
            total_runtime_seconds / len(run_reports) if run_reports else None,
        ),
        "completed_during_timeout_grace_count": completed_during_timeout_grace_count,
        "run_matrix": run_matrix,
        "space_rollout_summary": space_rollout_summary,
    }
    report: JSONObject = {
        "report_name": "full_ai_orchestrator_real_space_canary",
        "report_mode": config.report_mode,
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": config.base_url,
        "canary_label": config.canary_label,
        "expected_run_count": config.expected_run_count,
        "objective": config.objective,
        "seed_terms": list(config.seed_terms),
        "space_ids": list(config.space_ids),
        "summary": summary,
        "automated_gates": automated_gates,
        "all_passed": automated_gates["all_passed"],
        "runs": run_reports,
    }
    if config.report_mode == "canary":
        report["canary_gate"] = _build_canary_gate(
            summary=summary,
            runs=run_reports,
            expected_run_count=config.expected_run_count,
        )
    return report


def _build_space_rollout_summary(run_reports: list[JSONObject]) -> JSONObject:
    summary: dict[str, JSONObject] = {}
    for run in run_reports:
        space_id = _maybe_string(run.get("space_id")) or "unknown-space"
        space_summary = summary.setdefault(space_id, _empty_space_rollout_summary())
        _record_space_rollout_run(space_summary=space_summary, run=run)

    for space_summary in summary.values():
        _finalize_space_rollout_summary(space_summary)

    return summary


def _source_chase_run_is_clean(run: JSONObject) -> bool:
    return _space_rollout_run_is_clean(
        run=run,
        result_status=_maybe_string(run.get("result_status")),
    )


def _empty_space_rollout_summary() -> JSONObject:
    return {
        "requested_run_count": 0,
        "completed_run_count": 0,
        "failed_run_count": 0,
        "timed_out_run_count": 0,
        "malformed_run_count": 0,
        "guarded_source_chase_run_count": 0,
        "clean_guarded_source_chase_run_count": 0,
        "source_selection_intervention_count": 0,
        "chase_or_stop_intervention_count": 0,
        "profile_authority_exercised_count": 0,
        "source_intervention_observed": False,
        "chase_or_stop_intervention_observed": False,
        "profile_authority_exercised_observed": False,
        "space_verdict": "hold",
        "rollback_reasons": [],
        "hold_reasons": [],
    }


def _record_space_rollout_run(*, space_summary: JSONObject, run: JSONObject) -> None:
    space_summary["requested_run_count"] = (
        _int_value(space_summary.get("requested_run_count")) + 1
    )
    result_status = _maybe_string(run.get("result_status"))
    _increment_space_status_count(
        space_summary=space_summary, result_status=result_status
    )
    if run.get("requested_mode") != "guarded_source_chase":
        return

    space_summary["guarded_source_chase_run_count"] = (
        _int_value(space_summary.get("guarded_source_chase_run_count")) + 1
    )
    source_intervention_count = _int_value(
        run.get("source_selection_intervention_count")
    )
    chase_intervention_count = _int_value(run.get("chase_or_stop_intervention_count"))
    space_summary["source_selection_intervention_count"] = (
        _int_value(space_summary.get("source_selection_intervention_count"))
        + source_intervention_count
    )
    space_summary["chase_or_stop_intervention_count"] = (
        _int_value(space_summary.get("chase_or_stop_intervention_count"))
        + chase_intervention_count
    )
    if source_intervention_count > 0:
        space_summary["source_intervention_observed"] = True
    if chase_intervention_count > 0:
        space_summary["chase_or_stop_intervention_observed"] = True
    if run.get("profile_authority_exercised") is True:
        space_summary["profile_authority_exercised_observed"] = True
        space_summary["profile_authority_exercised_count"] = (
            _int_value(space_summary.get("profile_authority_exercised_count")) + 1
        )
    if _space_rollout_run_is_clean(run=run, result_status=result_status):
        space_summary["clean_guarded_source_chase_run_count"] = (
            _int_value(space_summary.get("clean_guarded_source_chase_run_count")) + 1
        )


def _increment_space_status_count(
    *,
    space_summary: JSONObject,
    result_status: str | None,
) -> None:
    field_by_status = {
        "completed": "completed_run_count",
        "failed": "failed_run_count",
        "timed_out": "timed_out_run_count",
        "malformed": "malformed_run_count",
    }
    field_name = field_by_status.get(result_status)
    if field_name is None:
        return
    space_summary[field_name] = _int_value(space_summary.get(field_name)) + 1


def _space_rollout_run_is_clean(*, run: JSONObject, result_status: str | None) -> bool:
    return (
        result_status == "completed"
        and run.get("proof_receipts_present_and_verified") is True
        and _int_value(run.get("invalid_output_count")) == 0
        and _int_value(run.get("fallback_count")) == 0
        and _int_value(run.get("budget_violation_count")) == 0
        and _int_value(run.get("disabled_source_violation_count")) == 0
        and _int_value(run.get("reserved_source_violation_count")) == 0
        and _int_value(run.get("context_only_source_violation_count")) == 0
        and _int_value(run.get("grounding_source_violation_count")) == 0
    )


def _finalize_space_rollout_summary(space_summary: JSONObject) -> None:
    rollback_reasons = _space_rollback_reasons(space_summary)
    hold_reasons = _space_hold_reasons(space_summary)
    verdict: CanaryVerdict
    if rollback_reasons:
        verdict = "rollback_required"
    elif hold_reasons:
        verdict = "hold"
    else:
        verdict = "pass"
    space_summary["space_verdict"] = verdict
    space_summary["rollback_reasons"] = rollback_reasons
    space_summary["hold_reasons"] = hold_reasons


def _space_rollback_reasons(space_summary: JSONObject) -> list[str]:
    reasons: list[str] = []
    if _int_value(space_summary.get("failed_run_count")) > 0:
        reasons.append("one or more runs failed")
    if _int_value(space_summary.get("timed_out_run_count")) > 0:
        reasons.append("one or more runs timed out")
    if _int_value(space_summary.get("malformed_run_count")) > 0:
        reasons.append("one or more runs returned malformed payloads")
    if (
        _int_value(space_summary.get("guarded_source_chase_run_count")) > 0
        and _int_value(space_summary.get("clean_guarded_source_chase_run_count")) == 0
    ):
        reasons.append("no clean guarded_source_chase run completed for this space")
    return reasons


def _space_hold_reasons(space_summary: JSONObject) -> list[str]:
    reasons: list[str] = []
    if _int_value(space_summary.get("guarded_source_chase_run_count")) == 0:
        reasons.append("no guarded_source_chase run was queued for this space")
    if space_summary.get("source_intervention_observed") is not True:
        reasons.append("no source-selection intervention was observed")
    if space_summary.get("chase_or_stop_intervention_observed") is not True:
        reasons.append("no chase/stop intervention was observed")
    if space_summary.get("profile_authority_exercised_observed") is not True:
        reasons.append("no guarded_source_chase run exercised authority")
    return reasons


def _build_canary_gate(
    *,
    summary: JSONObject,
    runs: list[JSONObject],
    expected_run_count: int | None,
) -> JSONObject:
    source_chase_runs = [
        run for run in runs if run.get("requested_mode") == "guarded_source_chase"
    ]
    rollback_reasons = _canary_rollback_reasons(summary)
    hold_reasons = _canary_hold_reasons(
        summary=summary,
        expected_run_count=expected_run_count,
    )
    space_rollout_summary = _dict_value(summary.get("space_rollout_summary"))
    distinct_space_count = len(space_rollout_summary)
    passing_spaces = _space_ids_for_verdict(space_rollout_summary, verdict="pass")
    held_spaces = _space_ids_for_verdict(space_rollout_summary, verdict="hold")
    rollback_spaces = _space_ids_for_verdict(
        space_rollout_summary,
        verdict="rollback_required",
    )
    verdict: CanaryVerdict
    note: str
    if rollback_reasons or rollback_spaces:
        verdict = "rollback_required"
        note = (
            rollback_reasons[0]
            if rollback_reasons
            else "one or more spaces failed guarded_source_chase cleanliness checks"
        )
    elif hold_reasons:
        verdict = "hold"
        note = hold_reasons[0]
    else:
        verdict = "pass"
        note = (
            "Real-space source+chase canary completed cleanly with exercised authority."
        )
    cohort_status: str
    operator_next_step: str
    if rollback_reasons or rollback_spaces:
        cohort_status = "rollback_required"
        operator_next_step = "Return affected spaces to deterministic mode and investigate the failed live canary."
    elif distinct_space_count < _MINIMUM_COHORT_SPACE_COUNT:
        cohort_status = "single_space_reference_only"
        operator_next_step = "Run the canary on additional ordinary low-risk spaces before any wider adoption review."
    elif held_spaces:
        cohort_status = "multi_space_partial"
        operator_next_step = "Keep collecting low-risk spaces until exercised authority appears cleanly beyond the supplemental reference."
    else:
        cohort_status = "multi_space_ready_for_review"
        operator_next_step = "Review the clean multi-space cohort and decide whether to widen guarded_source_chase cautiously."

    return {
        "verdict": verdict,
        "note": note,
        "rollback_reasons": rollback_reasons,
        "hold_reasons": hold_reasons,
        "source_chase_run_count": len(source_chase_runs),
        "distinct_space_count": distinct_space_count,
        "passing_spaces": passing_spaces,
        "held_spaces": held_spaces,
        "rollback_spaces": rollback_spaces,
        "cohort_status": cohort_status,
        "operator_next_step": operator_next_step,
        "profile_authority_exercised_count": _int_value(
            summary.get("profile_authority_exercised_count"),
        ),
        "source_selection_intervention_count": _int_value(
            summary.get("source_selection_intervention_count"),
        ),
        "chase_or_stop_intervention_count": _int_value(
            summary.get("chase_or_stop_intervention_count"),
        ),
    }


def _canary_rollback_reasons(summary: JSONObject) -> list[str]:
    reasons: list[str] = []
    if _string_list(summary.get("failed_runs")):
        reasons.append("one or more runs failed")
    if _string_list(summary.get("malformed_runs")):
        reasons.append("one or more runs returned malformed or incomplete payloads")
    if _string_list(summary.get("timed_out_runs")):
        reasons.append("one or more runs timed out")
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
    if _string_list(summary.get("source_chase_missing_proof_runs")):
        reasons.append("guarded_source_chase proof receipts were missing")
    if _string_list(summary.get("source_chase_unverified_proof_runs")):
        reasons.append("guarded_source_chase proof receipts were not fully verified")
    if _string_list(summary.get("unclean_source_chase_runs")):
        reasons.append("one or more guarded_source_chase runs were not clean")
    return reasons


def _canary_hold_reasons(
    *,
    summary: JSONObject,
    expected_run_count: int | None,
) -> list[str]:
    reasons: list[str] = []
    actual_run_count = _int_value(summary.get("actual_run_count"))
    if expected_run_count is not None and actual_run_count < expected_run_count:
        reasons.append(
            f"expected {expected_run_count} queued runs but observed {actual_run_count}",
        )
    if _int_value(summary.get("source_selection_intervention_count")) == 0:
        reasons.append("no source-selection intervention was observed")
    if _int_value(summary.get("chase_or_stop_intervention_count")) == 0:
        reasons.append("no chase/stop intervention was observed")
    if _int_value(summary.get("profile_authority_exercised_count")) == 0:
        reasons.append("no guarded_source_chase run exercised profile authority")
    return reasons


def _space_ids_for_verdict(
    space_rollout_summary: JSONObject,
    *,
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


def render_real_space_canary_markdown(report: JSONObject) -> str:
    """Render the real-space canary report as a compact markdown summary."""

    summary = _dict_value(report.get("summary"))
    canary_gate = _dict_value(report.get("canary_gate"))
    lines = [
        "# Real-Space Guarded Source+Chase Canary",
        "",
        f"- Report mode: `{_maybe_string(report.get('report_mode')) or 'unknown'}`",
        f"- Base URL: `{_maybe_string(report.get('base_url')) or 'unknown'}`",
        f"- Spaces: {', '.join(_string_list(report.get('space_ids'))) or 'none'}",
        f"- Requested runs: `{_int_value(summary.get('requested_run_count'))}`",
        f"- Queued runs: `{_int_value(summary.get('actual_run_count'))}`",
        f"- Completed runs: `{_int_value(summary.get('completed_run_count'))}`",
        f"- Failed runs: `{_int_value(summary.get('failed_run_count'))}`",
        f"- Timed out runs: `{_int_value(summary.get('timed_out_run_count'))}`",
        f"- Malformed runs: `{_int_value(summary.get('malformed_run_count'))}`",
        f"- Source interventions: `{_int_value(summary.get('source_selection_intervention_count'))}`",
        f"- Chase/stop interventions: `{_int_value(summary.get('chase_or_stop_intervention_count'))}`",
        f"- Authority exercised runs: `{_int_value(summary.get('profile_authority_exercised_count'))}`",
        f"- Invalid outputs: `{_int_value(summary.get('invalid_output_count'))}`",
        f"- Fallback outputs: `{_int_value(summary.get('fallback_count'))}`",
        f"- Grace completions: `{_int_value(summary.get('completed_during_timeout_grace_count'))}`",
        f"- Total runtime (s): `{_display_float(summary.get('total_runtime_seconds'))}`",
        f"- Average runtime (s): `{_display_float(summary.get('average_runtime_seconds'))}`",
    ]
    if canary_gate:
        lines.extend(
            [
                "",
                f"## Canary Verdict: `{_maybe_string(canary_gate.get('verdict')) or 'unknown'}`",
                "",
                _maybe_string(canary_gate.get("note")) or "No verdict note available.",
                "",
                f"- Cohort status: `{_maybe_string(canary_gate.get('cohort_status')) or 'unknown'}`",
                f"- Distinct spaces: `{_int_value(canary_gate.get('distinct_space_count'))}`",
            ],
        )
        rollback_reasons = _string_list(canary_gate.get("rollback_reasons"))
        hold_reasons = _string_list(canary_gate.get("hold_reasons"))
        if rollback_reasons:
            lines.extend(["", "### Rollback Reasons", ""])
            lines.extend(f"- {reason}" for reason in rollback_reasons)
        if hold_reasons:
            lines.extend(["", "### Hold Reasons", ""])
            lines.extend(f"- {reason}" for reason in hold_reasons)
        operator_next_step = _maybe_string(canary_gate.get("operator_next_step"))
        if operator_next_step is not None:
            lines.extend(["", "### Next Step", "", f"- {operator_next_step}"])

    run_matrix = _dict_value(summary.get("run_matrix"))
    if run_matrix:
        lines.extend(["", "## Run Matrix", ""])
        for space_id in sorted(run_matrix):
            lines.append(f"- `{space_id}`")
            mode_summary = _dict_value(run_matrix.get(space_id))
            for mode_key in (
                "full_ai_shadow",
                "guarded_dry_run",
                "guarded_source_chase",
            ):
                cell = _dict_value(mode_summary.get(mode_key))
                lines.append(
                    "  - "
                    f"`{mode_key}`: requested `{_int_value(cell.get('requested_count'))}`, "
                    f"completed `{_int_value(cell.get('completed_count'))}`, "
                    f"failed `{_int_value(cell.get('failed_count'))}`, "
                    f"statuses `{', '.join(_string_list(cell.get('statuses'))) or 'none'}`"
                )
    space_rollout_summary = _dict_value(summary.get("space_rollout_summary"))
    if space_rollout_summary:
        lines.extend(["", "## Space Rollout Summary", ""])
        for space_id in sorted(space_rollout_summary):
            space_summary = _dict_value(space_rollout_summary.get(space_id))
            lines.append(
                f"- `{space_id}`: verdict `{_maybe_string(space_summary.get('space_verdict')) or 'unknown'}`, "
                f"clean source+chase runs `{_int_value(space_summary.get('clean_guarded_source_chase_run_count'))}`, "
                f"source interventions `{_int_value(space_summary.get('source_selection_intervention_count'))}`, "
                f"chase/stop interventions `{_int_value(space_summary.get('chase_or_stop_intervention_count'))}`, "
                f"authority exercised `{_int_value(space_summary.get('profile_authority_exercised_count'))}`"
            )
    return "\n".join(lines)


def write_real_space_canary_report(
    *,
    report: JSONObject,
    output_dir: Path,
) -> dict[str, str]:
    """Write JSON and Markdown report files and return their paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    for run in _list_of_dicts(report.get("runs")):
        run_filename = f"{_safe_filename(_run_label(run)) or 'run'}.json"
        (runs_dir / run_filename).write_text(
            json.dumps(run, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    summary_json = output_dir / "summary.json"
    summary_markdown = output_dir / "summary.md"
    summary_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_markdown.write_text(
        render_real_space_canary_markdown(report) + "\n",
        encoding="utf-8",
    )
    return {
        "summary_json": str(summary_json),
        "summary_markdown": str(summary_markdown),
    }




__all__ = [
    "_build_real_space_canary_report",
    "_summarize_live_run",
    "render_real_space_canary_markdown",
    "write_real_space_canary_report",
]
