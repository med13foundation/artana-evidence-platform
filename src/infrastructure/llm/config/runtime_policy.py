"""Runtime replay/version policy loaded from ``artana.toml``."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from src.infrastructure.llm.config.model_registry import DEFAULT_CONFIG_PATH

ReplayPolicy = Literal["strict", "allow_prompt_drift", "fork_on_drift"]

_RUNTIME_SECTION = "runtime"
_DEFAULT_REPLAY_POLICY: ReplayPolicy = "fork_on_drift"
_DEFAULT_EXTRACTION_CONFIG_VERSION = "v1"


@dataclass(frozen=True)
class ArtanaRuntimePolicy:
    """Global runtime settings that must remain deterministic across runs."""

    replay_policy: ReplayPolicy = _DEFAULT_REPLAY_POLICY
    extraction_config_version: str = _DEFAULT_EXTRACTION_CONFIG_VERSION
    context_system_prompt_hash: str | None = None
    context_builder_version: str | None = None
    context_compaction_version: str | None = None

    def to_context_version(self) -> object | None:
        """Build an optional Artana ``ContextVersion`` value from configured fields."""
        if (
            self.context_system_prompt_hash is None
            and self.context_builder_version is None
            and self.context_compaction_version is None
        ):
            return None
        try:
            from artana.kernel import ContextVersion
        except ImportError:
            return None
        return ContextVersion(
            system_prompt_hash=self.context_system_prompt_hash,
            context_builder_version=self.context_builder_version,
            compaction_version=self.context_compaction_version,
        )


@lru_cache(maxsize=1)
def load_runtime_policy(config_path: str | None = None) -> ArtanaRuntimePolicy:
    """Load runtime replay/version policy from file + environment overrides."""
    config = _read_artana_toml(config_path)
    runtime_section = config.get(_RUNTIME_SECTION, {})
    if not isinstance(runtime_section, Mapping):
        runtime_section = {}

    replay_policy = _resolve_replay_policy(
        os.getenv("ARTANA_REPLAY_POLICY"),
        runtime_section.get("replay_policy"),
    )
    extraction_config_version = _resolve_extraction_config_version(
        os.getenv("ARTANA_EXTRACTION_CONFIG_VERSION"),
        runtime_section.get("extraction_config_version"),
    )
    context_system_prompt_hash = _resolve_optional_string(
        os.getenv("ARTANA_CONTEXT_SYSTEM_PROMPT_HASH"),
        runtime_section.get("context_system_prompt_hash"),
    )
    context_builder_version = _resolve_optional_string(
        os.getenv("ARTANA_CONTEXT_BUILDER_VERSION"),
        runtime_section.get("context_builder_version"),
    )
    context_compaction_version = _resolve_optional_string(
        os.getenv("ARTANA_CONTEXT_COMPACTION_VERSION"),
        runtime_section.get("context_compaction_version"),
    )
    return ArtanaRuntimePolicy(
        replay_policy=replay_policy,
        extraction_config_version=extraction_config_version,
        context_system_prompt_hash=context_system_prompt_hash,
        context_builder_version=context_builder_version,
        context_compaction_version=context_compaction_version,
    )


def _read_artana_toml(config_path: str | None = None) -> dict[str, object]:
    path = Path(config_path) if config_path else Path(DEFAULT_CONFIG_PATH)
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


def _resolve_extraction_config_version(
    env_value: str | None,
    config_value: object,
) -> str:
    for raw_value in (env_value, config_value):
        if not isinstance(raw_value, str):
            continue
        normalized = raw_value.strip()
        if normalized:
            return normalized
    return _DEFAULT_EXTRACTION_CONFIG_VERSION


def _resolve_optional_string(
    env_value: str | None,
    config_value: object,
) -> str | None:
    for raw_value in (env_value, config_value):
        if not isinstance(raw_value, str):
            continue
        normalized = raw_value.strip()
        if normalized:
            return normalized
    return None


__all__ = ["ArtanaRuntimePolicy", "ReplayPolicy", "load_runtime_policy"]
