#!/usr/bin/env python3
"""Run a manual guarded source+chase canary against live research-init routes."""

from __future__ import annotations

import argparse
import json
import os
import re
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

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject

RunModeKey = Literal["full_ai_shadow", "guarded_dry_run", "guarded_source_chase"]
ReportMode = Literal["standard", "canary"]
CanaryVerdict = Literal["pass", "hold", "rollback_required"]

_BASE_URL_ENV = "ARTANA_EVIDENCE_API_LIVE_BASE_URL"
_API_KEY_ENV = "ARTANA_EVIDENCE_API_KEY"
_BEARER_TOKEN_ENV = "ARTANA_EVIDENCE_API_BEARER_TOKEN"
_DEFAULT_BASE_URL = "http://localhost:8091"
_DEFAULT_REPORT_SUBDIR = "full_ai_orchestrator_real_space_canary"
_DEFAULT_TIMEOUT_SECONDS = 60.0
_DEFAULT_POLL_TIMEOUT_SECONDS = 900.0
_DEFAULT_POLL_INTERVAL_SECONDS = 2.0
_DEFAULT_POLL_REQUEST_TIMEOUT_SECONDS = 15.0
_DEFAULT_TERMINAL_GRACE_SECONDS = 30.0
_DEFAULT_GUARDED_PROOF_STABILIZATION_SECONDS = 20.0
_DEFAULT_POST_TERMINAL_FETCH_SECONDS = 20.0
_DEFAULT_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
_DEFAULT_TEST_USER_EMAIL = "researcher@example.com"
_DEFAULT_TEST_USER_ROLE = "researcher"
_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_UNAUTHORIZED = 401
_HTTP_NOT_FOUND = 404
_MINIMUM_COHORT_SPACE_COUNT = 2
_FINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled", "canceled"})
_SUCCESS_RUN_STATUS = "completed"
_GUARDED_READINESS_ARTIFACT_KEY = "full_ai_orchestrator_guarded_readiness"
_GUARDED_DECISION_PROOFS_ARTIFACT_KEY = "full_ai_orchestrator_guarded_decision_proofs"
_SOURCE_POLICY_CATEGORIES = (
    "disabled",
    "reserved",
    "context_only",
    "grounding",
)
_RESERVED_SOURCE_KEYS = frozenset({"uniprot", "hgnc"})
_CONTEXT_ONLY_SOURCE_KEYS = frozenset({"pdf", "text"})
_GROUNDING_SOURCE_KEYS = frozenset({"mondo"})
_ACTION_DEFAULT_SOURCE_KEYS: dict[str, str] = {
    "QUERY_PUBMED": "pubmed",
    "INGEST_AND_EXTRACT_PUBMED": "pubmed",
    "REVIEW_PDF_WORKSET": "pdf",
    "REVIEW_TEXT_WORKSET": "text",
    "LOAD_MONDO_GROUNDING": "mondo",
    "RUN_UNIPROT_GROUNDING": "uniprot",
    "RUN_HGNC_GROUNDING": "hgnc",
}
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class LiveCanaryMode:
    key: RunModeKey
    orchestration_mode: str
    guarded_rollout_profile: str | None
    expects_guarded_artifacts: bool


@dataclass(frozen=True, slots=True)
class RealSpaceCanaryConfig:
    base_url: str
    auth_headers: dict[str, str]
    output_dir: Path
    report_mode: ReportMode
    canary_label: str | None
    expected_run_count: int | None
    space_ids: tuple[str, ...]
    objective: str
    seed_terms: tuple[str, ...]
    title: str | None
    max_depth: int
    max_hypotheses: int
    sources: dict[str, bool] | None
    repeat_count: int
    poll_timeout_seconds: float
    poll_interval_seconds: float


_MODE_SEQUENCE: tuple[LiveCanaryMode, ...] = (
    LiveCanaryMode(
        key="full_ai_shadow",
        orchestration_mode="full_ai_shadow",
        guarded_rollout_profile=None,
        expects_guarded_artifacts=False,
    ),
    LiveCanaryMode(
        key="guarded_dry_run",
        orchestration_mode="full_ai_guarded",
        guarded_rollout_profile="guarded_dry_run",
        expects_guarded_artifacts=True,
    ),
    LiveCanaryMode(
        key="guarded_source_chase",
        orchestration_mode="full_ai_guarded",
        guarded_rollout_profile="guarded_source_chase",
        expects_guarded_artifacts=True,
    ),
)


def _task_payload(payload: JSONObject | None) -> JSONObject:
    payload_dict = _dict_value(payload)
    return _dict_value(payload_dict.get("task") or payload_dict.get("run"))


def _working_state_snapshot(payload: JSONObject | None) -> JSONObject:
    payload_dict = _dict_value(payload)
    return _dict_value(
        payload_dict.get("working_state") or payload_dict.get("snapshot"),
    )


def _output_list(payload: JSONObject | None) -> list[JSONObject]:
    payload_dict = _dict_value(payload)
    outputs = payload_dict.get("outputs")
    if isinstance(outputs, list):
        return _list_of_dicts(outputs)
    return _list_of_dicts(payload_dict.get("artifacts"))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the live canary runner."""

    parser = argparse.ArgumentParser(
        description=(
            "Run a live real-space full-AI canary sequence against the "
            "research-init route and write operator-facing reports."
        ),
    )
    parser.add_argument(
        "--space-id",
        action="append",
        default=[],
        help="Research space ID. Repeat to run the same canary against multiple spaces.",
    )
    parser.add_argument(
        "--space-ids",
        default="",
        help="Optional comma-separated space IDs for cohort canaries.",
    )
    parser.add_argument(
        "--objective",
        required=True,
        help="Research-init objective used for each canary run.",
    )
    parser.add_argument(
        "--seed-term",
        action="append",
        default=[],
        help="Repeatable seed term for the real-space canary run.",
    )
    parser.add_argument(
        "--seed-terms",
        default="",
        help="Optional comma-separated seed terms.",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Optional base title for queued research-init runs.",
    )
    parser.add_argument(
        "--sources-json",
        default="",
        help=(
            "Optional inline JSON object or JSON file path for source preferences. "
            'Example: {"pubmed": true, "clinvar": true}'
        ),
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Research-init max depth override. Defaults to 2.",
    )
    parser.add_argument(
        "--max-hypotheses",
        type=int,
        default=20,
        help="Research-init max hypotheses override. Defaults to 20.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=1,
        help="Repeat the full shadow -> dry-run -> source+chase sequence this many times.",
    )
    parser.add_argument(
        "--poll-timeout-seconds",
        type=float,
        default=_DEFAULT_POLL_TIMEOUT_SECONDS,
        help="Maximum time to wait for one queued run. Defaults to 900 seconds.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=_DEFAULT_POLL_INTERVAL_SECONDS,
        help="Polling interval between run status checks. Defaults to 2 seconds.",
    )
    parser.add_argument(
        "--report-mode",
        choices=("standard", "canary"),
        default="canary",
        help="Report posture. Canary mode adds operator verdicts and gates.",
    )
    parser.add_argument(
        "--canary-label",
        default="",
        help="Optional human-readable label for the report.",
    )
    parser.add_argument(
        "--expected-run-count",
        type=int,
        default=None,
        help="Optional expected number of successfully queued runs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for generated reports. Defaults to "
            "reports/full_ai_orchestrator_real_space_canary/<timestamp>/."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="",
        help=(
            "Artana Evidence API base URL. Defaults to "
            f"{_DEFAULT_BASE_URL} or {_BASE_URL_ENV}."
        ),
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Artana API key to send as X-Artana-Key.",
    )
    parser.add_argument(
        "--bearer-token",
        default="",
        help="Bearer token to send as Authorization header.",
    )
    parser.add_argument(
        "--use-test-auth",
        action="store_true",
        help="Use local X-TEST-* auth headers when test auth is enabled on the service.",
    )
    parser.add_argument(
        "--test-user-id",
        default=_DEFAULT_TEST_USER_ID,
        help=f"User ID for --use-test-auth. Defaults to {_DEFAULT_TEST_USER_ID}.",
    )
    parser.add_argument(
        "--test-user-email",
        default=_DEFAULT_TEST_USER_EMAIL,
        help="Email for --use-test-auth.",
    )
    parser.add_argument(
        "--test-user-role",
        default=_DEFAULT_TEST_USER_ROLE,
        help="Role for --use-test-auth. Defaults to researcher.",
    )
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
        report = run_real_space_canary(config=config, client=client)
    manifest = write_real_space_canary_report(
        report=report, output_dir=config.output_dir
    )
    print(render_real_space_canary_markdown(report))
    print()
    print(f"Summary JSON: {manifest['summary_json']}")
    print(f"Summary Markdown: {manifest['summary_markdown']}")
    if config.report_mode == "canary":
        verdict = _maybe_string(_dict_value(report.get("canary_gate")).get("verdict"))
        return 0 if verdict == "pass" else 1
    return 0 if report.get("all_passed") is True else 1


def _config_from_args(args: argparse.Namespace) -> RealSpaceCanaryConfig:
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
    return RealSpaceCanaryConfig(
        base_url=base_url,
        auth_headers=_resolve_auth_headers(args),
        output_dir=output_dir,
        report_mode=_normalize_report_mode(args.report_mode),
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
        repeat_count=_normalize_positive_int(args.repeat_count, name="repeat_count"),
        poll_timeout_seconds=_normalize_positive_float(
            args.poll_timeout_seconds,
            name="poll_timeout_seconds",
        ),
        poll_interval_seconds=_normalize_positive_float(
            args.poll_interval_seconds,
            name="poll_interval_seconds",
        ),
    )


def run_real_space_canary(
    *,
    config: RealSpaceCanaryConfig,
    client: httpx.Client,
) -> JSONObject:
    """Run the live canary sequence and return one aggregate report payload."""

    requested_run_count = (
        len(config.space_ids) * config.repeat_count * len(_MODE_SEQUENCE)
    )
    run_reports: list[JSONObject] = []
    for space_id in config.space_ids:
        for repeat_index in range(1, config.repeat_count + 1):
            for mode in _MODE_SEQUENCE:
                run_reports.append(
                    _execute_live_run(
                        config=config,
                        client=client,
                        space_id=space_id,
                        repeat_index=repeat_index,
                        mode=mode,
                    ),
                )
    return _build_real_space_canary_report(
        config=config,
        requested_run_count=requested_run_count,
        run_reports=run_reports,
    )


def _execute_live_run(
    *,
    config: RealSpaceCanaryConfig,
    client: httpx.Client,
    space_id: str,
    repeat_index: int,
    mode: LiveCanaryMode,
) -> JSONObject:
    started_at = time.perf_counter()
    request_started_at = datetime.now(UTC)
    errors: list[str] = []
    queued_response: JSONObject | None = None
    run_payload: JSONObject | None = None
    progress_payload: JSONObject | None = None
    workspace_payload: JSONObject | None = None
    artifacts_payload: JSONObject | None = None
    timeout_reached = False
    completed_during_timeout_grace = False
    run_id: str | None = None
    request_timeout_seconds = _request_timeout_seconds(config)
    request_payload = _research_init_request_payload(
        config=config,
        mode=mode,
        repeat_index=repeat_index,
    )

    try:
        try:
            queued_response = _request_json(
                client=client,
                method="POST",
                path=f"/v2/spaces/{space_id}/research-plan",
                headers=config.auth_headers,
                json_body=request_payload,
                acceptable_statuses=(_HTTP_CREATED,),
                timeout_seconds=request_timeout_seconds,
            )
            run_info = _task_payload(queued_response)
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
            queued_response = {"task": recovered_run}
        (
            run_payload,
            progress_payload,
            timeout_reached,
            completed_during_timeout_grace,
        ) = _poll_terminal_run(
            client=client,
            headers=config.auth_headers,
            space_id=space_id,
            run_id=run_id,
            timeout_seconds=config.poll_timeout_seconds,
            interval_seconds=config.poll_interval_seconds,
            request_timeout_seconds=request_timeout_seconds,
        )
        if timeout_reached:
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
        if run_id is not None:
            (
                workspace_payload,
                artifacts_payload,
            ) = _fetch_terminal_run_payloads(
                client=client,
                headers=config.auth_headers,
                space_id=space_id,
                run_id=run_id,
                interval_seconds=config.poll_interval_seconds,
                request_timeout_seconds=request_timeout_seconds,
                timeout_seconds=_DEFAULT_POST_TERMINAL_FETCH_SECONDS,
            )
            if mode.expects_guarded_artifacts:
                workspace_payload, artifacts_payload = _stabilize_guarded_payloads(
                    client=client,
                    headers=config.auth_headers,
                    space_id=space_id,
                    run_id=run_id,
                    interval_seconds=config.poll_interval_seconds,
                    request_timeout_seconds=request_timeout_seconds,
                    stabilization_seconds=(
                        _DEFAULT_GUARDED_PROOF_STABILIZATION_SECONDS
                    ),
                    workspace_payload=workspace_payload,
                    artifacts_payload=artifacts_payload,
                )
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    runtime_seconds = _run_runtime_seconds(
        run_payload=run_payload,
        observed_elapsed_seconds=time.perf_counter() - started_at,
    )
    return _summarize_live_run(
        config=config,
        space_id=space_id,
        repeat_index=repeat_index,
        mode=mode,
        queued_response=queued_response,
        run_payload=run_payload,
        progress_payload=progress_payload,
        workspace_payload=workspace_payload,
        artifacts_payload=artifacts_payload,
        runtime_seconds=runtime_seconds,
        timeout_reached=timeout_reached,
        completed_during_timeout_grace=completed_during_timeout_grace,
        errors=errors,
        run_id=run_id,
    )


def _poll_terminal_run(  # noqa: PLR0913
    *,
    client: httpx.Client,
    headers: dict[str, str],
    space_id: str,
    run_id: str,
    timeout_seconds: float,
    interval_seconds: float,
    request_timeout_seconds: float,
) -> tuple[JSONObject | None, JSONObject | None, bool, bool]:
    return _poll_terminal_run_with_grace(
        client=client,
        headers=headers,
        space_id=space_id,
        run_id=run_id,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        request_timeout_seconds=request_timeout_seconds,
        terminal_grace_seconds=_DEFAULT_TERMINAL_GRACE_SECONDS,
    )


def _poll_terminal_run_with_grace(  # noqa: PLR0913
    *,
    client: httpx.Client,
    headers: dict[str, str],
    space_id: str,
    run_id: str,
    timeout_seconds: float,
    interval_seconds: float,
    request_timeout_seconds: float,
    terminal_grace_seconds: float,
) -> tuple[JSONObject | None, JSONObject | None, bool, bool]:
    deadline = time.monotonic() + timeout_seconds
    latest_run: JSONObject | None = None
    latest_progress: JSONObject | None = None
    while time.monotonic() <= deadline:
        try:
            latest_run = _request_json(
                client=client,
                method="GET",
                path=f"/v2/spaces/{space_id}/tasks/{run_id}",
                headers=headers,
                timeout_seconds=request_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            if not _is_transient_request_error(exc):
                raise
            time.sleep(interval_seconds)
            continue
        try:
            latest_progress = _optional_json_request(
                client=client,
                method="GET",
                path=f"/v2/spaces/{space_id}/tasks/{run_id}/progress",
                headers=headers,
                timeout_seconds=request_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            if not _is_transient_request_error(exc):
                raise
            latest_progress = None
        run_status = _maybe_string(latest_run.get("status"))
        if run_status in _FINAL_RUN_STATUSES:
            return latest_run, latest_progress, False, False
        time.sleep(interval_seconds)
    final_run, final_progress = _terminal_grace_reconciliation(
        client=client,
        headers=headers,
        space_id=space_id,
        run_id=run_id,
        interval_seconds=interval_seconds,
        request_timeout_seconds=request_timeout_seconds,
        terminal_grace_seconds=terminal_grace_seconds,
        latest_run=latest_run,
        latest_progress=latest_progress,
    )
    final_status = _maybe_string(_dict_value(final_run).get("status"))
    completed_during_timeout_grace = final_status in _FINAL_RUN_STATUSES
    return (
        final_run,
        final_progress,
        not completed_during_timeout_grace,
        completed_during_timeout_grace,
    )


def _terminal_grace_reconciliation(  # noqa: PLR0913
    *,
    client: httpx.Client,
    headers: dict[str, str],
    space_id: str,
    run_id: str,
    interval_seconds: float,
    request_timeout_seconds: float,
    terminal_grace_seconds: float,
    latest_run: JSONObject | None,
    latest_progress: JSONObject | None,
) -> tuple[JSONObject | None, JSONObject | None]:
    grace_deadline = time.monotonic() + terminal_grace_seconds
    reconciled_run = latest_run
    reconciled_progress = latest_progress
    while time.monotonic() <= grace_deadline:
        try:
            reconciled_run = _request_json(
                client=client,
                method="GET",
                path=f"/v2/spaces/{space_id}/tasks/{run_id}",
                headers=headers,
                timeout_seconds=request_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            if not _is_transient_request_error(exc):
                raise
            time.sleep(interval_seconds)
            continue
        try:
            reconciled_progress = _optional_json_request(
                client=client,
                method="GET",
                path=f"/v2/spaces/{space_id}/tasks/{run_id}/progress",
                headers=headers,
                timeout_seconds=request_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            if not _is_transient_request_error(exc):
                raise
            reconciled_progress = None
        run_status = _maybe_string(_dict_value(reconciled_run).get("status"))
        if run_status in _FINAL_RUN_STATUSES:
            return reconciled_run, reconciled_progress
        time.sleep(interval_seconds)
    return reconciled_run, reconciled_progress


def _stabilize_guarded_payloads(  # noqa: PLR0913
    *,
    client: httpx.Client,
    headers: dict[str, str],
    space_id: str,
    run_id: str,
    interval_seconds: float,
    request_timeout_seconds: float,
    stabilization_seconds: float,
    workspace_payload: JSONObject | None,
    artifacts_payload: JSONObject | None,
) -> tuple[JSONObject | None, JSONObject | None]:
    latest_workspace = workspace_payload
    latest_artifacts = artifacts_payload
    if not _guarded_payloads_need_stabilization(
        workspace_payload=latest_workspace,
        artifacts_payload=latest_artifacts,
    ):
        return latest_workspace, latest_artifacts
    deadline = time.monotonic() + stabilization_seconds
    while time.monotonic() <= deadline:
        time.sleep(interval_seconds)
        try:
            latest_workspace, latest_artifacts = _fetch_terminal_run_payloads(
                client=client,
                headers=headers,
                space_id=space_id,
                run_id=run_id,
                interval_seconds=interval_seconds,
                request_timeout_seconds=request_timeout_seconds,
                timeout_seconds=interval_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            if not _is_transient_request_error(exc):
                raise
            continue
        if not _guarded_payloads_need_stabilization(
            workspace_payload=latest_workspace,
            artifacts_payload=latest_artifacts,
        ):
            return latest_workspace, latest_artifacts
    return latest_workspace, latest_artifacts


def _guarded_payloads_need_stabilization(
    *,
    workspace_payload: JSONObject | None,
    artifacts_payload: JSONObject | None,
) -> bool:
    workspace_snapshot = _working_state_snapshot(workspace_payload)
    artifact_list = _output_list(artifacts_payload)
    artifacts_by_key = _artifact_contents_by_key(artifact_list)
    guarded_proofs = _dict_value(workspace_snapshot.get("guarded_decision_proofs"))
    if not guarded_proofs:
        guarded_proofs = _dict_value(
            artifacts_by_key.get(_GUARDED_DECISION_PROOFS_ARTIFACT_KEY),
        )
    return _int_value(guarded_proofs.get("pending_verification_count")) > 0


def _recover_queued_run_by_title(  # noqa: PLR0913
    *,
    client: httpx.Client,
    headers: dict[str, str],
    space_id: str,
    title: str,
    started_at: datetime,
    timeout_seconds: float,
    interval_seconds: float,
) -> JSONObject | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() <= deadline:
        try:
            runs_payload = _request_json(
                client=client,
                method="GET",
                path=f"/v2/spaces/{space_id}/tasks?limit=200",
                headers=headers,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            if not _is_transient_request_error(exc):
                raise
            time.sleep(interval_seconds)
            continue
        tasks = _list_of_dicts(runs_payload.get("tasks") or runs_payload.get("runs"))
        for run in tasks:
            if _maybe_string(run.get("title")) != title:
                continue
            created_at = _parse_datetime(run.get("created_at"))
            if created_at is None or created_at >= started_at:
                return run
        time.sleep(interval_seconds)
    return None


def _fetch_terminal_run_payloads(  # noqa: PLR0913
    *,
    client: httpx.Client,
    headers: dict[str, str],
    space_id: str,
    run_id: str,
    interval_seconds: float,
    request_timeout_seconds: float,
    timeout_seconds: float,
) -> tuple[JSONObject, JSONObject]:
    deadline = time.monotonic() + timeout_seconds
    last_exc: Exception | None = None
    while time.monotonic() <= deadline:
        try:
            workspace_payload = _request_json(
                client=client,
                method="GET",
                path=f"/v2/spaces/{space_id}/tasks/{run_id}/working-state",
                headers=headers,
                timeout_seconds=request_timeout_seconds,
            )
            artifacts_payload = _request_json(
                client=client,
                method="GET",
                path=f"/v2/spaces/{space_id}/tasks/{run_id}/outputs",
                headers=headers,
                timeout_seconds=request_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            if not _is_transient_request_error(exc):
                raise
            last_exc = exc
            time.sleep(interval_seconds)
        else:
            return workspace_payload, artifacts_payload
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(
        f"Timed out fetching terminal payloads for run '{run_id}'.",
    )


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


def _research_init_request_payload(
    *,
    config: RealSpaceCanaryConfig,
    mode: LiveCanaryMode,
    repeat_index: int,
) -> JSONObject:
    payload: JSONObject = {
        "objective": config.objective,
        "seed_terms": list(config.seed_terms),
        "title": _build_run_title(config, mode=mode, repeat_index=repeat_index),
        "sources": dict(config.sources) if config.sources is not None else None,
        "max_depth": config.max_depth,
        "max_hypotheses": config.max_hypotheses,
        "orchestration_mode": mode.orchestration_mode,
    }
    if mode.guarded_rollout_profile is not None:
        payload["guarded_rollout_profile"] = mode.guarded_rollout_profile
    return {key: value for key, value in payload.items() if value is not None}


def _build_run_title(
    config: RealSpaceCanaryConfig,
    *,
    mode: LiveCanaryMode,
    repeat_index: int,
) -> str:
    base_title = config.title or config.canary_label or "Real-Space Guarded Canary"
    return f"{base_title} [{mode.key} #{repeat_index}]"


def _resolve_auth_headers(args: argparse.Namespace) -> dict[str, str]:
    api_key = _maybe_string(args.api_key) or _maybe_string(os.getenv(_API_KEY_ENV))
    if api_key is not None:
        return {"X-Artana-Key": api_key}
    bearer_token = _maybe_string(args.bearer_token) or _maybe_string(
        os.getenv(_BEARER_TOKEN_ENV),
    )
    if bearer_token is not None:
        return {"Authorization": f"Bearer {bearer_token}"}
    if bool(args.use_test_auth):
        return {
            "X-TEST-USER-ID": str(args.test_user_id).strip(),
            "X-TEST-USER-EMAIL": str(args.test_user_email).strip(),
            "X-TEST-USER-ROLE": str(args.test_user_role).strip(),
        }
    raise SystemExit(
        "Authentication is required. Provide --api-key / ARTANA_EVIDENCE_API_KEY, "
        "--bearer-token / ARTANA_EVIDENCE_API_BEARER_TOKEN, or --use-test-auth.",
    )


def _request_json(  # noqa: PLR0913
    *,
    client: httpx.Client,
    method: str,
    path: str,
    headers: dict[str, str],
    json_body: JSONObject | None = None,
    acceptable_statuses: tuple[int, ...] = (200,),
    timeout_seconds: float | None = None,
) -> JSONObject:
    response = client.request(
        method=method,
        url=path,
        headers=headers,
        json=json_body,
        timeout=timeout_seconds,
    )
    if response.status_code not in acceptable_statuses:
        raise RuntimeError(
            _format_http_error(
                method=method,
                path=path,
                status_code=response.status_code,
                detail=response.text.strip(),
            ),
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{method} {path} returned non-JSON content") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{method} {path} returned a non-object JSON payload")
    return dict(payload)


def _optional_json_request(
    *,
    client: httpx.Client,
    method: str,
    path: str,
    headers: dict[str, str],
    timeout_seconds: float | None = None,
) -> JSONObject | None:
    response = client.request(
        method=method,
        url=path,
        headers=headers,
        timeout=timeout_seconds,
    )
    if response.status_code == _HTTP_NOT_FOUND:
        return None
    if response.status_code != _HTTP_OK:
        raise RuntimeError(
            _format_http_error(
                method=method,
                path=path,
                status_code=response.status_code,
                detail=response.text.strip(),
            ),
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{method} {path} returned non-JSON content") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{method} {path} returned a non-object JSON payload")
    return dict(payload)


def _artifact_contents_by_key(artifact_list: list[JSONObject]) -> dict[str, JSONObject]:
    contents: dict[str, JSONObject] = {}
    for artifact in artifact_list:
        key = _maybe_string(artifact.get("key"))
        content = _dict_value(artifact.get("content"))
        if key is None or not content:
            continue
        contents[key] = content
    return contents


def _format_http_error(
    *,
    method: str,
    path: str,
    status_code: int,
    detail: str,
) -> str:
    detail_text = f": {detail}" if detail else ""
    if status_code == _HTTP_UNAUTHORIZED and "Signature verification failed" in detail:
        return (
            f"{method} {path} returned HTTP {_HTTP_UNAUTHORIZED}{detail_text}. "
            "Bearer token signature verification failed. Ensure the token was "
            "signed with the same AUTH_JWT_SECRET the Artana Evidence API is "
            "using, or rerun with --api-key / ARTANA_EVIDENCE_API_KEY or "
            "--use-test-auth for local development."
        )
    return f"{method} {path} returned HTTP {status_code}{detail_text}"


def _build_run_matrix(run_reports: list[JSONObject]) -> JSONObject:
    matrix: dict[str, dict[str, JSONObject]] = {}
    for run in run_reports:
        space_id = _maybe_string(run.get("space_id")) or "unknown-space"
        mode_key = _maybe_string(run.get("requested_mode")) or "unknown-mode"
        space_cell = matrix.setdefault(space_id, {})
        mode_cell = space_cell.setdefault(
            mode_key,
            {
                "requested_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "statuses": [],
            },
        )
        mode_cell["requested_count"] = _int_value(mode_cell.get("requested_count")) + 1
        if run.get("result_status") == "completed":
            mode_cell["completed_count"] = (
                _int_value(mode_cell.get("completed_count")) + 1
            )
        else:
            mode_cell["failed_count"] = _int_value(mode_cell.get("failed_count")) + 1
        statuses = _string_list(mode_cell.get("statuses"))
        statuses.append(_maybe_string(run.get("result_status")) or "unknown")
        mode_cell["statuses"] = statuses
    return matrix


def _run_runtime_seconds(
    *,
    run_payload: JSONObject | None,
    observed_elapsed_seconds: float,
) -> float | None:
    run = run_payload or {}
    created_at = _parse_datetime(run.get("created_at"))
    updated_at = _parse_datetime(run.get("updated_at"))
    if created_at is not None and updated_at is not None:
        return max(0.0, (updated_at - created_at).total_seconds())
    return observed_elapsed_seconds


def _normalize_space_ids(
    *,
    explicit_space_ids: list[str],
    csv_space_ids: str,
) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    raw_values = [*explicit_space_ids]
    if csv_space_ids.strip():
        raw_values.extend(part.strip() for part in csv_space_ids.split(","))
    for raw in raw_values:
        value = raw.strip()
        if value == "":
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    if not normalized:
        raise SystemExit("At least one non-empty --space-id is required.")
    return tuple(normalized)


def _normalize_seed_terms(
    *,
    explicit_terms: list[str],
    csv_terms: str,
) -> tuple[str, ...]:
    raw_values = [*explicit_terms]
    if csv_terms.strip():
        raw_values.extend(part.strip() for part in csv_terms.split(","))
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        trimmed = raw.strip()
        if trimmed == "" or trimmed in seen:
            continue
        seen.add(trimmed)
        normalized.append(trimmed)
    return tuple(normalized)


def _load_sources_preferences(raw_value: str) -> dict[str, bool] | None:
    normalized = _maybe_string(raw_value)
    if normalized is None:
        return None
    source_text = normalized
    if not normalized.startswith("{"):
        candidate_path = _resolve_path(Path(normalized))
        if not candidate_path.is_file():
            raise SystemExit(
                f"--sources-json must be inline JSON or an existing file path: {normalized}",
            )
        source_text = candidate_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(source_text)
    except ValueError as exc:
        raise SystemExit(f"Unable to parse --sources-json: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("--sources-json must resolve to a JSON object.")
    normalized_sources: dict[str, bool] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, bool):
            raise SystemExit(
                "--sources-json keys must be strings and values must be booleans.",
            )
        normalized_sources[key] = value
    return normalized_sources


def _normalize_report_mode(value: object) -> ReportMode:
    if value in {"standard", "canary"}:
        return value
    raise SystemExit(f"Unsupported report mode: {value!r}")


def _normalize_expected_run_count(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and value > 0:
        return value
    raise SystemExit("--expected-run-count must be a positive integer.")


def _normalize_positive_int(value: object, *, name: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    raise SystemExit(f"{name} must be a positive integer.")


def _normalize_positive_float(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise SystemExit(f"{name} must be a positive number.")
    if isinstance(value, int | float) and float(value) > 0:
        return float(value)
    raise SystemExit(f"{name} must be a positive number.")


def _request_timeout_seconds(config: RealSpaceCanaryConfig) -> float:
    return max(
        1.0,
        min(config.poll_timeout_seconds, _DEFAULT_POLL_REQUEST_TIMEOUT_SECONDS),
    )


def _is_transient_request_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, RuntimeError):
        message = str(exc)
        return "HTTP 500" in message or "HTTP 502" in message or "HTTP 503" in message
    return False


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else _REPO_ROOT / path


def _required_string(payload: JSONObject, key: str, label: str) -> str:
    value = _maybe_string(payload.get(key))
    if value is None:
        raise RuntimeError(f"{label} is missing required field '{key}'")
    return value


def _dict_value(value: object) -> JSONObject:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip() != ""]


def _maybe_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped != "" else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _int_value(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _is_int_value(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _round_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def _display_float(value: object) -> str:
    number = _optional_float(value)
    if number is None:
        return "n/a"
    return f"{number:.3f}"


def _run_label(run: JSONObject) -> str:
    space_id = _maybe_string(run.get("space_id")) or "unknown-space"
    mode = _maybe_string(run.get("requested_mode")) or "unknown-mode"
    repeat_index = _int_value(run.get("repeat_index"))
    run_id = _maybe_string(run.get("run_id"))
    if run_id is not None:
        return f"{space_id}:{mode}:repeat-{repeat_index}:{run_id}"
    return f"{space_id}:{mode}:repeat-{repeat_index}"


def _proof_recommended_source_key(proof: JSONObject) -> str | None:
    for key in ("recommended_source_key", "applied_source_key"):
        source_key = _maybe_string(proof.get(key))
        if source_key is not None:
            return source_key
    for key in ("recommended_action_type", "applied_action_type"):
        action_type = _maybe_string(proof.get(key))
        if action_type is None:
            continue
        default_source_key = _ACTION_DEFAULT_SOURCE_KEYS.get(action_type)
        if default_source_key is not None:
            return default_source_key
    return None


def _proof_source_policy_violation_category(
    proof: JSONObject,
) -> Literal["disabled", "reserved", "context_only", "grounding"] | None:
    if proof.get("disabled_source_violation") is True:
        return "disabled"
    source_key = _proof_recommended_source_key(proof)
    if source_key in _RESERVED_SOURCE_KEYS:
        return "reserved"
    if source_key in _CONTEXT_ONLY_SOURCE_KEYS:
        return "context_only"
    if source_key in _GROUNDING_SOURCE_KEYS:
        return "grounding"
    validation_error = (_maybe_string(proof.get("validation_error")) or "").casefold()
    if "reserved" in validation_error:
        return "reserved"
    if "context_only" in validation_error or "context-only" in validation_error:
        return "context_only"
    if "grounding" in validation_error:
        return "grounding"
    return None


def _safe_filename(value: str) -> str:
    normalized = _SAFE_FILENAME_RE.sub("_", value).strip("._")
    return normalized[:180]


if __name__ == "__main__":
    raise SystemExit(main())
