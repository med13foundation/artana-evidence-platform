"""Shared cost-calculation helpers for LLM usage accounting."""

from __future__ import annotations

from src.domain.services.direct_cost_tracking import (
    DirectCostUsage,
    activate_cost_usage_recorder,
    get_active_cost_usage_recorder,
)
from src.infrastructure.llm.config import get_model_registry


def normalize_openai_model_id(model_id: str) -> str:
    """Normalize model ids to the registry's provider:model format."""
    normalized = model_id.strip()
    if ":" in normalized:
        return normalized
    return f"openai:{normalized}"


def calculate_openai_usage_cost_usd(
    *,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Calculate direct USD cost from token usage and configured model pricing."""
    normalized_model_id = normalize_openai_model_id(model_id)
    registry = get_model_registry()
    cost_config = registry.get_cost_config(normalized_model_id)
    prompt_rate = float(cost_config.get("prompt_tokens_per_1k", 0.0))
    completion_rate = float(cost_config.get("completion_tokens_per_1k", 0.0))
    total_cost = (max(prompt_tokens, 0) / 1000.0) * max(prompt_rate, 0.0) + (
        max(completion_tokens, 0) / 1000.0
    ) * max(completion_rate, 0.0)
    return round(total_cost, 8)


def record_cost_usage(  # noqa: PLR0913
    *,
    provider: str,
    model_id: str,
    operation: str,
    cost_usd: float,
    prompt_tokens: int,
    completion_tokens: int,
    stage: str | None = None,
) -> None:
    """Emit one direct-usage record into the active recorder, if any."""
    recorder = get_active_cost_usage_recorder()
    if recorder is None:
        return
    normalized_cost = round(max(float(cost_usd), 0.0), 8)
    if normalized_cost <= 0.0:
        return
    recorder(
        DirectCostUsage(
            provider=provider.strip().lower() or "unknown",
            model_id=model_id.strip(),
            operation=operation.strip().lower() or "unknown",
            cost_usd=normalized_cost,
            prompt_tokens=max(int(prompt_tokens), 0),
            completion_tokens=max(int(completion_tokens), 0),
            stage=(
                stage.strip().lower()
                if isinstance(stage, str) and stage.strip()
                else None
            ),
        ),
    )


__all__ = [
    "DirectCostUsage",
    "activate_cost_usage_recorder",
    "calculate_openai_usage_cost_usd",
    "normalize_openai_model_id",
    "record_cost_usage",
]
