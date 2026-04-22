"""Repository interface for data source activation policies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID  # noqa: TC003

from src.domain.entities.data_source_activation import (  # noqa: TC001
    ActivationScope,
    DataSourceActivation,
    PermissionLevel,
)


class DataSourceActivationRepository(ABC):
    """Abstract repository for managing data source activation policies."""

    @abstractmethod
    def get_rule(
        self,
        catalog_entry_id: str,
        scope: ActivationScope,
        research_space_id: UUID | None = None,
    ) -> DataSourceActivation | None:
        """Retrieve a specific activation rule for a catalog entry."""

    @abstractmethod
    def list_rules_for_source(
        self,
        catalog_entry_id: str,
    ) -> list[DataSourceActivation]:
        """List all activation rules associated with a catalog entry."""

    @abstractmethod
    def list_rules_for_sources(
        self,
        catalog_entry_ids: list[str],
    ) -> dict[str, list[DataSourceActivation]]:
        """List activation rules for multiple catalog entries."""

    @abstractmethod
    def set_rule(
        self,
        *,
        catalog_entry_id: str,
        scope: ActivationScope,
        permission_level: PermissionLevel,
        updated_by: UUID,
        research_space_id: UUID | None = None,
    ) -> DataSourceActivation:
        """Create or update an activation rule for the provided scope."""

    @abstractmethod
    def delete_rule(
        self,
        *,
        catalog_entry_id: str,
        scope: ActivationScope,
        research_space_id: UUID | None = None,
    ) -> None:
        """Delete the activation rule for the provided scope (if it exists)."""
