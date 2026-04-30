"""Value normalization helpers for live evidence session audits."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.full_ai_real_space_canary.utils import _maybe_string
from scripts.live_evidence_session_audit.constants import (
    _DEFAULT_ENV_FILES,
    _QUOTED_ENV_MIN_LENGTH,
    _REPO_ROOT,
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject

    from scripts.live_evidence_session_audit.models import (
        LiveEvidenceSessionAuditConfig,
    )


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


__all__ = [
    "_int_value",
    "_load_environment_overrides",
    "_load_sources_preferences",
    "_normalize_string_tuple",
    "_required_string",
    "_session_label",
    "_string_list",
]
