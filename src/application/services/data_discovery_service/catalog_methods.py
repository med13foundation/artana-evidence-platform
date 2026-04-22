"""Catalog permission helpers for data discovery service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.entities.data_source_activation import PermissionLevel

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.data_source_activation_service import (
        DataSourceActivationService,
    )
    from src.domain.entities.data_discovery_session import SourceCatalogEntry
    from src.domain.repositories.data_discovery_repository import (
        SourceCatalogRepository,
    )


class CatalogPermissionMixin:
    _activation_service: DataSourceActivationService | None
    _catalog_repo: SourceCatalogRepository

    def _resolve_permission_level(
        self,
        catalog_entry_id: str,
        research_space_id: UUID | None,
    ) -> PermissionLevel:
        """Determine the permission level for a catalog entry within a space."""
        if not self._activation_service:
            return PermissionLevel.AVAILABLE
        return self._activation_service.get_effective_permission_level(
            catalog_entry_id,
            research_space_id,
        )

    def _can_display_source(
        self,
        catalog_entry_id: str,
        research_space_id: UUID | None,
    ) -> bool:
        """Return True when a source should be visible within the catalog."""
        return (
            self._resolve_permission_level(catalog_entry_id, research_space_id)
            != PermissionLevel.BLOCKED
        )

    def _can_execute_source(
        self,
        catalog_entry_id: str,
        research_space_id: UUID | None,
    ) -> bool:
        """Return True when tests/ingestion may run for a source in the space."""
        return (
            self._resolve_permission_level(catalog_entry_id, research_space_id)
            == PermissionLevel.AVAILABLE
        )

    def get_source_catalog(
        self,
        category: str | None = None,
        search_query: str | None = None,
        research_space_id: UUID | None = None,
    ) -> list[SourceCatalogEntry]:
        """
        Get the source catalog, optionally filtered.

        Args:
            category: Optional category filter
            search_query: Optional search query

        Returns:
            List of catalog entries
        """
        if search_query:
            entries = self._catalog_repo.search(search_query, category)
        elif category:
            entries = self._catalog_repo.find_by_category(category)
        else:
            entries = self._catalog_repo.find_all_active()

        return [
            entry
            for entry in entries
            if self._can_display_source(entry.id, research_space_id)
        ]
