#!/usr/bin/env python3
"""Compatibility entrypoint for the live evidence session audit script."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.live_evidence_session_audit.runner import (  # noqa: E402
    _bootstrap_linked_proposal_ids,
    _build_graph_audit,
    _config_from_args,
    _dict_value,
    _execute_bootstrap_run,
    _execute_queue_only_step,
    _execute_research_init_run,
    _execute_step_with_optional_sync_result,
    _fetch_run_diagnostics,
    _maybe_string,
    _normalize_positive_float,
    _normalize_positive_int,
    _primary_payload_from_workspace_artifacts,
    _promote_first_bootstrap_proposal,
    _request_timeout_seconds,
    _resolve_auth_headers,
    _resolve_bootstrap_proposal_id,
    _resolve_path,
    _round_float,
    _run_single_live_session,
    _safe_filename,
    _step_report,
    _wait_for_graph_claim_audit,
    main,
    parse_args,
    run_live_evidence_session_audit,
)
from scripts.live_evidence_session_audit.support import (  # noqa: E402
    LiveEvidenceSessionAuditConfig,
    LogCommandConfig,
    _graph_audit_errors,
    _graph_claim_total,
    _int_value,
    _list_all_graph_claims,
    _load_environment_overrides,
    _load_sources_preferences,
    _locate_target_claim,
    _normalize_log_commands,
    _normalize_string_tuple,
    _request_json_with_status,
    _required_string,
    _session_label,
    _start_log_monitors,
    _step_errors,
    _stop_log_monitors,
    _string_list,
    build_live_evidence_session_audit_report,
    render_live_evidence_session_audit_markdown,
    write_live_evidence_session_audit_report,
)

__all__ = [
    "LiveEvidenceSessionAuditConfig",
    "LogCommandConfig",
    "_bootstrap_linked_proposal_ids",
    "_build_graph_audit",
    "_config_from_args",
    "_dict_value",
    "_execute_bootstrap_run",
    "_execute_queue_only_step",
    "_execute_research_init_run",
    "_execute_step_with_optional_sync_result",
    "_fetch_run_diagnostics",
    "_graph_audit_errors",
    "_graph_claim_total",
    "_int_value",
    "_list_all_graph_claims",
    "_load_environment_overrides",
    "_load_sources_preferences",
    "_locate_target_claim",
    "_maybe_string",
    "_normalize_log_commands",
    "_normalize_positive_float",
    "_normalize_positive_int",
    "_normalize_string_tuple",
    "_primary_payload_from_workspace_artifacts",
    "_promote_first_bootstrap_proposal",
    "_request_json_with_status",
    "_request_timeout_seconds",
    "_required_string",
    "_resolve_auth_headers",
    "_resolve_bootstrap_proposal_id",
    "_resolve_path",
    "_round_float",
    "_run_single_live_session",
    "_safe_filename",
    "_session_label",
    "_start_log_monitors",
    "_step_errors",
    "_step_report",
    "_stop_log_monitors",
    "_string_list",
    "_wait_for_graph_claim_audit",
    "build_live_evidence_session_audit_report",
    "main",
    "parse_args",
    "render_live_evidence_session_audit_markdown",
    "run_live_evidence_session_audit",
    "write_live_evidence_session_audit_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
