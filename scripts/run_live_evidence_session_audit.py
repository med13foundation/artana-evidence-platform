#!/usr/bin/env python3
"""Run a live Artana Evidence API session audit with real AI and graph checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, TextIO
from urllib.parse import urlencode

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from scripts.run_full_ai_real_space_canary import (  # noqa: E402
    _artifact_contents_by_key,
    _dict_value,
    _fetch_terminal_run_payloads,
    _is_transient_request_error,
    _list_of_dicts,
    _maybe_string,
    _normalize_positive_float,
    _normalize_positive_int,
    _normalize_seed_terms,
    _normalize_space_ids,
    _optional_json_request,
    _poll_terminal_run,
    _recover_queued_run_by_title,
    _request_json,
    _resolve_auth_headers,
    _resolve_path,
    _round_float,
    _safe_filename,
    _output_list,
    _task_payload,
    _working_state_snapshot,
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject


_BASE_URL_ENV = "ARTANA_EVIDENCE_API_LIVE_BASE_URL"
_DEFAULT_BASE_URL = "http://localhost:8091"
_DEFAULT_REPORT_SUBDIR = "live_evidence_session_audit"
_DEFAULT_TIMEOUT_SECONDS = 60.0
_DEFAULT_POLL_TIMEOUT_SECONDS = 900.0
_DEFAULT_POLL_INTERVAL_SECONDS = 2.0
_DEFAULT_REQUEST_TIMEOUT_SECONDS = 15.0
_DEFAULT_GRAPH_SETTLE_SECONDS = 20.0
_DEFAULT_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
_DEFAULT_TEST_USER_EMAIL = "researcher@example.com"
_DEFAULT_TEST_USER_ROLE = "researcher"
_DEFAULT_REPEAT_COUNT = 1
_DEFAULT_RESEARCH_INIT_TITLE = "Live Evidence Session Audit"
_DEFAULT_BOOTSTRAP_TITLE = "Live Evidence Bootstrap Audit"
_DEFAULT_PROMOTION_REASON = "Live evidence session audit promotion"
_DEFAULT_RESEARCH_INIT_PHASE = "research_init"
_DEFAULT_BOOTSTRAP_PHASE = "research_bootstrap"
_DEFAULT_SESSION_KIND = "live_evidence_session_audit"
_DEFAULT_LOG_TAIL_LINES = 80
_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_ACCEPTED = 202
_FINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled", "canceled"})
_SUCCESS_RUN_STATUS = "completed"
_DEFAULT_LOG_ERROR_PATTERNS = (
    r"(?i)\btraceback\b",
    r"(?i)\bfatal\b",
    r"(?i)\bexception\b",
    r"(?i)\berror\b",
    r'"\s5\d{2}\b',
)
_DEFAULT_ENV_FILES = (
    Path(".env.postgres"),
    Path(".env"),
    Path("scripts/.env"),
)
_QUOTED_ENV_MIN_LENGTH = 2


@dataclass(frozen=True, slots=True)
class LogCommandConfig:
    command: str
    name: str


@dataclass(frozen=True, slots=True)
class LiveEvidenceSessionAuditConfig:
    base_url: str
    auth_headers: dict[str, str]
    output_dir: Path
    label: str | None
    space_ids: tuple[str, ...]
    objective: str
    seed_terms: tuple[str, ...]
    research_init_title: str
    research_init_max_depth: int
    research_init_max_hypotheses: int
    sources: dict[str, bool] | None
    bootstrap_objective: str
    bootstrap_title: str
    bootstrap_seed_entity_ids: tuple[str, ...]
    bootstrap_source_type: str
    bootstrap_max_depth: int
    bootstrap_max_hypotheses: int
    repeat_count: int
    promote_first_proposal: bool
    promotion_reason: str
    require_graph_activity: bool
    poll_timeout_seconds: float
    poll_interval_seconds: float
    graph_settle_seconds: float
    log_commands: tuple[LogCommandConfig, ...]
    log_error_patterns: tuple[str, ...]
    log_ignore_patterns: tuple[str, ...]
    fail_on_log_match: bool


@dataclass(slots=True)
class _CapturedLogLine:
    channel: str
    text: str
    matched_error_pattern: bool

    def render(self) -> str:
        return f"[{self.channel}] {self.text}"


@dataclass(slots=True)
class _LogCommandMonitor:
    config: LogCommandConfig
    output_path: Path
    error_patterns: tuple[re.Pattern[str], ...]
    ignore_patterns: tuple[re.Pattern[str], ...]
    tail_lines: int = _DEFAULT_LOG_TAIL_LINES
    process: subprocess.Popen[str] | None = field(init=False, default=None)
    _threads: list[threading.Thread] = field(init=False, default_factory=list)
    _writer: TextIO | None = field(init=False, default=None)
    _tail: deque[str] = field(init=False)
    _suspicious: deque[str] = field(init=False)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    total_lines: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self._tail = deque(maxlen=self.tail_lines)
        self._suspicious = deque(maxlen=max(self.tail_lines, 40))

    def start(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._writer = self.output_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            ["/bin/sh", "-lc", self.config.command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        for channel, stream in (("stdout", self.process.stdout), ("stderr", self.process.stderr)):
            if stream is None:
                continue
            thread = threading.Thread(
                target=self._consume_stream,
                args=(channel, stream),
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def _consume_stream(self, channel: str, stream: TextIO) -> None:
        try:
            for raw_line in stream:
                line = raw_line.rstrip("\n")
                matched = self._line_matches_error(line)
                captured = _CapturedLogLine(
                    channel=channel,
                    text=line,
                    matched_error_pattern=matched,
                )
                rendered = captured.render()
                with self._lock:
                    self.total_lines += 1
                    self._tail.append(rendered)
                    if matched:
                        self._suspicious.append(rendered)
                    if self._writer is not None:
                        self._writer.write(rendered + "\n")
                        self._writer.flush()
        finally:
            stream.close()

    def _line_matches_error(self, line: str) -> bool:
        if line.strip() == "":
            return False
        if any(pattern.search(line) for pattern in self.ignore_patterns):
            return False
        return any(pattern.search(line) for pattern in self.error_patterns)

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=timeout_seconds)
        for thread in self._threads:
            thread.join(timeout=timeout_seconds)
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    def summary(self) -> JSONObject:
        with self._lock:
            suspicious_lines = list(self._suspicious)
            tail_lines = list(self._tail)
        process = self.process
        exit_code = process.returncode if process is not None else None
        return {
            "name": self.config.name,
            "command": self.config.command,
            "output_path": str(self.output_path),
            "total_lines": self.total_lines,
            "suspicious_line_count": len(suspicious_lines),
            "suspicious_lines": suspicious_lines,
            "tail_lines": tail_lines,
            "exit_code": exit_code,
        }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a live Artana Evidence API end-to-end session audit using real AI "
            "calls, stage graph proposals, promote one proposal, and verify the "
            "claim/evidence writes through graph-explorer reads."
        ),
    )
    parser.add_argument("--space-id", action="append", default=[])
    parser.add_argument("--space-ids", default="")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--seed-term", action="append", default=[])
    parser.add_argument("--seed-terms", default="")
    parser.add_argument("--research-init-title", default=_DEFAULT_RESEARCH_INIT_TITLE)
    parser.add_argument("--bootstrap-title", default=_DEFAULT_BOOTSTRAP_TITLE)
    parser.add_argument("--bootstrap-objective", default="")
    parser.add_argument("--sources-json", default="")
    parser.add_argument("--research-init-max-depth", type=int, default=2)
    parser.add_argument("--research-init-max-hypotheses", type=int, default=20)
    parser.add_argument("--bootstrap-seed-entity-id", action="append", default=[])
    parser.add_argument("--bootstrap-source-type", default="pubmed")
    parser.add_argument("--bootstrap-max-depth", type=int, default=2)
    parser.add_argument("--bootstrap-max-hypotheses", type=int, default=20)
    parser.add_argument("--repeat-count", type=int, default=_DEFAULT_REPEAT_COUNT)
    parser.add_argument(
        "--promote-first-proposal",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--require-graph-activity",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--promotion-reason", default=_DEFAULT_PROMOTION_REASON)
    parser.add_argument(
        "--poll-timeout-seconds",
        type=float,
        default=_DEFAULT_POLL_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=_DEFAULT_POLL_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--graph-settle-seconds",
        type=float,
        default=_DEFAULT_GRAPH_SETTLE_SECONDS,
    )
    parser.add_argument("--log-command", action="append", default=[])
    parser.add_argument("--log-error-pattern", action="append", default=[])
    parser.add_argument("--log-ignore-pattern", action="append", default=[])
    parser.add_argument("--fail-on-log-match", action="store_true")
    parser.add_argument("--label", default="")
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
    loaded_env_keys = _load_environment_overrides()
    args = parse_args(argv)
    config = _config_from_args(args)
    with httpx.Client(
        base_url=config.base_url,
        timeout=_DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        report = run_live_evidence_session_audit(config=config, client=client)
    report["loaded_env_keys"] = loaded_env_keys
    manifest = write_live_evidence_session_audit_report(
        report=report,
        output_dir=config.output_dir,
    )
    print(render_live_evidence_session_audit_markdown(report))
    print()
    print(f"Summary JSON: {manifest['summary_json']}")
    print(f"Summary Markdown: {manifest['summary_markdown']}")
    return 0 if report.get("all_passed") is True else 1


def _config_from_args(args: argparse.Namespace) -> LiveEvidenceSessionAuditConfig:
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
    objective = str(args.objective).strip()
    bootstrap_objective = (
        _maybe_string(args.bootstrap_objective)
        or f"{objective} (bootstrap audit)"
    )
    label = _maybe_string(args.label)
    return LiveEvidenceSessionAuditConfig(
        base_url=base_url,
        auth_headers=_resolve_auth_headers(args),
        output_dir=output_dir,
        label=label,
        space_ids=_normalize_space_ids(
            explicit_space_ids=list(args.space_id),
            csv_space_ids=str(args.space_ids),
        ),
        objective=objective,
        seed_terms=_normalize_seed_terms(
            explicit_terms=list(args.seed_term),
            csv_terms=str(args.seed_terms),
        ),
        research_init_title=(
            _maybe_string(args.research_init_title) or _DEFAULT_RESEARCH_INIT_TITLE
        ),
        research_init_max_depth=_normalize_positive_int(
            args.research_init_max_depth,
            name="research_init_max_depth",
        ),
        research_init_max_hypotheses=_normalize_positive_int(
            args.research_init_max_hypotheses,
            name="research_init_max_hypotheses",
        ),
        sources=_load_sources_preferences(args.sources_json),
        bootstrap_objective=bootstrap_objective,
        bootstrap_title=(
            _maybe_string(args.bootstrap_title) or _DEFAULT_BOOTSTRAP_TITLE
        ),
        bootstrap_seed_entity_ids=_normalize_string_tuple(
            list(args.bootstrap_seed_entity_id),
        ),
        bootstrap_source_type=str(args.bootstrap_source_type).strip() or "pubmed",
        bootstrap_max_depth=_normalize_positive_int(
            args.bootstrap_max_depth,
            name="bootstrap_max_depth",
        ),
        bootstrap_max_hypotheses=_normalize_positive_int(
            args.bootstrap_max_hypotheses,
            name="bootstrap_max_hypotheses",
        ),
        repeat_count=_normalize_positive_int(args.repeat_count, name="repeat_count"),
        promote_first_proposal=bool(args.promote_first_proposal),
        promotion_reason=(
            _maybe_string(args.promotion_reason) or _DEFAULT_PROMOTION_REASON
        ),
        require_graph_activity=bool(args.require_graph_activity),
        poll_timeout_seconds=_normalize_positive_float(
            args.poll_timeout_seconds,
            name="poll_timeout_seconds",
        ),
        poll_interval_seconds=_normalize_positive_float(
            args.poll_interval_seconds,
            name="poll_interval_seconds",
        ),
        graph_settle_seconds=_normalize_positive_float(
            args.graph_settle_seconds,
            name="graph_settle_seconds",
        ),
        log_commands=_normalize_log_commands(list(args.log_command)),
        log_error_patterns=tuple(
            args.log_error_pattern or _DEFAULT_LOG_ERROR_PATTERNS
        ),
        log_ignore_patterns=tuple(args.log_ignore_pattern or []),
        fail_on_log_match=bool(args.fail_on_log_match),
    )


def run_live_evidence_session_audit(
    *,
    config: LiveEvidenceSessionAuditConfig,
    client: httpx.Client,
) -> JSONObject:
    session_reports = [
        _run_single_live_session(
            config=config,
            client=client,
            space_id=space_id,
            repeat_index=repeat_index,
        )
        for space_id in config.space_ids
        for repeat_index in range(1, config.repeat_count + 1)
    ]
    return build_live_evidence_session_audit_report(
        config=config,
        session_reports=session_reports,
    )


def _run_single_live_session(
    *,
    config: LiveEvidenceSessionAuditConfig,
    client: httpx.Client,
    space_id: str,
    repeat_index: int,
) -> JSONObject:
    session_started_at = time.perf_counter()
    session_label = _session_label(
        config=config,
        space_id=space_id,
        repeat_index=repeat_index,
    )
    session_dir = config.output_dir / "sessions" / _safe_filename(session_label)
    session_dir.mkdir(parents=True, exist_ok=True)
    monitors = _start_log_monitors(config=config, session_dir=session_dir)
    errors: list[str] = []
    baseline_claim_total = 0
    research_init_step: JSONObject | None = None
    bootstrap_step: JSONObject | None = None
    promotion_step: JSONObject | None = None
    graph_audit: JSONObject | None = None
    proposal_id: str | None = None
    log_summaries: list[JSONObject] = []

    try:
        baseline_claim_total = _graph_claim_total(
            client=client,
            headers=config.auth_headers,
            space_id=space_id,
            request_timeout_seconds=_request_timeout_seconds(config),
        )
        research_init_step = _execute_research_init_run(
            config=config,
            client=client,
            space_id=space_id,
            repeat_index=repeat_index,
            session_label=session_label,
        )
        errors.extend(_step_errors(research_init_step))

        bootstrap_step = _execute_bootstrap_run(
            config=config,
            client=client,
            space_id=space_id,
            repeat_index=repeat_index,
            session_label=session_label,
        )
        errors.extend(_step_errors(bootstrap_step))

        proposal_id = _resolve_bootstrap_proposal_id(
            config=config,
            client=client,
            space_id=space_id,
            bootstrap_step=bootstrap_step,
        )
        if config.promote_first_proposal:
            if proposal_id is None:
                errors.append("No bootstrap proposal was available to promote.")
            else:
                promotion_step = _promote_first_bootstrap_proposal(
                    config=config,
                    client=client,
                    space_id=space_id,
                    proposal_id=proposal_id,
                )
                errors.extend(_step_errors(promotion_step))
        graph_audit = _wait_for_graph_claim_audit(
            config=config,
            client=client,
            space_id=space_id,
            proposal_id=proposal_id,
            promotion_step=promotion_step,
            baseline_claim_total=baseline_claim_total,
        )
        errors.extend(_graph_audit_errors(graph_audit, require_graph_activity=config.require_graph_activity))
    finally:
        log_summaries = _stop_log_monitors(monitors)

    if config.fail_on_log_match:
        suspicious_count = sum(
            _int_value(summary.get("suspicious_line_count")) for summary in log_summaries
        )
        if suspicious_count > 0:
            errors.append(
                f"Log monitors captured {suspicious_count} suspicious line(s).",
            )

    status = "completed" if not errors else "failed"
    return {
        "session_kind": _DEFAULT_SESSION_KIND,
        "session_label": session_label,
        "space_id": space_id,
        "repeat_index": repeat_index,
        "status": status,
        "runtime_seconds": _round_float(time.perf_counter() - session_started_at),
        "baseline_claim_total": baseline_claim_total,
        "research_init": research_init_step,
        "research_bootstrap": bootstrap_step,
        "proposal_id": proposal_id,
        "proposal_promotion": promotion_step,
        "graph_audit": graph_audit,
        "logs": log_summaries,
        "errors": errors,
    }


def _execute_research_init_run(
    *,
    config: LiveEvidenceSessionAuditConfig,
    client: httpx.Client,
    space_id: str,
    repeat_index: int,
    session_label: str,
) -> JSONObject:
    del repeat_index
    title = f"{config.research_init_title} [{session_label}]"
    request_payload: JSONObject = {
        "objective": config.objective,
        "seed_terms": list(config.seed_terms),
        "title": title,
        "max_depth": config.research_init_max_depth,
        "max_hypotheses": config.research_init_max_hypotheses,
    }
    if config.sources is not None:
        request_payload["sources"] = dict(config.sources)
    return _execute_queue_only_step(
        config=config,
        client=client,
        space_id=space_id,
        step_key=_DEFAULT_RESEARCH_INIT_PHASE,
        path=f"/v2/spaces/{space_id}/research-plan",
        request_payload=request_payload,
        started_at=datetime.now(UTC),
    )


def _execute_bootstrap_run(
    *,
    config: LiveEvidenceSessionAuditConfig,
    client: httpx.Client,
    space_id: str,
    repeat_index: int,
    session_label: str,
) -> JSONObject:
    del repeat_index
    request_payload: JSONObject = {
        "objective": config.bootstrap_objective,
        "title": f"{config.bootstrap_title} [{session_label}]",
        "source_type": config.bootstrap_source_type,
        "max_depth": config.bootstrap_max_depth,
        "max_hypotheses": config.bootstrap_max_hypotheses,
    }
    if config.bootstrap_seed_entity_ids:
        request_payload["seed_entity_ids"] = list(config.bootstrap_seed_entity_ids)
    return _execute_step_with_optional_sync_result(
        config=config,
        client=client,
        space_id=space_id,
        step_key=_DEFAULT_BOOTSTRAP_PHASE,
        path=f"/v2/spaces/{space_id}/workflows/topic-setup/tasks",
        request_payload=request_payload,
        started_at=datetime.now(UTC),
    )


def _execute_queue_only_step(  # noqa: PLR0913
    *,
    config: LiveEvidenceSessionAuditConfig,
    client: httpx.Client,
    space_id: str,
    step_key: str,
    path: str,
    request_payload: JSONObject,
    started_at: datetime,
) -> JSONObject:
    started_at_seconds = time.perf_counter()
    errors: list[str] = []
    queued_response: JSONObject | None = None
    run_payload: JSONObject | None = None
    progress_payload: JSONObject | None = None
    workspace_payload: JSONObject | None = None
    artifacts_payload: JSONObject | None = None
    events_payload: JSONObject | None = None
    run_id: str | None = None
    timed_out = False
    completed_during_timeout_grace = False
    request_timeout_seconds = _request_timeout_seconds(config)

    try:
        try:
            queued_response = _request_json(
                client=client,
                method="POST",
                path=path,
                headers=config.auth_headers,
                json_body=request_payload,
                acceptable_statuses=(_HTTP_CREATED,),
                timeout_seconds=request_timeout_seconds,
            )
            run_id = _required_string(
                _task_payload(queued_response),
                "id",
                f"{step_key} queued response run",
            )
        except httpx.TimeoutException:
            recovered_run = _recover_queued_run_by_title(
                client=client,
                headers=config.auth_headers,
                space_id=space_id,
                title=_required_string(request_payload, "title", f"{step_key} request"),
                started_at=started_at,
                timeout_seconds=request_timeout_seconds,
                interval_seconds=config.poll_interval_seconds,
            )
            if recovered_run is None:
                raise
            run_id = _required_string(recovered_run, "id", f"{step_key} recovered run")
            queued_response = {"task": recovered_run}
        (
            run_payload,
            progress_payload,
            timed_out,
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
        if run_id is not None:
            (
                workspace_payload,
                artifacts_payload,
                events_payload,
            ) = _fetch_run_diagnostics(
                client=client,
                headers=config.auth_headers,
                space_id=space_id,
                run_id=run_id,
                interval_seconds=config.poll_interval_seconds,
                request_timeout_seconds=request_timeout_seconds,
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
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    result_payload = _primary_payload_from_workspace_artifacts(
        workspace_payload=workspace_payload,
        artifacts_payload=artifacts_payload,
    )
    return _step_report(
        step_key=step_key,
        request_payload=request_payload,
        queued_response=queued_response,
        run_payload=run_payload,
        progress_payload=progress_payload,
        workspace_payload=workspace_payload,
        artifacts_payload=artifacts_payload,
        events_payload=events_payload,
        result_payload=result_payload,
        runtime_seconds=time.perf_counter() - started_at_seconds,
        timed_out=timed_out,
        completed_during_timeout_grace=completed_during_timeout_grace,
        errors=errors,
        run_id=run_id,
    )


def _execute_step_with_optional_sync_result(  # noqa: PLR0913
    *,
    config: LiveEvidenceSessionAuditConfig,
    client: httpx.Client,
    space_id: str,
    step_key: str,
    path: str,
    request_payload: JSONObject,
    started_at: datetime,
) -> JSONObject:
    started_at_seconds = time.perf_counter()
    errors: list[str] = []
    response_payload: JSONObject | None = None
    run_payload: JSONObject | None = None
    progress_payload: JSONObject | None = None
    workspace_payload: JSONObject | None = None
    artifacts_payload: JSONObject | None = None
    events_payload: JSONObject | None = None
    result_payload: JSONObject | None = None
    run_id: str | None = None
    timed_out = False
    completed_during_timeout_grace = False
    request_timeout_seconds = _request_timeout_seconds(config)

    try:
        try:
            status_code, response_payload = _request_json_with_status(
                client=client,
                method="POST",
                path=path,
                headers=config.auth_headers,
                json_body=request_payload,
                acceptable_statuses=(_HTTP_CREATED, _HTTP_ACCEPTED),
                timeout_seconds=request_timeout_seconds,
            )
        except httpx.TimeoutException:
            recovered_run = _recover_queued_run_by_title(
                client=client,
                headers=config.auth_headers,
                space_id=space_id,
                title=_required_string(request_payload, "title", f"{step_key} request"),
                started_at=started_at,
                timeout_seconds=request_timeout_seconds,
                interval_seconds=config.poll_interval_seconds,
            )
            if recovered_run is None:
                raise
            status_code = _HTTP_ACCEPTED
            response_payload = {"task": recovered_run}

        run_id = _required_string(
            _dict_value(response_payload.get("run")),
            "id",
            f"{step_key} run",
        )
        if status_code == _HTTP_ACCEPTED:
            (
                run_payload,
                progress_payload,
                timed_out,
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
        else:
            run_payload = _dict_value(response_payload.get("run"))
            result_payload = response_payload
        (
            workspace_payload,
            artifacts_payload,
            events_payload,
        ) = _fetch_run_diagnostics(
            client=client,
            headers=config.auth_headers,
            space_id=space_id,
            run_id=run_id,
            interval_seconds=config.poll_interval_seconds,
            request_timeout_seconds=request_timeout_seconds,
        )
        if result_payload is None:
            result_payload = _primary_payload_from_workspace_artifacts(
                workspace_payload=workspace_payload,
                artifacts_payload=artifacts_payload,
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    return _step_report(
        step_key=step_key,
        request_payload=request_payload,
        queued_response=response_payload,
        run_payload=run_payload,
        progress_payload=progress_payload,
        workspace_payload=workspace_payload,
        artifacts_payload=artifacts_payload,
        events_payload=events_payload,
        result_payload=result_payload,
        runtime_seconds=time.perf_counter() - started_at_seconds,
        timed_out=timed_out,
        completed_during_timeout_grace=completed_during_timeout_grace,
        errors=errors,
        run_id=run_id,
    )


def _promote_first_bootstrap_proposal(
    *,
    config: LiveEvidenceSessionAuditConfig,
    client: httpx.Client,
    space_id: str,
    proposal_id: str,
) -> JSONObject:
    started_at_seconds = time.perf_counter()
    errors: list[str] = []
    response_payload: JSONObject | None = None
    try:
        response_payload = _request_json(
            client=client,
            method="POST",
            path=f"/v2/spaces/{space_id}/proposed-updates/{proposal_id}/promote",
            headers=config.auth_headers,
            json_body={"reason": config.promotion_reason},
            acceptable_statuses=(_HTTP_OK,),
            timeout_seconds=_request_timeout_seconds(config),
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    metadata = _dict_value(_dict_value(response_payload).get("metadata"))
    status = "completed" if not errors else "failed"
    return {
        "step_key": "proposal_promotion",
        "status": status,
        "proposal_id": proposal_id,
        "runtime_seconds": _round_float(time.perf_counter() - started_at_seconds),
        "graph_claim_id": _maybe_string(metadata.get("graph_claim_id")),
        "graph_relation_id": _maybe_string(metadata.get("graph_relation_id")),
        "response": response_payload,
        "errors": errors,
    }


def _resolve_bootstrap_proposal_id(
    *,
    config: LiveEvidenceSessionAuditConfig,
    client: httpx.Client,
    space_id: str,
    bootstrap_step: JSONObject | None,
) -> str | None:
    step_payload = _dict_value(_dict_value(bootstrap_step).get("result_payload"))
    proposal_ids = _bootstrap_linked_proposal_ids(step_payload)
    if proposal_ids:
        return proposal_ids[0]
    run_id = _maybe_string(_dict_value(bootstrap_step).get("run_id"))
    query_param_sets: list[dict[str, str]] = []
    if run_id is not None:
        query_param_sets.append({"status": "pending_review", "run_id": run_id})
    query_param_sets.append({"status": "pending_review"})
    for query_params in query_param_sets:
        path = f"/v2/spaces/{space_id}/proposed-updates?{urlencode(query_params)}"
        try:
            response_payload = _request_json(
                client=client,
                method="GET",
                path=path,
                headers=config.auth_headers,
                timeout_seconds=_request_timeout_seconds(config),
            )
        except Exception as exc:  # noqa: BLE001
            if not _is_transient_request_error(exc):
                raise
            continue
        proposals = _list_of_dicts(response_payload.get("proposals"))
        candidate_claims = [
            proposal
            for proposal in proposals
            if _maybe_string(proposal.get("proposal_type")) == "candidate_claim"
        ]
        selected = (
            candidate_claims[0]
            if candidate_claims
            else (proposals[0] if proposals else None)
        )
        proposal_id = _maybe_string(_dict_value(selected).get("id"))
        if proposal_id is not None:
            return proposal_id
    return None


def _bootstrap_linked_proposal_ids(step_payload: JSONObject | None) -> list[str]:
    payload = _dict_value(step_payload)
    ordered_ids: list[str] = []
    seen_ids: set[str] = set()

    def _append(raw_value: object) -> None:
        proposal_id = _maybe_string(raw_value)
        if proposal_id is None or proposal_id in seen_ids:
            return
        seen_ids.add(proposal_id)
        ordered_ids.append(proposal_id)

    claim_curation = _dict_value(payload.get("claim_curation"))
    for proposal_id in _string_list(claim_curation.get("proposal_ids")):
        _append(proposal_id)

    research_state = _dict_value(payload.get("research_state"))
    research_state_metadata = _dict_value(research_state.get("metadata"))
    research_state_claim_curation = _dict_value(
        research_state_metadata.get("claim_curation"),
    )
    for proposal_id in _string_list(research_state_claim_curation.get("proposal_ids")):
        _append(proposal_id)

    research_brief = _dict_value(payload.get("research_brief"))
    top_candidate_claims = _list_of_dicts(research_brief.get("top_candidate_claims"))
    for candidate_claim in top_candidate_claims:
        _append(candidate_claim.get("proposal_id"))

    return ordered_ids


def _wait_for_graph_claim_audit(  # noqa: PLR0913
    *,
    config: LiveEvidenceSessionAuditConfig,
    client: httpx.Client,
    space_id: str,
    proposal_id: str | None,
    promotion_step: JSONObject | None,
    baseline_claim_total: int,
) -> JSONObject:
    graph_claim_id = _maybe_string(_dict_value(promotion_step).get("graph_claim_id"))
    expected_source_document_ref = (
        f"harness_proposal:{proposal_id}" if proposal_id is not None else None
    )
    deadline = time.monotonic() + config.graph_settle_seconds
    last_audit = _build_graph_audit(
        baseline_claim_total=baseline_claim_total,
        final_claim_total=baseline_claim_total,
        target_claim=None,
        evidence_payload=None,
        graph_claim_id=graph_claim_id,
        expected_source_document_ref=expected_source_document_ref,
    )
    while time.monotonic() <= deadline:
        try:
            claims_payload = _list_all_graph_claims(
                client=client,
                headers=config.auth_headers,
                space_id=space_id,
                request_timeout_seconds=_request_timeout_seconds(config),
            )
            claims = _list_of_dicts(claims_payload.get("claims"))
            target_claim = _locate_target_claim(
                claims=claims,
                graph_claim_id=graph_claim_id,
                expected_source_document_ref=expected_source_document_ref,
            )
            evidence_payload = None
            if target_claim is not None:
                claim_id = _maybe_string(target_claim.get("id"))
                if claim_id is not None:
                    evidence_payload = _request_json(
                        client=client,
                        method="GET",
                        path=(
                            f"/v2/spaces/{space_id}/evidence-map/claims/{claim_id}/evidence"
                        ),
                        headers=config.auth_headers,
                        timeout_seconds=_request_timeout_seconds(config),
                    )
            last_audit = _build_graph_audit(
                baseline_claim_total=baseline_claim_total,
                final_claim_total=_int_value(claims_payload.get("total")),
                target_claim=target_claim,
                evidence_payload=evidence_payload,
                graph_claim_id=graph_claim_id,
                expected_source_document_ref=expected_source_document_ref,
            )
            if (
                last_audit["target_claim_found"] is True
                and _int_value(last_audit.get("evidence_total")) > 0
            ):
                return last_audit
        except Exception as exc:  # noqa: BLE001
            if not _is_transient_request_error(exc):
                last_audit = dict(last_audit)
                last_audit["errors"] = [*(_string_list(last_audit.get("errors"))), str(exc)]
                return last_audit
        time.sleep(config.poll_interval_seconds)
    return last_audit


def _build_graph_audit(  # noqa: PLR0913
    *,
    baseline_claim_total: int,
    final_claim_total: int,
    target_claim: JSONObject | None,
    evidence_payload: JSONObject | None,
    graph_claim_id: str | None,
    expected_source_document_ref: str | None,
) -> JSONObject:
    evidence_rows = _list_of_dicts(_dict_value(evidence_payload).get("evidence"))
    claim = _dict_value(target_claim)
    source_document_ref = _maybe_string(claim.get("source_document_ref"))
    evidence_source_refs = [
        ref
        for ref in (
            _maybe_string(evidence.get("source_document_ref")) for evidence in evidence_rows
        )
        if ref is not None
    ]
    errors: list[str] = []
    if graph_claim_id is not None and _maybe_string(claim.get("id")) not in {None, graph_claim_id}:
        errors.append(
            f"Promoted graph claim '{graph_claim_id}' was not visible in graph-explorer reads.",
        )
    if expected_source_document_ref is not None and source_document_ref not in {
        None,
        expected_source_document_ref,
    }:
        errors.append(
            "Promoted claim source_document_ref did not match the promoted proposal.",
        )
    if evidence_rows and expected_source_document_ref is not None and expected_source_document_ref not in evidence_source_refs:
        errors.append(
            "Claim evidence rows did not preserve the promoted proposal source_document_ref.",
        )
    return {
        "baseline_claim_total": baseline_claim_total,
        "final_claim_total": final_claim_total,
        "claim_delta": max(final_claim_total - baseline_claim_total, 0),
        "promoted_graph_claim_id": graph_claim_id,
        "expected_source_document_ref": expected_source_document_ref,
        "target_claim_found": bool(claim),
        "claim_id": _maybe_string(claim.get("id")),
        "claim_status": _maybe_string(claim.get("claim_status")),
        "validation_state": _maybe_string(claim.get("validation_state")),
        "persistability": _maybe_string(claim.get("persistability")),
        "relation_type": _maybe_string(claim.get("relation_type")),
        "source_label": _maybe_string(claim.get("source_label")),
        "target_label": _maybe_string(claim.get("target_label")),
        "source_document_ref": source_document_ref,
        "evidence_total": _int_value(_dict_value(evidence_payload).get("total")),
        "evidence_source_document_refs": evidence_source_refs,
        "errors": errors,
    }


def build_live_evidence_session_audit_report(
    *,
    config: LiveEvidenceSessionAuditConfig,
    session_reports: Sequence[JSONObject],
) -> JSONObject:
    reports = [dict(report) for report in session_reports]
    suspicious_log_lines = sum(
        _int_value(summary.get("suspicious_line_count"))
        for report in reports
        for summary in _list_of_dicts(report.get("logs"))
    )
    graph_claim_deltas = sum(
        _int_value(_dict_value(report.get("graph_audit")).get("claim_delta"))
        for report in reports
    )
    graph_evidence_rows = sum(
        _int_value(_dict_value(report.get("graph_audit")).get("evidence_total"))
        for report in reports
    )
    completed_sessions = sum(
        1 for report in reports if _maybe_string(report.get("status")) == "completed"
    )
    failed_sessions = len(reports) - completed_sessions
    all_errors = [
        error
        for report in reports
        for error in _string_list(report.get("errors"))
    ]
    return {
        "session_kind": _DEFAULT_SESSION_KIND,
        "label": config.label,
        "base_url": config.base_url,
        "requested_session_count": len(config.space_ids) * config.repeat_count,
        "completed_sessions": completed_sessions,
        "failed_sessions": failed_sessions,
        "graph_claim_deltas": graph_claim_deltas,
        "graph_evidence_rows": graph_evidence_rows,
        "suspicious_log_lines": suspicious_log_lines,
        "all_passed": failed_sessions == 0,
        "errors": all_errors,
        "sessions": reports,
    }


def write_live_evidence_session_audit_report(
    *,
    report: JSONObject,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir = output_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    for session in _list_of_dicts(report.get("sessions")):
        label = _maybe_string(session.get("session_label")) or "session"
        session_path = sessions_dir / f"{_safe_filename(label)}.json"
        session_path.write_text(
            json.dumps(session, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

    summary_json_path = output_dir / "summary.json"
    summary_md_path = output_dir / "summary.md"
    summary_json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    summary_md_path.write_text(
        render_live_evidence_session_audit_markdown(report),
        encoding="utf-8",
    )
    return {
        "summary_json": str(summary_json_path),
        "summary_markdown": str(summary_md_path),
    }


def render_live_evidence_session_audit_markdown(report: JSONObject) -> str:
    lines = [
        "# Live Evidence Session Audit",
        "",
        f"- All passed: {'yes' if report.get('all_passed') is True else 'no'}",
        f"- Completed sessions: {_int_value(report.get('completed_sessions'))}",
        f"- Failed sessions: {_int_value(report.get('failed_sessions'))}",
        f"- Graph claim delta: {_int_value(report.get('graph_claim_deltas'))}",
        f"- Graph evidence rows: {_int_value(report.get('graph_evidence_rows'))}",
        f"- Suspicious log lines: {_int_value(report.get('suspicious_log_lines'))}",
        "",
        "## Sessions",
        "",
    ]
    for session in _list_of_dicts(report.get("sessions")):
        graph_audit = _dict_value(session.get("graph_audit"))
        lines.extend(
            [
                f"### {_maybe_string(session.get('session_label')) or 'session'}",
                f"- Status: {_maybe_string(session.get('status')) or 'unknown'}",
                f"- Space: {_maybe_string(session.get('space_id')) or 'unknown'}",
                f"- Claim delta: {_int_value(graph_audit.get('claim_delta'))}",
                f"- Evidence rows: {_int_value(graph_audit.get('evidence_total'))}",
            ]
        )
        session_errors = _string_list(session.get("errors"))
        if session_errors:
            lines.append("- Errors:")
            for error in session_errors:
                lines.append(f"  - {error}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _request_timeout_seconds(config: LiveEvidenceSessionAuditConfig) -> float:
    return max(
        1.0,
        min(config.poll_timeout_seconds, _DEFAULT_REQUEST_TIMEOUT_SECONDS),
    )


def _fetch_run_diagnostics(  # noqa: PLR0913
    *,
    client: httpx.Client,
    headers: dict[str, str],
    space_id: str,
    run_id: str,
    interval_seconds: float,
    request_timeout_seconds: float,
) -> tuple[JSONObject | None, JSONObject | None, JSONObject | None]:
    workspace_payload, artifacts_payload = _fetch_terminal_run_payloads(
        client=client,
        headers=headers,
        space_id=space_id,
        run_id=run_id,
        interval_seconds=interval_seconds,
        request_timeout_seconds=request_timeout_seconds,
        timeout_seconds=max(interval_seconds, _DEFAULT_REQUEST_TIMEOUT_SECONDS),
    )
    events_payload = _optional_json_request(
        client=client,
        method="GET",
        path=f"/v2/spaces/{space_id}/tasks/{run_id}/events",
        headers=headers,
        timeout_seconds=request_timeout_seconds,
    )
    return workspace_payload, artifacts_payload, events_payload


def _primary_payload_from_workspace_artifacts(
    *,
    workspace_payload: JSONObject | None,
    artifacts_payload: JSONObject | None,
) -> JSONObject | None:
    workspace_snapshot = _working_state_snapshot(workspace_payload)
    primary_result_key = _maybe_string(workspace_snapshot.get("primary_result_key"))
    if primary_result_key is None:
        return None
    artifact_list = _output_list(artifacts_payload)
    artifacts_by_key = _artifact_contents_by_key(artifact_list)
    payload = _dict_value(artifacts_by_key.get(primary_result_key))
    return payload or None


def _step_report(  # noqa: PLR0913
    *,
    step_key: str,
    request_payload: JSONObject,
    queued_response: JSONObject | None,
    run_payload: JSONObject | None,
    progress_payload: JSONObject | None,
    workspace_payload: JSONObject | None,
    artifacts_payload: JSONObject | None,
    events_payload: JSONObject | None,
    result_payload: JSONObject | None,
    runtime_seconds: float,
    timed_out: bool,
    completed_during_timeout_grace: bool,
    errors: list[str],
    run_id: str | None,
) -> JSONObject:
    status = "completed"
    run_status = _maybe_string(_dict_value(run_payload).get("status"))
    if timed_out or errors or run_status not in {
        None,
        _SUCCESS_RUN_STATUS,
    }:
        status = "failed"
    artifact_keys = [
        key
        for key in (
            _maybe_string(artifact.get("key"))
            for artifact in _output_list(artifacts_payload)
        )
        if key is not None
    ]
    return {
        "step_key": step_key,
        "status": status,
        "run_id": run_id,
        "run_status": run_status,
        "timed_out": timed_out,
        "completed_during_timeout_grace": completed_during_timeout_grace,
        "runtime_seconds": _round_float(runtime_seconds),
        "artifact_keys": artifact_keys,
        "request_payload": request_payload,
        "queued_response": queued_response,
        "run_payload": run_payload,
        "progress_payload": progress_payload,
        "workspace_payload": workspace_payload,
        "artifacts_payload": artifacts_payload,
        "events_payload": events_payload,
        "result_payload": result_payload,
        "errors": errors,
    }


def _start_log_monitors(
    *,
    config: LiveEvidenceSessionAuditConfig,
    session_dir: Path,
) -> list[_LogCommandMonitor]:
    error_patterns = tuple(
        re.compile(pattern) for pattern in config.log_error_patterns if pattern.strip()
    )
    ignore_patterns = tuple(
        re.compile(pattern) for pattern in config.log_ignore_patterns if pattern.strip()
    )
    monitors: list[_LogCommandMonitor] = []
    for index, command in enumerate(config.log_commands, start=1):
        output_path = session_dir / "logs" / f"{index:02d}_{_safe_filename(command.name)}.log"
        monitor = _LogCommandMonitor(
            config=command,
            output_path=output_path,
            error_patterns=error_patterns,
            ignore_patterns=ignore_patterns,
        )
        monitor.start()
        monitors.append(monitor)
    return monitors


def _stop_log_monitors(monitors: Sequence[_LogCommandMonitor]) -> list[JSONObject]:
    summaries: list[JSONObject] = []
    for monitor in monitors:
        monitor.stop()
        summaries.append(monitor.summary())
    return summaries


def _graph_claim_total(
    *,
    client: httpx.Client,
    headers: dict[str, str],
    space_id: str,
    request_timeout_seconds: float,
) -> int:
    payload = _request_json(
        client=client,
        method="GET",
        path=f"/v2/spaces/{space_id}/evidence-map/claims?offset=0&limit=1",
        headers=headers,
        timeout_seconds=request_timeout_seconds,
    )
    return _int_value(payload.get("total"))


def _list_all_graph_claims(
    *,
    client: httpx.Client,
    headers: dict[str, str],
    space_id: str,
    request_timeout_seconds: float,
    limit: int = 200,
) -> JSONObject:
    all_claims: list[JSONObject] = []
    offset = 0
    total = 0
    while True:
        payload = _request_json(
            client=client,
            method="GET",
            path=(
                f"/v2/spaces/{space_id}/evidence-map/claims?"
                f"offset={offset}&limit={limit}"
            ),
            headers=headers,
            timeout_seconds=request_timeout_seconds,
        )
        total = _int_value(payload.get("total"))
        claims = _list_of_dicts(payload.get("claims"))
        all_claims.extend(claims)
        offset += len(claims)
        if not claims or offset >= total:
            break
    return {"claims": all_claims, "total": total, "offset": 0, "limit": limit}


def _locate_target_claim(
    *,
    claims: Sequence[JSONObject],
    graph_claim_id: str | None,
    expected_source_document_ref: str | None,
) -> JSONObject | None:
    if graph_claim_id is not None:
        for claim in claims:
            if _maybe_string(claim.get("id")) == graph_claim_id:
                return dict(claim)
    if expected_source_document_ref is not None:
        for claim in claims:
            if _maybe_string(claim.get("source_document_ref")) == expected_source_document_ref:
                return dict(claim)
    return None


def _graph_audit_errors(
    graph_audit: JSONObject | None,
    *,
    require_graph_activity: bool,
) -> list[str]:
    payload = _dict_value(graph_audit)
    errors = _string_list(payload.get("errors"))
    if require_graph_activity:
        if _int_value(payload.get("claim_delta")) <= 0:
            errors.append("No graph claim delta was observed after promotion.")
        if payload.get("target_claim_found") is not True:
            errors.append("Promoted claim was not visible through graph-explorer.")
        if _int_value(payload.get("evidence_total")) <= 0:
            errors.append("Promoted claim did not expose any claim_evidence rows.")
    return errors


def _step_errors(step_payload: JSONObject | None) -> list[str]:
    payload = _dict_value(step_payload)
    return _string_list(payload.get("errors"))


def _request_json_with_status(  # noqa: PLR0913
    *,
    client: httpx.Client,
    method: str,
    path: str,
    headers: dict[str, str],
    json_body: JSONObject | None = None,
    acceptable_statuses: tuple[int, ...] = (_HTTP_OK,),
    timeout_seconds: float | None = None,
) -> tuple[int, JSONObject]:
    response = client.request(
        method=method,
        url=path,
        headers=headers,
        json=json_body,
        timeout=timeout_seconds,
    )
    if response.status_code not in acceptable_statuses:
        detail = response.text.strip()
        raise RuntimeError(
            f"{method} {path} returned HTTP {response.status_code}: {detail}",
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError(f"{method} {path} returned a non-object JSON payload")
    return response.status_code, dict(payload)


def _normalize_log_commands(values: list[str]) -> tuple[LogCommandConfig, ...]:
    commands: list[LogCommandConfig] = []
    for index, raw_value in enumerate(values, start=1):
        command = raw_value.strip()
        if command == "":
            continue
        first_token = command.split()[0]
        commands.append(
            LogCommandConfig(
                command=command,
                name=f"log-command-{index}-{first_token}",
            ),
        )
    return tuple(commands)


def _normalize_string_tuple(values: list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        stripped = value.strip()
        if stripped and stripped not in normalized:
            normalized.append(stripped)
    return tuple(normalized)


def _session_label(
    *,
    config: LiveEvidenceSessionAuditConfig,
    space_id: str,
    repeat_index: int,
) -> str:
    base = config.label or "live-evidence-session"
    return f"{base}:{space_id}:repeat-{repeat_index}"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip() != ""]


def _int_value(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _required_string(payload: JSONObject, key: str, label: str) -> str:
    value = _maybe_string(payload.get(key))
    if value is None:
        raise RuntimeError(f"{label} is missing required field '{key}'")
    return value


def _load_environment_overrides() -> list[str]:
    loaded_keys: list[str] = []
    for env_path in _DEFAULT_ENV_FILES:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line.removeprefix("export ").strip()
            if "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            normalized_key = key.strip()
            if not normalized_key:
                continue
            existing = os.getenv(normalized_key)
            if isinstance(existing, str) and existing.strip():
                continue
            value = raw_value.strip()
            if (
                len(value) >= _QUOTED_ENV_MIN_LENGTH
                and value[0] == value[-1]
                and value[0] in {'"', "'"}
            ):
                value = value[1:-1]
            os.environ[normalized_key] = value
            loaded_keys.append(normalized_key)
    return loaded_keys


def _load_sources_preferences(raw_value: str) -> dict[str, bool] | None:
    value = raw_value.strip()
    if value == "":
        return None
    path = _REPO_ROOT / value if not Path(value).is_absolute() else Path(value)
    payload_text = path.read_text(encoding="utf-8") if path.exists() else value
    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise SystemExit("--sources-json must resolve to a JSON object.")
    normalized: dict[str, bool] = {}
    for key, raw_enabled in payload.items():
        if not isinstance(key, str) or key.strip() == "":
            raise SystemExit("--sources-json contains an invalid source key.")
        if not isinstance(raw_enabled, bool):
            raise SystemExit("--sources-json values must be booleans.")
        normalized[key.strip()] = raw_enabled
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())
