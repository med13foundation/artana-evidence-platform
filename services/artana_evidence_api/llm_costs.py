"""Service-local cost helpers for LLM usage accounting."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

_DEFAULT_COST_CONFIG = {
    "prompt_tokens_per_1k": 0.001,
    "completion_tokens_per_1k": 0.002,
}
_ARTANA_TOML_PATH = Path(__file__).with_name("artana.toml")


def normalize_openai_model_id(model_id: str) -> str:
    """Normalize model ids to the registry's provider:model format."""
    normalized = model_id.strip()
    if ":" in normalized:
        return normalized
    return f"openai:{normalized}"


@lru_cache(maxsize=1)
def _load_cost_config() -> dict[str, dict[str, float]]:
    if not _ARTANA_TOML_PATH.exists():
        return {}
    with _ARTANA_TOML_PATH.open("rb") as handle:
        loaded = tomllib.load(handle)

    raw_cost_section = loaded.get("cost")
    if not isinstance(raw_cost_section, dict):
        return {}
    raw_providers = raw_cost_section.get("providers")
    if not isinstance(raw_providers, dict):
        return {}

    config: dict[str, dict[str, float]] = {}
    for provider_name, raw_models in raw_providers.items():
        if not isinstance(provider_name, str) or not isinstance(raw_models, dict):
            continue
        for model_name, raw_costs in raw_models.items():
            if not isinstance(model_name, str) or not isinstance(raw_costs, dict):
                continue
            config[f"{provider_name}:{model_name}"] = {
                "prompt_tokens_per_1k": float(
                    raw_costs.get("prompt_tokens_per_1k", 0.0),
                ),
                "completion_tokens_per_1k": float(
                    raw_costs.get("completion_tokens_per_1k", 0.0),
                ),
            }
    return config


def calculate_openai_usage_cost_usd(
    *,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Calculate direct USD cost from token usage and local service pricing."""
    normalized_model_id = normalize_openai_model_id(model_id)
    cost_config = _load_cost_config().get(normalized_model_id, _DEFAULT_COST_CONFIG)
    prompt_rate = float(cost_config.get("prompt_tokens_per_1k", 0.0))
    completion_rate = float(cost_config.get("completion_tokens_per_1k", 0.0))
    total_cost = (max(prompt_tokens, 0) / 1000.0) * max(prompt_rate, 0.0) + (
        max(completion_tokens, 0) / 1000.0
    ) * max(completion_rate, 0.0)
    return round(total_cost, 8)


__all__ = [
    "calculate_openai_usage_cost_usd",
    "normalize_openai_model_id",
]
