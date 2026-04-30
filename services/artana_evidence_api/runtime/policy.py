"""Runtime governance and replay policy configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from artana_evidence_api.runtime.config import (
    _DEFAULT_REPLAY_POLICY,
    ReplayPolicy,
    _read_artana_toml,
    _resolve_optional_string,
    _resolve_replay_policy,
    _resolve_string,
)


@dataclass(frozen=True)
class UsageLimits:
    """Usage limits for graph-harness runtime operations."""

    total_cost_usd: float | None = None
    max_turns: int | None = None
    max_tokens: int | None = None

    @classmethod
    def from_environment(cls) -> UsageLimits:
        cost_raw = os.getenv("ARTANA_USAGE_COST_LIMIT")
        turns_raw = os.getenv("ARTANA_USAGE_MAX_TURNS")
        tokens_raw = os.getenv("ARTANA_USAGE_MAX_TOKENS")
        return cls(
            total_cost_usd=float(cost_raw) if cost_raw else 1.0,
            max_turns=int(turns_raw) if turns_raw else 10,
            max_tokens=int(tokens_raw) if tokens_raw else 8192,
        )


@dataclass(frozen=True)
class GovernanceConfig:
    """Minimal governance settings used by graph-harness runtimes."""

    usage_limits: UsageLimits = field(default_factory=UsageLimits.from_environment)

    @classmethod
    def from_environment(cls) -> GovernanceConfig:
        return cls(usage_limits=UsageLimits.from_environment())


@dataclass(frozen=True)
class ArtanaRuntimePolicy:
    """Global runtime settings that must remain deterministic across runs."""

    replay_policy: ReplayPolicy = _DEFAULT_REPLAY_POLICY
    extraction_config_version: str = "v1"
    context_system_prompt_hash: str | None = None
    context_builder_version: str | None = None
    context_compaction_version: str | None = None


@lru_cache(maxsize=1)
def load_runtime_policy(config_path: str | None = None) -> ArtanaRuntimePolicy:
    config = _read_artana_toml(config_path)
    runtime_section = config.get("runtime", {})
    if not isinstance(runtime_section, dict):
        runtime_section = {}
    replay_policy = _resolve_replay_policy(
        os.getenv("ARTANA_REPLAY_POLICY"),
        runtime_section.get("replay_policy"),
    )
    return ArtanaRuntimePolicy(
        replay_policy=replay_policy,
        extraction_config_version=_resolve_string(
            os.getenv("ARTANA_EXTRACTION_CONFIG_VERSION"),
            runtime_section.get("extraction_config_version"),
            default="v1",
        ),
        context_system_prompt_hash=_resolve_optional_string(
            os.getenv("ARTANA_CONTEXT_SYSTEM_PROMPT_HASH"),
            runtime_section.get("context_system_prompt_hash"),
        ),
        context_builder_version=_resolve_optional_string(
            os.getenv("ARTANA_CONTEXT_BUILDER_VERSION"),
            runtime_section.get("context_builder_version"),
        ),
        context_compaction_version=_resolve_optional_string(
            os.getenv("ARTANA_CONTEXT_COMPACTION_VERSION"),
            runtime_section.get("context_compaction_version"),
        ),
    )


__all__ = [
    "ArtanaRuntimePolicy",
    "GovernanceConfig",
    "ReplayPolicy",
    "UsageLimits",
    "load_runtime_policy",
]
