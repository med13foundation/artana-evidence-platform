"""Configuration parsing and scalar helpers for runtime support."""

from __future__ import annotations

import hashlib
import os
import tomllib
from pathlib import Path
from typing import Literal

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "artana.toml"
_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})

ReplayPolicy = Literal["strict", "allow_prompt_drift", "fork_on_drift"]
_DEFAULT_REPLAY_POLICY: ReplayPolicy = "fork_on_drift"


def _read_artana_toml(config_path: str | None = None) -> dict[str, object]:
    path = Path(config_path) if config_path else _CONFIG_PATH
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        loaded = tomllib.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _resolve_replay_policy(
    env_value: str | None,
    config_value: object,
) -> ReplayPolicy:
    for raw_value in (env_value, config_value):
        normalized = _normalize_replay_policy(raw_value)
        if normalized is not None:
            return normalized
    return _DEFAULT_REPLAY_POLICY


def _normalize_replay_policy(raw_value: object) -> ReplayPolicy | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip().lower()
    if normalized == "strict":
        return "strict"
    if normalized == "allow_prompt_drift":
        return "allow_prompt_drift"
    if normalized == "fork_on_drift":
        return "fork_on_drift"
    return None


def _resolve_string(
    env_value: str | None,
    config_value: object,
    *,
    default: str,
) -> str:
    for raw_value in (env_value, config_value):
        if isinstance(raw_value, str):
            normalized = raw_value.strip()
            if normalized:
                return normalized
    return default


def _resolve_optional_string(env_value: str | None, config_value: object) -> str | None:
    for raw_value in (env_value, config_value):
        if isinstance(raw_value, str):
            normalized = raw_value.strip()
            if normalized:
                return normalized
    return None


def resolve_configured_openai_api_key() -> str | None:
    raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("ARTANA_OPENAI_API_KEY")
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized or normalized.lower() in _INVALID_OPENAI_KEYS:
        return None
    return normalized


def has_configured_openai_api_key() -> bool:
    return resolve_configured_openai_api_key() is not None


def stable_sha256_digest(payload: str, *, length: int = 24) -> str:
    normalized_length = max(length, 1)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:normalized_length]


def normalize_litellm_model_id(model_id: str) -> str:
    """Convert registry provider:model ids into LiteLLM execution ids."""
    normalized = model_id.strip()
    if ":" not in normalized:
        return normalized
    provider, model_name = normalized.split(":", 1)
    if provider.strip() == "" or model_name.strip() == "":
        return normalized
    return f"{provider.strip()}/{model_name.strip()}"


__all__ = [
    "ReplayPolicy",
    "_CONFIG_PATH",
    "_DEFAULT_REPLAY_POLICY",
    "_INVALID_OPENAI_KEYS",
    "_normalize_replay_policy",
    "_read_artana_toml",
    "_resolve_optional_string",
    "_resolve_replay_policy",
    "_resolve_string",
    "has_configured_openai_api_key",
    "normalize_litellm_model_id",
    "resolve_configured_openai_api_key",
    "stable_sha256_digest",
]
