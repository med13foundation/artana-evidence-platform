#!/usr/bin/env python3
"""Run one settings-path guarded source+chase canary cycle against live spaces."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from scripts.run_full_ai_real_space_canary import (  # noqa: E402
    LiveCanaryMode,
    _artifact_contents_by_key,
    _dict_value,
    _extract_guarded_payloads,
    _fetch_terminal_run_payloads,
    _int_value,
    _is_transient_request_error,
    _list_of_dicts,
    _load_sources_preferences,
    _maybe_string,
    _normalize_expected_run_count,
    _normalize_positive_float,
    _normalize_positive_int,
    _normalize_seed_terms,
    _normalize_space_ids,
    _poll_terminal_run,
    _proof_metrics,
    _readiness_metrics,
    _recover_queued_run_by_title,
    _request_json,
    _resolve_auth_headers,
    _resolve_path,
    _round_float,
    _run_runtime_seconds,
    _safe_filename,
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject


SettingsVerdict = Literal["pass", "hold", "rollback_required"]

_BASE_URL_ENV = "ARTANA_EVIDENCE_API_LIVE_BASE_URL"
_DEFAULT_BASE_URL = "http://localhost:8091"
_DEFAULT_REPORT_SUBDIR = "full_ai_orchestrator_settings_canary"
_DEFAULT_TIMEOUT_SECONDS = 60.0
_DEFAULT_POLL_TIMEOUT_SECONDS = 900.0
_DEFAULT_POLL_INTERVAL_SECONDS = 2.0
_DEFAULT_POLL_REQUEST_TIMEOUT_SECONDS = 15.0
_DEFAULT_POST_TERMINAL_FETCH_SECONDS = 20.0
_DEFAULT_GUARDED_PROOF_STABILIZATION_SECONDS = 20.0
_DEFAULT_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
_DEFAULT_TEST_USER_EMAIL = "researcher@example.com"
_DEFAULT_TEST_USER_ROLE = "researcher"
_HTTP_CREATED = 201
_SUCCESS_RUN_STATUS = "completed"
_EXPECTED_PROFILE = "guarded_source_chase"
_EXPECTED_PROFILE_SOURCE = "space_setting"
_GUARDED_READINESS_ARTIFACT_KEY = "full_ai_orchestrator_guarded_readiness"
_GUARDED_DECISION_PROOFS_ARTIFACT_KEY = "full_ai_orchestrator_guarded_decision_proofs"
_SETTINGS_MODE = LiveCanaryMode(
    key="guarded_source_chase",
    orchestration_mode="full_ai_guarded",
    guarded_rollout_profile=_EXPECTED_PROFILE,
    expects_guarded_artifacts=True,
)


@dataclass(frozen=True, slots=True)
class SettingsCanaryConfig:
    base_url: str
    auth_headers: dict[str, str]
    output_dir: Path
    canary_label: str | None
    expected_run_count: int | None
    space_ids: tuple[str, ...]
    objective: str
    seed_terms: tuple[str, ...]
    title: str | None
    max_depth: int
    max_hypotheses: int
    sources: dict[str, bool] | None
    poll_timeout_seconds: float
    poll_interval_seconds: float


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the settings-path canary cycle."""

    parser = argparse.ArgumentParser(
        description=(
            "Run normal research-init requests against spaces that are already "
            "configured for full_ai_guarded + guarded_source_chase."
        ),
    )
    parser.add_argument("--space-id", action="append", default=[])
    parser.add_argument("--space-ids", default="")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--seed-term", action="append", default=[])
    parser.add_argument("--seed-terms", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--sources-json", default="")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-hypotheses", type=int, default=20)
    parser.add_argument(
        "--poll-timeout-seconds", type=float, default=_DEFAULT_POLL_TIMEOUT_SECONDS
    )
    parser.add_argument(
        "--poll-interval-seconds", type=float, default=_DEFAULT_POLL_INTERVAL_SECONDS
    )
    parser.add_argument("--canary-label", default="")
    parser.add_argument("--expected-run-count", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--bearer-token", default="")
    parser.add_argument("--use-test-auth", action="store_true")
    parser.add_argument("--test-user-id", default=_DEFAULT_TEST_USER_ID)
    parser.add_argument("--test-user-email", default=_DEFAULT_TEST_USER_EMAIL)
    parser.add_argument("--test-user-role", default=_DEFAULT_TEST_USER_ROLE)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    args = parse_args(argv)
    config = _config_from_args(args)
    with httpx.Client(
        base_url=config.base_url,
        timeout=_DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        report = run_settings_canary_cycle(config=config, client=client)
    manifest = write_settings_canary_report(report=report, output_dir=config.output_dir)
    print(render_settings_canary_markdown(report))
    print()
    print(f"Summary JSON: {manifest['summary_json']}")
    print(f"Summary Markdown: {manifest['summary_markdown']}")
    verdict = _maybe_string(report.get("verdict"))
    return 2 if verdict == "rollback_required" else 0


def _config_from_args(args: argparse.Namespace) -> SettingsCanaryConfig:
    base_url = (
        _maybe_string(args.base_url)
        or _maybe_string(os.getenv(_BASE_URL_ENV))
        or _DEFAULT_BASE_URL
    )
    output_dir = (
        _resolve_path(args.output_dir)
        if args.output_dir is not None
        else (
            _REPO_ROOT
            / "reports"
            / _DEFAULT_REPORT_SUBDIR
            / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        )
    )
    return SettingsCanaryConfig(
        base_url=base_url,
        auth_headers=_resolve_auth_headers(args),
        output_dir=output_dir,
        canary_label=_maybe_string(args.canary_label),
        expected_run_count=_normalize_expected_run_count(args.expected_run_count),
        space_ids=_normalize_space_ids(
            explicit_space_ids=list(args.space_id),
            csv_space_ids=str(args.space_ids),
        ),
        objective=str(args.objective).strip(),
        seed_terms=_normalize_seed_terms(
            explicit_terms=list(args.seed_term),
            csv_terms=str(args.seed_terms),
        ),
        title=_maybe_string(args.title),
        max_depth=_normalize_positive_int(args.max_depth, name="max_depth"),
        max_hypotheses=_normalize_positive_int(
            args.max_hypotheses,
            name="max_hypotheses",
        ),
        sources=_load_sources_preferences(args.sources_json),
        poll_timeout_seconds=_normalize_positive_float(
            args.poll_timeout_seconds,
            name="poll_timeout_seconds",
        ),
        poll_interval_seconds=_normalize_positive_float(
            args.poll_interval_seconds,
            name="poll_interval_seconds",
        ),
    )


def run_settings_canary_cycle(
    *,
    config: SettingsCanaryConfig,
    client: httpx.Client,
) -> JSONObject:
    """Run one settings-path cycle and return the aggregate report."""

    run_reports = [
        _execute_settings_path_run(config=config, client=client, space_id=space_id)
        for space_id in config.space_ids
    ]
    return build_settings_canary_report(
        config=config,
        requested_run_count=len(config.space_ids),
        runs=run_reports,
    )


def _execute_settings_path_run(
    *,
    config: SettingsCanaryConfig,
    client: httpx.Client,
    space_id: str,
) -> JSONObject:
    started_at = time.perf_counter()
    request_started_at = datetime.now(UTC)
    request_payload = _settings_research_init_request_payload(config=config)
    request_timeout_seconds = _request_timeout_seconds(config)
    errors: list[str] = []
    queued_response: JSONObject | None = None
    run_payload: JSONObject | None = None
    progress_payload: JSONObject | None = None
    workspace_payload: JSONObject | None = None
    artifacts_payload: JSONObject | None = None
    run_id: str | None = None
    timed_out = False
    completed_during_timeout_grace = False

    try:
        try:
            queued_response = _request_json(
                client=client,
                method="POST",
                path=f"/v1/spaces/{space_id}/research-init",
                headers=config.auth_headers,
                json_body=request_payload,
                acceptable_statuses=(_HTTP_CREATED,),
                timeout_seconds=request_timeout_seconds,
            )
            run_info = _dict_value(queued_response.get("run"))
            run_id = _required_string(run_info, "id", "queued response run")
        except httpx.TimeoutException:
            recovered_run = _recover_queued_run_by_title(
                client=client,
                headers=config.auth_headers,
                space_id=space_id,
                title=_required_string(
                    request_payload, "title", "research-init request"
                ),
                started_at=request_started_at,
                timeout_seconds=request_timeout_seconds,
                interval_seconds=config.poll_interval_seconds,
            )
            if recovered_run is None:
                raise
            run_id = _required_string(recovered_run, "id", "recovered queued run")
            queued_response = {"run": recovered_run}

        run_payload, progress_payload, timed_out, completed_during_timeout_grace = (
            _poll_terminal_run(
                client=client,
                headers=config.auth_headers,
                space_id=space_id,
                run_id=run_id,
                timeout_seconds=config.poll_timeout_seconds,
                interval_seconds=config.poll_interval_seconds,
                request_timeout_seconds=request_timeout_seconds,
            )
        )
        if timed_out:
            errors.append(
                f"Run '{run_id}' did not reach a terminal state within "
                f"{config.poll_timeout_seconds:.1f}s.",
            )
        if (
            run_payload is not None
            and _maybe_string(run_payload.get("status")) != _SUCCESS_RUN_STATUS
        ):
            errors.append(
                f"Run '{run_id}' finished with status "
                f"'{_maybe_string(run_payload.get('status')) or 'unknown'}'.",
            )
        workspace_payload, artifacts_payload = _fetch_terminal_run_payloads(
            client=client,
            headers=config.auth_headers,
            space_id=space_id,
            run_id=run_id,
            interval_seconds=config.poll_interval_seconds,
            request_timeout_seconds=request_timeout_seconds,
            timeout_seconds=_DEFAULT_POST_TERMINAL_FETCH_SECONDS,
        )
        workspace_payload, artifacts_payload = _stabilize_settings_payloads(
            client=client,
            config=config,
            space_id=space_id,
            run_id=run_id,
            workspace_payload=workspace_payload,
            artifacts_payload=artifacts_payload,
            request_timeout_seconds=request_timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    runtime_seconds = _run_runtime_seconds(
        run_payload=run_payload,
        observed_elapsed_seconds=time.perf_counter() - started_at,
    )
    return _summarize_settings_run(
        space_id=space_id,
        run_id=run_id,
        request_payload=request_payload,
        queued_response=queued_response,
        run_payload=run_payload,
        progress_payload=progress_payload,
        workspace_payload=workspace_payload,
        artifacts_payload=artifacts_payload,
        runtime_seconds=runtime_seconds,
        timed_out=timed_out,
        completed_during_timeout_grace=completed_during_timeout_grace,
        errors=errors,
    )


def _stabilize_settings_payloads(  # noqa: PLR0913
    *,
    client: httpx.Client,
    config: SettingsCanaryConfig,
    space_id: str,
    run_id: str,
    workspace_payload: JSONObject,
    artifacts_payload: JSONObject,
    request_timeout_seconds: float,
) -> tuple[JSONObject, JSONObject]:
    latest_workspace = workspace_payload
    latest_artifacts = artifacts_payload
    deadline = time.monotonic() + _DEFAULT_GUARDED_PROOF_STABILIZATION_SECONDS
    while (
        _guarded_payloads_have_pending_proofs(
            workspace_payload=latest_workspace,
            artifacts_payload=latest_artifacts,
        )
        and time.monotonic() <= deadline
    ):
        time.sleep(config.poll_interval_seconds)
        try:
            latest_workspace, latest_artifacts = _fetch_terminal_run_payloads(
                client=client,
                headers=config.auth_headers,
                space_id=space_id,
                run_id=run_id,
                interval_seconds=config.poll_interval_seconds,
                request_timeout_seconds=request_timeout_seconds,
                timeout_seconds=config.poll_interval_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            if not _is_transient_request_error(exc):
                raise
    return latest_workspace, latest_artifacts


def _guarded_payloads_have_pending_proofs(
    *,
    workspace_payload: JSONObject,
    artifacts_payload: JSONObject,
) -> bool:
    workspace_snapshot = _dict_value(_dict_value(workspace_payload).get("snapshot"))
    artifacts = _artifact_contents_by_key(
        _list_of_dicts(_dict_value(artifacts_payload).get("artifacts")),
    )
    guarded_proofs = _dict_value(workspace_snapshot.get("guarded_decision_proofs"))
    if not guarded_proofs:
        guarded_proofs = _dict_value(
            artifacts.get(_GUARDED_DECISION_PROOFS_ARTIFACT_KEY)
        )
    return _int_value(guarded_proofs.get("pending_verification_count")) > 0


def _summarize_settings_run(  # noqa: PLR0913
    *,
    space_id: str,
    run_id: str | None,
    request_payload: JSONObject,
    queued_response: JSONObject | None,
    run_payload: JSONObject | None,
    progress_payload: JSONObject | None,
    workspace_payload: JSONObject | None,
    artifacts_payload: JSONObject | None,
    runtime_seconds: float | None,
    timed_out: bool,
    completed_during_timeout_grace: bool,
    errors: list[str],
) -> JSONObject:
    workspace_snapshot = _dict_value(_dict_value(workspace_payload).get("snapshot"))
    artifact_list = _list_of_dicts(_dict_value(artifacts_payload).get("artifacts"))
    artifacts_by_key = _artifact_contents_by_key(artifact_list)
    payload_errors = _payload_errors(
        run_payload=run_payload,
        workspace_payload=workspace_payload,
        workspace_snapshot=workspace_snapshot,
        artifacts_payload=artifacts_payload,
    )
    guarded_readiness, guarded_decision_proofs, proof_list, guarded_errors = (
        _extract_guarded_payloads(
            mode=_SETTINGS_MODE,
            workspace_snapshot=workspace_snapshot,
            artifacts_by_key=artifacts_by_key,
        )
    )
    payload_errors.extend(guarded_errors)
    proof_metrics = _proof_metrics(guarded_decision_proofs, proof_list)
    readiness_metrics = _readiness_metrics(guarded_readiness)
    final_run_status = _maybe_string(_dict_value(run_payload).get("status"))
    status = _result_status(
        final_run_status=final_run_status,
        timed_out=timed_out,
        errors=errors,
        payload_errors=payload_errors,
    )
    policy = _dict_value(_dict_value(guarded_readiness).get("policy"))
    return {
        "space_id": space_id,
        "label": _run_label_from_payload(
            request_payload=request_payload, run_payload=run_payload
        ),
        "run_id": run_id,
        "status": status,
        "run_status": final_run_status,
        "timed_out": timed_out,
        "completed_during_timeout_grace": completed_during_timeout_grace,
        "queued_response_present": queued_response is not None,
        "readiness_status": _maybe_string(
            readiness_metrics.get("guarded_readiness_status")
        ),
        "guarded_rollout_profile": (
            _maybe_string(workspace_snapshot.get("guarded_rollout_profile"))
            or _maybe_string(policy.get("profile"))
        ),
        "guarded_rollout_profile_source": (
            _maybe_string(workspace_snapshot.get("guarded_rollout_profile_source"))
            or _maybe_string(policy.get("profile_source"))
        ),
        "profile_authority_exercised": readiness_metrics.get(
            "profile_authority_exercised"
        ),
        "source_selection_interventions": _int_value(
            readiness_metrics.get("source_selection_intervention_count"),
        ),
        "chase_or_stop_interventions": _int_value(
            readiness_metrics.get("chase_or_stop_intervention_count"),
        ),
        "proof_count": _int_value(proof_metrics.get("proof_count")),
        "proofs_verified": _int_value(proof_metrics.get("verified_count")),
        "proof_verification_failures": _int_value(
            proof_metrics.get("verification_failed_count"),
        ),
        "pending_proof_verifications": _int_value(
            proof_metrics.get("pending_verification_count"),
        ),
        "invalid_outputs": _int_value(proof_metrics.get("invalid_output_count")),
        "fallback_outputs": _int_value(proof_metrics.get("fallback_count")),
        "budget_violations": _int_value(proof_metrics.get("budget_violation_count")),
        "policy_violations": _dict_value(
            proof_metrics.get("source_policy_violation_counts"),
        ),
        "brief_present": bool(
            _maybe_string(workspace_snapshot.get("brief_result_key"))
            or _dict_value(workspace_snapshot.get("brief_metadata"))
        ),
        "runtime_seconds": _round_float(runtime_seconds),
        "progress_status": _maybe_string(_dict_value(progress_payload).get("status")),
        "progress_phase": _maybe_string(_dict_value(progress_payload).get("phase")),
        "payload_status": "valid" if not payload_errors else "malformed",
        "errors": [*errors, *payload_errors],
        "request_payload": request_payload,
    }


def build_settings_canary_report(
    *,
    config: SettingsCanaryConfig,
    requested_run_count: int,
    runs: Sequence[JSONObject],
) -> JSONObject:
    """Build the operator-facing settings-path report."""

    run_list = [dict(run) for run in runs]
    policy = _sum_policy_violations(run_list)
    summary = {
        "completed_runs": sum(
            1 for run in run_list if _maybe_string(run.get("status")) == "completed"
        ),
        "failed_runs": sum(
            1
            for run in run_list
            if _maybe_string(run.get("status")) not in {None, "completed"}
        ),
        "timed_out_runs": sum(1 for run in run_list if run.get("timed_out") is True),
        "source_selection_interventions": sum(
            _int_value(run.get("source_selection_interventions")) for run in run_list
        ),
        "chase_or_stop_interventions": sum(
            _int_value(run.get("chase_or_stop_interventions")) for run in run_list
        ),
        "authority_exercised_runs": sum(
            1 for run in run_list if run.get("profile_authority_exercised") is True
        ),
        "proofs_verified": sum(
            _int_value(run.get("proofs_verified")) for run in run_list
        ),
        "proof_verification_failures": sum(
            _int_value(run.get("proof_verification_failures")) for run in run_list
        ),
        "pending_proof_verifications": sum(
            _int_value(run.get("pending_proof_verifications")) for run in run_list
        ),
        "invalid_outputs": sum(
            _int_value(run.get("invalid_outputs")) for run in run_list
        ),
        "fallback_outputs": sum(
            _int_value(run.get("fallback_outputs")) for run in run_list
        ),
        "budget_violations": sum(
            _int_value(run.get("budget_violations")) for run in run_list
        ),
        "source_policy_violations": policy,
    }
    verdict, reasons = _settings_verdict(
        requested_run_count=requested_run_count,
        expected_run_count=config.expected_run_count,
        runs=run_list,
        summary=summary,
    )
    return {
        "report_name": "full_ai_orchestrator_settings_canary",
        "report_type": "settings_enabled_widened_canary",
        "created_at": datetime.now(UTC).isoformat(),
        "base_url": config.base_url,
        "canary_label": config.canary_label,
        "expected_run_count": config.expected_run_count,
        "requested_run_count": requested_run_count,
        "actual_run_count": sum(
            1 for run in run_list if _maybe_string(run.get("run_id")) is not None
        ),
        "objective": config.objective,
        "seed_terms": list(config.seed_terms),
        "space_ids": list(config.space_ids),
        "verdict": verdict,
        "reasons": reasons,
        **summary,
        "runs": run_list,
    }


def render_settings_canary_markdown(report: JSONObject) -> str:
    """Render the settings-path report as compact Markdown."""

    policy = _dict_value(report.get("source_policy_violations"))
    lines = [
        "# Full AI Orchestrator Settings Canary Cycle",
        "",
        f"- Verdict: `{_maybe_string(report.get('verdict')) or 'unknown'}`",
        f"- Requested runs: `{_int_value(report.get('requested_run_count'))}`",
        f"- Actual runs: `{_int_value(report.get('actual_run_count'))}`",
        f"- Completed runs: `{_int_value(report.get('completed_runs'))}`",
        f"- Failed runs: `{_int_value(report.get('failed_runs'))}`",
        f"- Timed out runs: `{_int_value(report.get('timed_out_runs'))}`",
        f"- Source interventions: `{_int_value(report.get('source_selection_interventions'))}`",
        f"- Chase/stop interventions: `{_int_value(report.get('chase_or_stop_interventions'))}`",
        f"- Authority exercised runs: `{_int_value(report.get('authority_exercised_runs'))}`",
        f"- Proofs verified: `{_int_value(report.get('proofs_verified'))}`",
        f"- Proof verification failures: `{_int_value(report.get('proof_verification_failures'))}`",
        f"- Pending proof verifications: `{_int_value(report.get('pending_proof_verifications'))}`",
        f"- Invalid outputs: `{_int_value(report.get('invalid_outputs'))}`",
        f"- Fallback outputs: `{_int_value(report.get('fallback_outputs'))}`",
        f"- Budget violations: `{_int_value(report.get('budget_violations'))}`",
        "- Source-policy violations: "
        f"`disabled={_int_value(policy.get('disabled'))}, "
        f"reserved={_int_value(policy.get('reserved'))}, "
        f"context_only={_int_value(policy.get('context_only'))}, "
        f"grounding={_int_value(policy.get('grounding'))}`",
    ]
    reasons = _string_list(report.get("reasons"))
    if reasons:
        lines.extend(["", "## Reasons", ""])
        lines.extend(f"- {reason}" for reason in reasons)
    lines.extend(["", "## Runs", ""])
    for run in _list_of_dicts(report.get("runs")):
        lines.append(
            "- "
            f"`{_maybe_string(run.get('label')) or _maybe_string(run.get('space_id')) or 'unknown'}`: "
            f"run `{_maybe_string(run.get('run_id')) or 'none'}`, "
            f"status `{_maybe_string(run.get('status')) or 'unknown'}`, "
            f"readiness `{_maybe_string(run.get('readiness_status')) or 'unknown'}`, "
            f"profile `{_maybe_string(run.get('guarded_rollout_profile')) or 'unknown'}`, "
            f"profile source `{_maybe_string(run.get('guarded_rollout_profile_source')) or 'unknown'}`, "
            f"source interventions `{_int_value(run.get('source_selection_interventions'))}`, "
            f"chase/stop interventions `{_int_value(run.get('chase_or_stop_interventions'))}`, "
            f"authority `{run.get('profile_authority_exercised')}`"
        )
    return "\n".join(lines)


def write_settings_canary_report(
    *,
    report: JSONObject,
    output_dir: Path,
) -> dict[str, str]:
    """Write JSON and Markdown report files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    for run in _list_of_dicts(report.get("runs")):
        run_id = _maybe_string(run.get("run_id")) or "run"
        label = (
            _maybe_string(run.get("label"))
            or _maybe_string(run.get("space_id"))
            or "space"
        )
        (
            runs_dir / f"{_safe_filename(label)}_{_safe_filename(run_id)}.json"
        ).write_text(
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
        render_settings_canary_markdown(report) + "\n",
        encoding="utf-8",
    )
    return {
        "summary_json": str(summary_json),
        "summary_markdown": str(summary_markdown),
    }


def _settings_research_init_request_payload(
    *,
    config: SettingsCanaryConfig,
) -> JSONObject:
    payload: JSONObject = {
        "objective": config.objective,
        "seed_terms": list(config.seed_terms),
        "title": config.title or config.canary_label or "Settings Canary Cycle",
        "sources": dict(config.sources) if config.sources is not None else None,
        "max_depth": config.max_depth,
        "max_hypotheses": config.max_hypotheses,
    }
    return {key: value for key, value in payload.items() if value is not None}


def _settings_verdict(
    *,
    requested_run_count: int,
    expected_run_count: int | None,
    runs: Sequence[JSONObject],
    summary: JSONObject,
) -> tuple[SettingsVerdict, list[str]]:
    rollback_reasons = _settings_rollback_reasons(runs=runs, summary=summary)
    hold_reasons = _settings_hold_reasons(
        requested_run_count=requested_run_count,
        expected_run_count=expected_run_count,
        runs=runs,
        summary=summary,
    )
    if rollback_reasons:
        return "rollback_required", rollback_reasons
    if hold_reasons:
        return "hold", hold_reasons
    return "pass", []


def _settings_rollback_reasons(
    *,
    runs: Sequence[JSONObject],
    summary: JSONObject,
) -> list[str]:
    reasons: list[str] = []
    if _int_value(summary.get("failed_runs")):
        reasons.append("one or more settings-path runs did not complete")
    if _int_value(summary.get("timed_out_runs")):
        reasons.append("one or more settings-path runs timed out")
    if any(_maybe_string(run.get("payload_status")) == "malformed" for run in runs):
        reasons.append(
            "one or more settings-path runs returned malformed guarded payloads"
        )
    if any(
        _maybe_string(run.get("guarded_rollout_profile")) != _EXPECTED_PROFILE
        or _maybe_string(run.get("guarded_rollout_profile_source"))
        != _EXPECTED_PROFILE_SOURCE
        for run in runs
    ):
        reasons.append(
            "one or more runs were not guarded_source_chase from space settings"
        )
    if _int_value(summary.get("proof_verification_failures")):
        reasons.append("one or more proof receipts failed verification")
    if _int_value(summary.get("pending_proof_verifications")):
        reasons.append("one or more proof receipts were still pending")
    if _int_value(summary.get("invalid_outputs")):
        reasons.append("one or more planner outputs were invalid")
    if _int_value(summary.get("fallback_outputs")):
        reasons.append("one or more fallback outputs were present")
    if _int_value(summary.get("budget_violations")):
        reasons.append("one or more budget violations were present")
    policy = _dict_value(summary.get("source_policy_violations"))
    for category in ("disabled", "reserved", "context_only", "grounding"):
        if _int_value(policy.get(category)):
            reasons.append(f"{category} source-policy violations were present")
    return reasons


def _settings_hold_reasons(
    *,
    requested_run_count: int,
    expected_run_count: int | None,
    runs: Sequence[JSONObject],
    summary: JSONObject,
) -> list[str]:
    reasons: list[str] = []
    actual_run_count = sum(
        1 for run in runs if _maybe_string(run.get("run_id")) is not None
    )
    if actual_run_count < requested_run_count:
        reasons.append(
            f"requested {requested_run_count} runs but observed {actual_run_count}"
        )
    if expected_run_count is not None and actual_run_count < expected_run_count:
        reasons.append(
            f"expected {expected_run_count} runs but observed {actual_run_count}"
        )
    if _int_value(summary.get("source_selection_interventions")) == 0:
        reasons.append("no source-selection intervention was observed")
    if _int_value(summary.get("chase_or_stop_interventions")) == 0:
        reasons.append("no chase/stop intervention was observed")
    if _int_value(summary.get("authority_exercised_runs")) == 0:
        reasons.append("no settings-path run exercised guarded source+chase authority")
    return reasons


def _payload_errors(
    *,
    run_payload: JSONObject | None,
    workspace_payload: JSONObject | None,
    workspace_snapshot: JSONObject,
    artifacts_payload: JSONObject | None,
) -> list[str]:
    errors: list[str] = []
    if run_payload is None:
        errors.append("run payload missing")
    elif not run_payload:
        errors.append("run payload empty")
    if workspace_payload is None:
        errors.append("workspace payload missing")
    elif not workspace_snapshot:
        errors.append("workspace snapshot missing")
    if artifacts_payload is None:
        errors.append("artifacts payload missing")
    return errors


def _result_status(
    *,
    final_run_status: str | None,
    timed_out: bool,
    errors: Sequence[str],
    payload_errors: Sequence[str],
) -> str:
    if timed_out:
        return "timed_out"
    if final_run_status not in {None, _SUCCESS_RUN_STATUS} or errors:
        return "failed"
    if payload_errors:
        return "malformed"
    return "completed"


def _sum_policy_violations(runs: Sequence[JSONObject]) -> JSONObject:
    totals = {"disabled": 0, "reserved": 0, "context_only": 0, "grounding": 0}
    for run in runs:
        policy = _dict_value(run.get("policy_violations"))
        for key in totals:
            totals[key] += _int_value(policy.get(key))
    return totals


def _run_label_from_payload(
    *,
    request_payload: JSONObject,
    run_payload: JSONObject | None,
) -> str:
    run_title = _maybe_string(_dict_value(run_payload).get("title"))
    request_title = _maybe_string(request_payload.get("title"))
    return run_title or request_title or "settings-canary-run"


def _request_timeout_seconds(config: SettingsCanaryConfig) -> float:
    return max(
        1.0,
        min(config.poll_timeout_seconds, _DEFAULT_POLL_REQUEST_TIMEOUT_SECONDS),
    )


def _required_string(payload: JSONObject, key: str, label: str) -> str:
    value = _maybe_string(payload.get(key))
    if value is None:
        raise RuntimeError(f"{label} is missing required field '{key}'")
    return value


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip() != ""]


if __name__ == "__main__":
    raise SystemExit(main())
