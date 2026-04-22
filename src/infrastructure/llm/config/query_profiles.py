"""Source-specific query agent configuration loaded from artana.toml."""

from __future__ import annotations

import contextlib
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from src.infrastructure.llm.config.governance import UsageLimits
from src.infrastructure.llm.config.model_registry import DEFAULT_CONFIG_PATH

_SOURCE_PROFILES_SECTION = "source_profiles"
_MODEL_KEY = "model"
_USAGE_LIMITS_KEY = "usage_limits"
_USAGE_LIMITS_PROFILE_KEY = "budget_profile"
_DEFAULT_BUDGET_SECTION = "budgets"
_TIMEOUT_SECONDS_KEY = "timeout_seconds"


@dataclass(frozen=True)
class QuerySourcePolicy:
    """
    Per-source overrides for query generation runtime behavior.

    All fields are optional so this object can represent partial overrides.
    """

    model_id: str | None = None
    usage_limits: UsageLimits | None = None
    timeout_seconds: float | None = None


def load_query_source_policies(
    config_path: str | None = None,
) -> dict[str, QuerySourcePolicy]:
    """
    Load source-specific query policies from artana.toml.

    The expected config shape is:

    [source_profiles]
    [source_profiles.pubmed]
    model = "openai:gpt-4o-mini"

    [source_profiles.pubmed.usage_limits]
    total_cost_usd = 1.0
    max_turns = 10
    max_tokens = 8192
    """
    config = _read_artana_toml(config_path)
    raw_profiles = config.get(_SOURCE_PROFILES_SECTION, {})
    if not isinstance(raw_profiles, Mapping):
        return {}

    budgets = config.get(_DEFAULT_BUDGET_SECTION, {})
    if not isinstance(budgets, Mapping):
        budgets = {}

    policies: dict[str, QuerySourcePolicy] = {}
    for source_type_raw, raw_profile in raw_profiles.items():
        if not isinstance(source_type_raw, str):
            continue
        source_type = source_type_raw.strip().lower()
        if not source_type or not isinstance(raw_profile, Mapping):
            continue

        model_id = _coerce_string(raw_profile.get(_MODEL_KEY))
        usage_limits = _build_usage_limits(raw_profile, budgets)
        timeout_seconds = _coerce_optional_float(
            raw_profile.get(_TIMEOUT_SECONDS_KEY),
        )
        if model_id is None and usage_limits is None and timeout_seconds is None:
            continue

        policies[source_type] = QuerySourcePolicy(
            model_id=model_id,
            usage_limits=usage_limits,
            timeout_seconds=timeout_seconds,
        )

    return policies


def _build_usage_limits(
    raw_profile: Mapping[str, object],
    budgets: Mapping[str, object],
) -> UsageLimits | None:
    """
    Build usage limits from inline source overrides or shared budget profile.

    Priority:
    1. [source_profiles.<source>.usage_limits]
    2. [source_profiles.<source>.budget_profile] -> [budgets.<name>]
    """
    inline_limits = _coerce_usage_limits(raw_profile.get(_USAGE_LIMITS_KEY))
    if inline_limits is not None:
        return inline_limits

    profile_name = _coerce_string(raw_profile.get(_USAGE_LIMITS_PROFILE_KEY))
    if profile_name is None:
        return None
    budget_limits_raw = budgets.get(profile_name)
    return _coerce_usage_limits(budget_limits_raw)


def resolve_source_policy(
    source_type: str,
    config_path: str | None = None,
) -> QuerySourcePolicy | None:
    """
    Resolve a single source's policy by source type.
    Returns None if no explicit policy exists.
    """
    normalized = source_type.strip().lower()
    if not normalized:
        return None
    return load_query_source_policies(config_path).get(normalized)


def _read_artana_toml(config_path: str | None = None) -> dict[str, object]:
    """
    Read and parse artana.toml.
    """
    path = Path(config_path) if config_path else Path(DEFAULT_CONFIG_PATH)
    if not path.exists():
        return {}

    with path.open("rb") as handle:
        loaded = tomllib.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _coerce_usage_limits(
    raw_limits: object | None,
) -> UsageLimits | None:
    """
    Parse usage limit overrides into UsageLimits.
    """
    if not isinstance(raw_limits, Mapping):
        return None

    total_cost_usd = _coerce_optional_float(raw_limits.get("total_cost_usd"))
    max_turns = _coerce_optional_int(raw_limits.get("max_turns"))
    max_tokens = _coerce_optional_int(raw_limits.get("max_tokens"))

    if total_cost_usd is None and max_turns is None and max_tokens is None:
        return None

    return UsageLimits(
        total_cost_usd=total_cost_usd,
        max_turns=max_turns,
        max_tokens=max_tokens,
    )


def _coerce_optional_float(raw_value: object) -> float | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, int | float):
        return float(raw_value)
    if isinstance(raw_value, str):
        try:
            return float(raw_value)
        except ValueError:
            return None
    return None


def _coerce_optional_int(raw_value: object) -> int | None:
    parsed: int | None = None

    if raw_value is None or isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float) and raw_value.is_integer():
        return int(raw_value)
    if isinstance(raw_value, str):
        with contextlib.suppress(ValueError):
            parsed = int(raw_value)
    return parsed


def _coerce_string(raw_value: object) -> str | None:
    if not isinstance(raw_value, str):
        return None
    value = raw_value.strip()
    return value or None
