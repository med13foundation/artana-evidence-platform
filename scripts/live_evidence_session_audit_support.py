"""Support helpers for the live evidence session audit script."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    import httpx

from scripts.run_full_ai_real_space_canary import (
    _dict_value,
    _list_of_dicts,
    _maybe_string,
    _request_json,
    _safe_filename,
)

try:
    from artana_evidence_api.types.common import JSONObject
except ModuleNotFoundError:  # pragma: no cover - import path is set by caller script
    JSONObject = dict[str, object]  # type: ignore[misc,assignment]

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_LOG_TAIL_LINES = 80
_DEFAULT_SESSION_KIND = "live_evidence_session_audit"
_HTTP_OK = 200
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
