#!/usr/bin/env python3
"""Run a manual guarded source+chase canary against live research-init routes."""

from __future__ import annotations

import argparse
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

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject

from scripts.full_ai_real_space_canary import utils as _canary_utils  # noqa: E402
from scripts.full_ai_real_space_canary.reporting import (  # noqa: E402
    _build_real_space_canary_report,
    _summarize_live_run,
    render_real_space_canary_markdown,
    write_real_space_canary_report,
)
from scripts.full_ai_real_space_canary.utils import (  # noqa: E402
    _artifact_contents_by_key,
    _dict_value,
    _int_value,
    _is_transient_request_error,
    _list_of_dicts,
    _load_sources_preferences,
    _maybe_string,
    _normalize_expected_run_count,
    _normalize_positive_float,
    _normalize_positive_int,
    _normalize_report_mode,
    _normalize_seed_terms,
    _normalize_space_ids,
    _optional_json_request,
    _output_list,
    _parse_datetime,
    _request_json,
    _request_timeout_seconds,
    _required_string,
    _research_init_request_payload,
    _resolve_auth_headers,
    _resolve_path,
    _run_runtime_seconds,
    _task_payload,
    _working_state_snapshot,
)

_round_float = _canary_utils._round_float  # noqa: SLF001
_safe_filename = _canary_utils._safe_filename  # noqa: SLF001

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


if __name__ == "__main__":
    raise SystemExit(main())
