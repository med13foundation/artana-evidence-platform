"""
Domain entity for AI model specifications.

Defines the core business representation of available LLM models,
their capabilities, cost tiers, and configuration requirements.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ModelCapability(str, Enum):
    """
    Capabilities that a model can perform.

    Used to validate that a model is appropriate for a given task.
    """

    QUERY_GENERATION = "query_generation"
    EVIDENCE_EXTRACTION = "evidence_extraction"
    CURATION = "curation"
    JUDGE = "judge"  # For shadow evaluation / quality assessment


class ModelCostTier(str, Enum):
    """
    Cost classification for models.

    Helps users understand relative costs when selecting models.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModelReasoningSettings(BaseModel):
    """
    Settings for reasoning models (e.g., gpt-5, o1).

    Reasoning models require special configuration for
    thinking effort and output verbosity.
    """

    effort: Literal["low", "medium", "high"] = "medium"
    verbosity: Literal["low", "medium", "high"] | None = "medium"
    # Legacy compatibility field: old configs used summary=brief|detailed.
    summary: Literal["brief", "detailed"] | None = None

    def resolved_verbosity(self) -> Literal["low", "medium", "high"]:
        """Resolve effective verbosity, preserving legacy summary compatibility."""
        if self.verbosity is not None:
            return self.verbosity
        if self.summary == "brief":
            return "low"
        if self.summary == "detailed":
            return "medium"
        return "medium"


class ModelSpec(BaseModel):
    """
    Domain entity representing an available AI model.

    This is the business representation of a model that can be
    selected by users or configured at various levels (system,
    space, data source).

    Attributes:
        model_id: model identifier (e.g., "openai:gpt-5-mini")
        display_name: Human-readable name for UI
        provider: Model provider ("openai", "anthropic", etc.)
        capabilities: Set of tasks this model can perform
        cost_tier: Relative cost classification
        prompt_tokens_per_1k: Cost per 1K prompt tokens (USD)
        completion_tokens_per_1k: Cost per 1K completion tokens (USD)
        is_reasoning_model: Whether this is a reasoning model requiring special settings
        default_reasoning_settings: Default settings for reasoning models
        max_retries: Default retry count for this model
        timeout_seconds: Default timeout for this model
        is_enabled: Whether the model is available for selection
        is_default: Whether this is a system default model
    """

    model_id: str = Field(..., description="Model identifier")
    display_name: str = Field(..., description="Human-readable name")
    provider: str = Field(..., description="Model provider")
    capabilities: frozenset[ModelCapability] = Field(
        default_factory=frozenset,
        description="Tasks this model can perform",
    )
    cost_tier: ModelCostTier = Field(
        default=ModelCostTier.MEDIUM,
        description="Relative cost classification",
    )
    prompt_tokens_per_1k: float = Field(
        ...,
        ge=0,
        description="Cost per 1K prompt tokens (USD)",
    )
    completion_tokens_per_1k: float = Field(
        ...,
        ge=0,
        description="Cost per 1K completion tokens (USD)",
    )
    is_reasoning_model: bool = Field(
        default=False,
        description="Whether this requires reasoning-specific settings",
    )
    default_reasoning_settings: ModelReasoningSettings | None = Field(
        default=None,
        description="Default reasoning settings for reasoning models",
    )
    max_retries: int = Field(default=3, ge=1, description="Default retry count")
    timeout_seconds: float = Field(default=30.0, gt=0, description="Default timeout")
    is_enabled: bool = Field(default=True, description="Available for selection")
    is_default: bool = Field(default=False, description="System default model")

    model_config = {"frozen": True}

    def supports_capability(self, capability: ModelCapability) -> bool:
        """Check if this model supports a specific capability."""
        return capability in self.capabilities

    def get_reasoning_settings(
        self,
        effort: Literal["low", "medium", "high"] | None = None,
    ) -> dict[str, dict[str, str]] | None:
        """
        Get reasoning settings for runtime model_settings parameter.

        Returns None for non-reasoning models.

        Args:
            effort: Override the default effort level

        Returns:
            Dictionary suitable for reasoning-capable model_settings payloads
        """
        if not self.is_reasoning_model:
            return None

        settings = self.default_reasoning_settings or ModelReasoningSettings()
        actual_effort = effort or settings.effort
        actual_verbosity = settings.resolved_verbosity()

        return {
            "reasoning": {"effort": actual_effort},
            "text": {"verbosity": actual_verbosity},
        }
