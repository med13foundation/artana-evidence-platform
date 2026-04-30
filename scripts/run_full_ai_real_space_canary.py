#!/usr/bin/env python3
"""Compatibility entrypoint for the full-AI real-space canary script."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.full_ai_real_space_canary.reporting import (  # noqa: E402
    _extract_guarded_payloads,
    _proof_metrics,
    _readiness_metrics,
    render_real_space_canary_markdown,
    write_real_space_canary_report,
)
from scripts.full_ai_real_space_canary.runner import (  # noqa: E402
    LiveCanaryMode,
    RealSpaceCanaryConfig,
    _execute_live_run,
    _fetch_terminal_run_payloads,
    _guarded_payloads_need_stabilization,
    _poll_terminal_run,
    _poll_terminal_run_with_grace,
    _recover_queued_run_by_title,
    _round_float,
    _run_runtime_seconds,
    _safe_filename,
    _stabilize_guarded_payloads,
    _terminal_grace_reconciliation,
    main,
    parse_args,
    run_real_space_canary,
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
    _normalize_seed_terms,
    _normalize_space_ids,
    _optional_json_request,
    _output_list,
    _request_json,
    _resolve_auth_headers,
    _resolve_path,
    _task_payload,
    _working_state_snapshot,
)

__all__ = [
    "LiveCanaryMode",
    "RealSpaceCanaryConfig",
    "_artifact_contents_by_key",
    "_dict_value",
    "_execute_live_run",
    "_extract_guarded_payloads",
    "_fetch_terminal_run_payloads",
    "_guarded_payloads_need_stabilization",
    "_int_value",
    "_is_transient_request_error",
    "_list_of_dicts",
    "_load_sources_preferences",
    "_maybe_string",
    "_normalize_expected_run_count",
    "_normalize_positive_float",
    "_normalize_positive_int",
    "_normalize_seed_terms",
    "_normalize_space_ids",
    "_optional_json_request",
    "_output_list",
    "_poll_terminal_run",
    "_poll_terminal_run_with_grace",
    "_proof_metrics",
    "_readiness_metrics",
    "_recover_queued_run_by_title",
    "_request_json",
    "_resolve_auth_headers",
    "_resolve_path",
    "_round_float",
    "_run_runtime_seconds",
    "_safe_filename",
    "_stabilize_guarded_payloads",
    "_task_payload",
    "_terminal_grace_reconciliation",
    "_working_state_snapshot",
    "main",
    "parse_args",
    "render_real_space_canary_markdown",
    "run_real_space_canary",
    "write_real_space_canary_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
