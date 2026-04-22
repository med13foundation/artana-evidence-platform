"""
Port interface for model registry operations.

Defines how the application layer accesses available AI models
following the Ports & Adapters (Hexagonal) architecture pattern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.models import ModelCapability, ModelSpec


class ModelRegistryPort(ABC):
    """
    Domain interface for accessing available AI models.

    This port defines how the application layer interacts with
    the model registry, enabling dependency inversion and
    testability.

    The infrastructure layer implements this port to load
    models from configuration (artana.toml, environment, etc.).
    """

    @abstractmethod
    def get_model(self, model_id: str) -> ModelSpec:
        """
        Get a specific model by ID.

        Args:
            model_id: The model identifier (e.g., "openai:gpt-5-mini")

        Returns:
            The model specification

        Raises:
            KeyError: If the model is not registered
        """

    @abstractmethod
    def get_available_models(self) -> list[ModelSpec]:
        """
        Get all enabled models.

        Returns:
            List of all models that are available for selection
        """

    @abstractmethod
    def get_models_for_capability(
        self,
        capability: ModelCapability,
    ) -> list[ModelSpec]:
        """
        Get models that support a specific capability.

        Args:
            capability: The required capability

        Returns:
            List of enabled models that support the capability
        """

    @abstractmethod
    def get_default_model(self, capability: ModelCapability) -> ModelSpec:
        """
        Get the default model for a capability.

        Resolution order:
        1. Environment variable (ARTANA_AI_{CAPABILITY}_MODEL)
        2. artana.toml [models] defaults
        3. First enabled model with the capability

        Args:
            capability: The capability to get default for

        Returns:
            The default model for the capability

        Raises:
            ValueError: If no model is available for the capability
        """

    @abstractmethod
    def validate_model_for_capability(
        self,
        model_id: str,
        capability: ModelCapability,
    ) -> bool:
        """
        Check if a model can be used for a specific task.

        Args:
            model_id: The model to validate
            capability: The required capability

        Returns:
            True if the model exists, is enabled, and supports the capability
        """

    @abstractmethod
    def list_model_ids(self) -> list[str]:
        """
        List all registered model IDs.

        Returns:
            List of all model IDs (including disabled models)
        """
