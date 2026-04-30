"""Model registry loading for graph-harness runtime operations."""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path

from artana_evidence_api.runtime.config import _CONFIG_PATH, _read_artana_toml
from pydantic import BaseModel, Field


class ModelCapability(str, Enum):
    """Capabilities used by graph-harness runtime model selection."""

    QUERY_GENERATION = "query_generation"
    EVIDENCE_EXTRACTION = "evidence_extraction"
    CURATION = "curation"
    JUDGE = "judge"


class ModelSpec(BaseModel):
    """Minimal model registry entry required by graph-harness runtimes."""

    model_id: str
    capabilities: frozenset[ModelCapability] = Field(default_factory=frozenset)
    timeout_seconds: float = Field(default=30.0, gt=0)
    is_enabled: bool = True

    model_config = {"frozen": True}

    def supports_capability(self, capability: ModelCapability) -> bool:
        return capability in self.capabilities


class ArtanaModelRegistry:
    """Service-local registry loader for graph-harness runtime models."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config_path = Path(config_path) if config_path else _CONFIG_PATH
        self._models: dict[str, ModelSpec] = {}
        self._defaults: dict[ModelCapability, str] = {}
        self._allow_runtime_model_overrides = False
        self._load_configuration()

    def _load_configuration(self) -> None:
        config = _read_artana_toml(str(self._config_path))
        models_section = config.get("models", {})
        if not isinstance(models_section, dict):
            return
        self._models = self._parse_models(models_section)
        self._defaults = self._parse_defaults(models_section)
        raw_allow_overrides = models_section.get("allow_runtime_model_overrides")
        self._allow_runtime_model_overrides = (
            raw_allow_overrides if isinstance(raw_allow_overrides, bool) else False
        )

    def _parse_models(self, models_section: dict[str, object]) -> dict[str, ModelSpec]:
        models: dict[str, ModelSpec] = {}
        registry = models_section.get("registry", {})
        if not isinstance(registry, dict):
            return models
        for model_id, raw_spec in registry.items():
            if not isinstance(raw_spec, dict):
                continue
            raw_capabilities = raw_spec.get("capabilities", [])
            capabilities = frozenset(
                ModelCapability(value)
                for value in raw_capabilities
                if isinstance(value, str)
                and value in ModelCapability._value2member_map_
            )
            models[model_id] = ModelSpec(
                model_id=model_id,
                capabilities=capabilities,
                timeout_seconds=float(raw_spec.get("timeout_seconds", 30.0)),
                is_enabled=bool(raw_spec.get("is_enabled", True)),
            )
        return models

    def _parse_defaults(
        self,
        models_section: dict[str, object],
    ) -> dict[ModelCapability, str]:
        defaults: dict[ModelCapability, str] = {}
        capability_map = {
            "default_query_generation": ModelCapability.QUERY_GENERATION,
            "default_evidence_extraction": ModelCapability.EVIDENCE_EXTRACTION,
            "default_curation": ModelCapability.CURATION,
            "default_judge": ModelCapability.JUDGE,
        }
        for config_key, capability in capability_map.items():
            value = models_section.get(config_key)
            if isinstance(value, str):
                defaults[capability] = value
        return defaults

    def get_model(self, model_id: str) -> ModelSpec:
        if model_id not in self._models:
            available = list(self._models.keys())
            message = f"Model '{model_id}' not found. Available: {available}"
            raise KeyError(message)
        return self._models[model_id]

    def get_default_model(self, capability: ModelCapability) -> ModelSpec:
        env_key = f"ARTANA_AI_{capability.value.upper()}_MODEL"
        env_model = os.getenv(env_key)
        if isinstance(env_model, str) and env_model in self._models:
            model = self._models[env_model]
            if model.is_enabled and model.supports_capability(capability):
                return model

        default_id = self._defaults.get(capability)
        if isinstance(default_id, str) and default_id in self._models:
            model = self._models[default_id]
            if model.is_enabled and model.supports_capability(capability):
                return model

        for model in self._models.values():
            if model.is_enabled and model.supports_capability(capability):
                return model

        message = f"No model available for capability: {capability.value}"
        raise ValueError(message)

    def validate_model_for_capability(
        self,
        model_id: str,
        capability: ModelCapability,
    ) -> bool:
        if model_id not in self._models:
            return False
        model = self._models[model_id]
        return model.is_enabled and model.supports_capability(capability)

    def allow_runtime_model_overrides(self) -> bool:
        raw_env = os.getenv("ARTANA_AI_ALLOW_RUNTIME_MODEL_OVERRIDES")
        if isinstance(raw_env, str):
            normalized = raw_env.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return self._allow_runtime_model_overrides


@lru_cache(maxsize=1)
def get_model_registry() -> ArtanaModelRegistry:
    return ArtanaModelRegistry()


__all__ = [
    "ArtanaModelRegistry",
    "ModelCapability",
    "ModelSpec",
    "get_model_registry",
]
