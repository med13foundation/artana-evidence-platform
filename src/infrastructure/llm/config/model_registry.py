"""
Model registry implementation for AI agent configurations.

Implements the ModelRegistryPort interface, loading models from
artana.toml configuration with environment variable overrides.

This is the single source of truth for available AI models.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

import tomllib

from src.domain.agents.models import (
    ModelCapability,
    ModelCostTier,
    ModelReasoningSettings,
    ModelSpec,
)
from src.domain.agents.ports import ModelRegistryPort

# Default config path relative to project root
DEFAULT_CONFIG_PATH = "artana.toml"


class ArtanaModelRegistry(ModelRegistryPort):
    """
    Model registry implementation loading from artana.toml.

    Provides centralized access to model configurations for
    agent factories, cost tracking, and model selection.

    Configuration hierarchy (highest priority first):
    1. Environment variables (ARTANA_AI_{CAPABILITY}_MODEL)
    2. artana.toml [models] section
    3. Fallback to first enabled model
    """

    _instance: ArtanaModelRegistry | None = None
    _models: dict[str, ModelSpec]
    _defaults: dict[ModelCapability, str]
    _cost_config: dict[str, dict[str, float]]
    _allow_runtime_model_overrides: bool

    def __init__(self, config_path: str | Path | None = None) -> None:
        """
        Initialize the registry from configuration.

        Args:
            config_path: Path to artana.toml (defaults to project root)
        """
        self._config_path = (
            Path(config_path) if config_path else Path(DEFAULT_CONFIG_PATH)
        )
        self._load_configuration()

    def _load_configuration(self) -> None:
        """Load models and defaults from artana.toml."""
        config = self._read_config_file()

        # Parse models from registry section
        self._models = self._parse_models(config)

        # Parse defaults from [models] section
        self._defaults = self._parse_defaults(config)

        # Store cost config for reference
        self._cost_config = self._parse_cost_config(config)
        self._allow_runtime_model_overrides = self._parse_allow_runtime_model_overrides(
            config,
        )

    def _read_config_file(self) -> dict[str, object]:
        """Read and parse the TOML configuration file."""
        if not self._config_path.exists():
            # Return empty config if file doesn't exist (use code defaults)
            return {}

        with self._config_path.open("rb") as f:
            return tomllib.load(f)

    def _parse_models(self, config: Mapping[str, object]) -> dict[str, ModelSpec]:
        """Parse model specifications from config."""
        models: dict[str, ModelSpec] = {}

        models_section = config.get("models", {})
        if not isinstance(models_section, dict):
            return models

        registry = models_section.get("registry", {})
        if not isinstance(registry, dict):
            return models

        cost_providers = self._get_cost_providers(config)

        for model_id, spec in registry.items():
            if not isinstance(spec, dict):
                continue

            # Get cost from cost.providers section
            provider, model_name = self._parse_model_id(model_id)
            provider_costs = cost_providers.get(provider, {})
            cost_info: dict[str, object] = {}
            if isinstance(provider_costs, dict):
                model_costs = provider_costs.get(model_name, {})
                if isinstance(model_costs, dict):
                    cost_info = model_costs

            # Parse capabilities
            raw_capabilities = spec.get("capabilities", [])
            if not isinstance(raw_capabilities, list):
                raw_capabilities = []
            capabilities = frozenset(
                ModelCapability(c)
                for c in raw_capabilities
                if c in ModelCapability._value2member_map_
            )

            # Parse reasoning settings if present
            reasoning_settings = None
            raw_reasoning = spec.get("default_reasoning_settings")
            if isinstance(raw_reasoning, dict):
                reasoning_settings = ModelReasoningSettings(
                    effort=self._parse_reasoning_effort(raw_reasoning.get("effort")),
                    verbosity=self._parse_reasoning_verbosity(
                        raw_reasoning.get("verbosity"),
                    ),
                    summary=self._parse_reasoning_summary(raw_reasoning.get("summary")),
                )

            # Parse cost tier
            raw_cost_tier = spec.get("cost_tier", "medium")
            cost_tier = (
                ModelCostTier(raw_cost_tier)
                if raw_cost_tier in ModelCostTier._value2member_map_
                else ModelCostTier.MEDIUM
            )

            # Extract cost values with proper type handling
            prompt_cost_raw = cost_info.get("prompt_tokens_per_1k", 0.001)
            completion_cost_raw = cost_info.get("completion_tokens_per_1k", 0.002)
            prompt_cost = (
                float(prompt_cost_raw)
                if isinstance(prompt_cost_raw, int | float | str)
                else 0.001
            )
            completion_cost = (
                float(completion_cost_raw)
                if isinstance(completion_cost_raw, int | float | str)
                else 0.002
            )

            models[model_id] = ModelSpec(
                model_id=model_id,
                display_name=str(spec.get("display_name", model_id)),
                provider=str(spec.get("provider", provider)),
                capabilities=capabilities,
                cost_tier=cost_tier,
                prompt_tokens_per_1k=prompt_cost,
                completion_tokens_per_1k=completion_cost,
                is_reasoning_model=bool(spec.get("is_reasoning_model", False)),
                default_reasoning_settings=reasoning_settings,
                max_retries=int(spec.get("max_retries", 3)),
                timeout_seconds=float(spec.get("timeout_seconds", 30.0)),
                is_enabled=bool(spec.get("is_enabled", True)),
                is_default=bool(spec.get("is_default", False)),
            )

        return models

    def _parse_defaults(
        self,
        config: Mapping[str, object],
    ) -> dict[ModelCapability, str]:
        """Parse default model mappings from config."""
        defaults: dict[ModelCapability, str] = {}

        models_section = config.get("models", {})
        if not isinstance(models_section, dict):
            return defaults

        # Map config keys to capabilities
        capability_map = {
            "default_query_generation": ModelCapability.QUERY_GENERATION,
            "default_evidence_extraction": ModelCapability.EVIDENCE_EXTRACTION,
            "default_curation": ModelCapability.CURATION,
            "default_judge": ModelCapability.JUDGE,
        }

        for config_key, capability in capability_map.items():
            if config_key in models_section:
                value = models_section[config_key]
                if isinstance(value, str):
                    defaults[capability] = value

        return defaults

    def _parse_cost_config(
        self,
        config: Mapping[str, object],
    ) -> dict[str, dict[str, float]]:
        """Parse cost configuration for cost tracking."""
        result: dict[str, dict[str, float]] = {}
        cost_providers = self._get_cost_providers(config)

        for provider, provider_models in cost_providers.items():
            if not isinstance(provider_models, dict):
                continue
            for model_name, costs in provider_models.items():
                if not isinstance(costs, dict):
                    continue
                full_id = f"{provider}:{model_name}"
                result[full_id] = {
                    "prompt_tokens_per_1k": float(costs.get("prompt_tokens_per_1k", 0)),
                    "completion_tokens_per_1k": float(
                        costs.get("completion_tokens_per_1k", 0),
                    ),
                }

        return result

    def _parse_allow_runtime_model_overrides(
        self,
        config: Mapping[str, object],
    ) -> bool:
        models_section = config.get("models", {})
        if isinstance(models_section, dict):
            raw_value = models_section.get("allow_runtime_model_overrides")
            if isinstance(raw_value, bool):
                return raw_value

        return False

    def _get_cost_providers(self, config: Mapping[str, object]) -> dict[str, object]:
        """Extract cost.providers section from config."""
        cost = config.get("cost", {})
        if not isinstance(cost, dict):
            return {}
        providers = cost.get("providers", {})
        if not isinstance(providers, dict):
            return {}
        return providers

    @staticmethod
    def _parse_model_id(model_id: str) -> tuple[str, str]:
        """Parse 'provider:model' format into components."""
        if ":" in model_id:
            parts = model_id.split(":", 1)
            return parts[0], parts[1]
        return "openai", model_id

    @staticmethod
    def _parse_reasoning_effort(raw_value: object) -> Literal["low", "medium", "high"]:
        if raw_value == "low":
            return "low"
        if raw_value == "high":
            return "high"
        return "medium"

    @staticmethod
    def _parse_reasoning_verbosity(
        raw_value: object,
    ) -> Literal["low", "medium", "high"] | None:
        if raw_value == "low":
            return "low"
        if raw_value == "high":
            return "high"
        if raw_value == "medium":
            return "medium"
        return "medium"

    @staticmethod
    def _parse_reasoning_summary(
        raw_value: object,
    ) -> Literal["brief", "detailed"] | None:
        if raw_value == "brief":
            return "brief"
        if raw_value == "detailed":
            return "detailed"
        return None

    # =========================================================================
    # ModelRegistryPort Implementation
    # =========================================================================

    def get_model(self, model_id: str) -> ModelSpec:
        """Get a specific model by ID."""
        if model_id not in self._models:
            available = list(self._models.keys())
            msg = f"Model '{model_id}' not found. Available: {available}"
            raise KeyError(msg)
        return self._models[model_id]

    def get_available_models(self) -> list[ModelSpec]:
        """Get all enabled models."""
        return [m for m in self._models.values() if m.is_enabled]

    def get_models_for_capability(
        self,
        capability: ModelCapability,
    ) -> list[ModelSpec]:
        """Get models that support a specific capability."""
        return [
            m
            for m in self._models.values()
            if m.is_enabled and m.supports_capability(capability)
        ]

    def get_default_model(self, capability: ModelCapability) -> ModelSpec:
        """
        Get the default model for a capability.

        Resolution order:
        1. Environment variable (ARTANA_AI_{CAPABILITY}_MODEL)
        2. artana.toml [models] defaults
        3. First enabled model with the capability
        """
        # 1. Check environment variable
        env_key = f"ARTANA_AI_{capability.value.upper()}_MODEL"
        env_model = os.getenv(env_key)
        if env_model and env_model in self._models:
            model = self._models[env_model]
            if model.is_enabled and model.supports_capability(capability):
                return model

        # 2. Check artana.toml defaults
        if capability in self._defaults:
            default_id = self._defaults[capability]
            if default_id in self._models:
                model = self._models[default_id]
                if model.is_enabled and model.supports_capability(capability):
                    return model

        # 3. Fallback to first enabled model with capability
        for model in self._models.values():
            if model.is_enabled and model.supports_capability(capability):
                return model

        msg = f"No model available for capability: {capability.value}"
        raise ValueError(msg)

    def validate_model_for_capability(
        self,
        model_id: str,
        capability: ModelCapability,
    ) -> bool:
        """Check if a model can be used for a specific task."""
        if model_id not in self._models:
            return False
        model = self._models[model_id]
        return model.is_enabled and model.supports_capability(capability)

    def list_model_ids(self) -> list[str]:
        """List all registered model IDs."""
        return list(self._models.keys())

    def allow_runtime_model_overrides(self) -> bool:
        """
        Whether runtime/per-source model_id overrides are allowed.

        Environment override:
        - ARTANA_AI_ALLOW_RUNTIME_MODEL_OVERRIDES=1|true|yes|on to enable
        - ARTANA_AI_ALLOW_RUNTIME_MODEL_OVERRIDES=0|false|no|off to disable
        """
        raw_env = os.getenv("ARTANA_AI_ALLOW_RUNTIME_MODEL_OVERRIDES")
        if isinstance(raw_env, str):
            normalized = raw_env.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return self._allow_runtime_model_overrides

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    def get_cost_config(self, model_id: str) -> dict[str, float]:
        """Get cost configuration for a model."""
        return self._cost_config.get(
            model_id,
            {
                "prompt_tokens_per_1k": 0.001,
                "completion_tokens_per_1k": 0.002,
            },
        )


@lru_cache(maxsize=1)
def get_model_registry() -> ArtanaModelRegistry:
    """
    Get the singleton model registry instance.

    This function is cached to ensure a single registry
    instance is used throughout the application.

    Returns:
        The global ArtanaModelRegistry instance
    """
    return ArtanaModelRegistry()


def get_default_model_id(capability: ModelCapability) -> str:
    """
    Get the default model ID for a capability.

    Convenience function for getting just the model ID
    without the full ModelSpec.

    Args:
        capability: The capability to get default for

    Returns:
        The model ID string
    """
    registry = get_model_registry()
    return registry.get_default_model(capability).model_id


# =============================================================================
# Legacy Compatibility Layer
# =============================================================================
# Thin compatibility wrapper for code paths that still use
# ModelRegistry class methods directly.


class ModelRegistry:
    """
    Compatibility wrapper for ArtanaModelRegistry.

    Provides the same class-method interface as the previous
    implementation.

    New code should use get_model_registry() instead.
    """

    @classmethod
    def get_model(cls, model_id: str) -> ModelSpec:
        """Get configuration for a specific model."""
        return get_model_registry().get_model(model_id)

    @classmethod
    def get_default_query_model(cls) -> ModelSpec:
        """Get the default model for query generation."""
        return get_model_registry().get_default_model(ModelCapability.QUERY_GENERATION)

    @classmethod
    def get_default_extraction_model(cls) -> ModelSpec:
        """Get the default model for evidence extraction."""
        return get_model_registry().get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )

    @classmethod
    def get_default_curation_model(cls) -> ModelSpec:
        """Get the default model for curation."""
        return get_model_registry().get_default_model(ModelCapability.CURATION)

    @classmethod
    def get_default_judge_model(cls) -> ModelSpec:
        """Get the default model for shadow evaluation."""
        return get_model_registry().get_default_model(ModelCapability.JUDGE)

    @classmethod
    def list_models(cls) -> list[str]:
        """List all registered model IDs."""
        return get_model_registry().list_model_ids()

    @classmethod
    def get_available_models(cls) -> list[ModelSpec]:
        """Get all enabled models."""
        return get_model_registry().get_available_models()
