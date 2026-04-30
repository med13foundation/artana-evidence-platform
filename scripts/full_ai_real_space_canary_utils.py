"""HTTP and normalization helpers for the live full-AI canary script."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import httpx

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject
    from run_full_ai_real_space_canary import LiveCanaryMode, RealSpaceCanaryConfig

ReportMode = Literal["standard", "canary"]
_REPO_ROOT = Path(__file__).resolve().parents[1]
_BASE_URL_ENV = "ARTANA_EVIDENCE_API_LIVE_BASE_URL"
_API_KEY_ENV = "ARTANA_EVIDENCE_API_KEY"
_BEARER_TOKEN_ENV = "ARTANA_EVIDENCE_API_BEARER_TOKEN"
_DEFAULT_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
_DEFAULT_TEST_USER_EMAIL = "researcher@example.com"
_DEFAULT_TEST_USER_ROLE = "researcher"
_DEFAULT_POLL_REQUEST_TIMEOUT_SECONDS = 15.0
_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_UNAUTHORIZED = 401
_HTTP_NOT_FOUND = 404
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




__all__ = [name for name in globals() if name.startswith("_")]
