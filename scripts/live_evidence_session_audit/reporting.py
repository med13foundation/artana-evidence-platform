"""Report rendering and writing for live evidence session audits."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.full_ai_real_space_canary.utils import (
    _dict_value,
    _list_of_dicts,
    _maybe_string,
    _safe_filename,
)
from scripts.live_evidence_session_audit.constants import _DEFAULT_SESSION_KIND
from scripts.live_evidence_session_audit.values import _int_value, _string_list

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject

    from scripts.live_evidence_session_audit.models import (
        LiveEvidenceSessionAuditConfig,
    )


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
        error for report in reports for error in _string_list(report.get("errors"))
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
            ],
        )
        session_errors = _string_list(session.get("errors"))
        if session_errors:
            lines.append("- Errors:")
            for error in session_errors:
                lines.append(f"  - {error}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "build_live_evidence_session_audit_report",
    "render_live_evidence_session_audit_markdown",
    "write_live_evidence_session_audit_report",
]
