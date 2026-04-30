"""Payload extraction and report-shaping helpers for the live canary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from scripts.full_ai_real_space_canary.constants import (
    _ACTION_DEFAULT_SOURCE_KEYS,
    _CONTEXT_ONLY_SOURCE_KEYS,
    _GROUNDING_SOURCE_KEYS,
    _RESERVED_SOURCE_KEYS,
)
from scripts.full_ai_real_space_canary.json_values import (
    _dict_value,
    _int_value,
    _list_of_dicts,
    _maybe_string,
    _parse_datetime,
    _string_list,
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject

    from scripts.full_ai_real_space_canary.runner import (
        LiveCanaryMode,
        RealSpaceCanaryConfig,
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


def _artifact_contents_by_key(artifact_list: list[JSONObject]) -> dict[str, JSONObject]:
    contents: dict[str, JSONObject] = {}
    for artifact in artifact_list:
        key = _maybe_string(artifact.get("key"))
        content = _dict_value(artifact.get("content"))
        if key is None or not content:
            continue
        contents[key] = content
    return contents


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


__all__ = [
    "_artifact_contents_by_key",
    "_build_run_matrix",
    "_build_run_title",
    "_output_list",
    "_proof_recommended_source_key",
    "_proof_source_policy_violation_category",
    "_research_init_request_payload",
    "_run_label",
    "_run_runtime_seconds",
    "_task_payload",
    "_working_state_snapshot",
]
