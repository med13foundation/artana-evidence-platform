"""Application service for managing data source activation policies."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID  # noqa: TC003

from src.domain.entities.data_source_activation import (
    ActivationScope,
    DataSourceActivation,
    PermissionLevel,
)
from src.domain.repositories.data_source_activation_repository import (  # noqa: TC001
    DataSourceActivationRepository,
)

DEFAULT_AVAILABLE_SOURCES: frozenset[str] = frozenset(
    {
        "pubmed",
        "clinvar",
    },
)


@dataclass(frozen=True)
class DataSourceAvailabilitySummary:
    """Aggregate view of activation policies for a catalog entry."""

    catalog_entry_id: str
    effective_permission_level: PermissionLevel
    effective_is_active: bool
    global_rule: DataSourceActivation | None
    project_rules: list[DataSourceActivation]


class DataSourceActivationService:
    """Application-level coordinator for data source availability policies."""

    def __init__(self, repository: DataSourceActivationRepository) -> None:
        self._repository = repository

    def _default_permission(self, catalog_entry_id: str) -> PermissionLevel:
        """Return the default permission for catalog entries without explicit rules."""
        if catalog_entry_id in DEFAULT_AVAILABLE_SOURCES:
            return PermissionLevel.AVAILABLE
        return PermissionLevel.BLOCKED

    def set_global_activation(
        self,
        *,
        catalog_entry_id: str,
        permission_level: PermissionLevel,
        updated_by: UUID,
    ) -> DataSourceActivation:
        """Create or update the global activation status for a data source."""

        return self._repository.set_rule(
            catalog_entry_id=catalog_entry_id,
            scope=ActivationScope.GLOBAL,
            permission_level=permission_level,
            updated_by=updated_by,
        )

    def clear_global_activation(self, catalog_entry_id: str) -> None:
        """Remove the global activation override for a data source."""

        self._repository.delete_rule(
            catalog_entry_id=catalog_entry_id,
            scope=ActivationScope.GLOBAL,
        )

    def set_project_activation(
        self,
        *,
        catalog_entry_id: str,
        research_space_id: UUID,
        permission_level: PermissionLevel,
        updated_by: UUID,
    ) -> DataSourceActivation:
        """Create or update an activation override for a specific research space."""

        return self._repository.set_rule(
            catalog_entry_id=catalog_entry_id,
            scope=ActivationScope.RESEARCH_SPACE,
            research_space_id=research_space_id,
            permission_level=permission_level,
            updated_by=updated_by,
        )

    def clear_project_activation(
        self,
        *,
        catalog_entry_id: str,
        research_space_id: UUID,
    ) -> None:
        """Delete the activation override for the provided research space."""

        self._repository.delete_rule(
            catalog_entry_id=catalog_entry_id,
            scope=ActivationScope.RESEARCH_SPACE,
            research_space_id=research_space_id,
        )

    def get_effective_permission_level(
        self,
        catalog_entry_id: str,
        research_space_id: UUID | None = None,
    ) -> PermissionLevel:
        """Resolve the effective permission level for the provided context."""

        if research_space_id:
            project_rule = self._repository.get_rule(
                catalog_entry_id,
                ActivationScope.RESEARCH_SPACE,
                research_space_id,
            )
            if project_rule is not None:
                return project_rule.permission_level

        global_rule = self._repository.get_rule(
            catalog_entry_id,
            ActivationScope.GLOBAL,
        )
        if global_rule is not None:
            return global_rule.permission_level

        return self._default_permission(catalog_entry_id)

    def is_source_active(
        self,
        catalog_entry_id: str,
        research_space_id: UUID | None = None,
    ) -> bool:
        """Determine if a data source is active for the provided scope."""

        return (
            self.get_effective_permission_level(catalog_entry_id, research_space_id)
            != PermissionLevel.BLOCKED
        )

    def get_availability_summary(
        self,
        catalog_entry_id: str,
    ) -> DataSourceAvailabilitySummary:
        """Return a summary of activation rules for a data source."""

        rules = self._repository.list_rules_for_source(catalog_entry_id)
        return self._build_summary(catalog_entry_id, rules)

    def get_availability_summaries(
        self,
        catalog_entry_ids: list[str],
    ) -> list[DataSourceAvailabilitySummary]:
        """Return summaries for multiple catalog entries."""

        if not catalog_entry_ids:
            return []

        unique_ids: list[str] = list(dict.fromkeys(catalog_entry_ids))
        rules_by_source = self._repository.list_rules_for_sources(unique_ids)
        return [
            self._build_summary(entry_id, rules_by_source.get(entry_id, []))
            for entry_id in unique_ids
        ]

    def _build_summary(
        self,
        catalog_entry_id: str,
        rules: list[DataSourceActivation],
    ) -> DataSourceAvailabilitySummary:
        global_rule: DataSourceActivation | None = None
        project_rules: list[DataSourceActivation] = []

        for rule in rules:
            if rule.scope == ActivationScope.GLOBAL:
                global_rule = rule
            else:
                project_rules.append(rule)

        effective_permission = (
            global_rule.permission_level
            if global_rule is not None
            else self._default_permission(catalog_entry_id)
        )
        if project_rules:
            # Use the first project rule for deterministic ordering in summary (sorted below)
            project_rules_sorted = sorted(
                project_rules,
                key=lambda r: (
                    str(r.research_space_id or ""),
                    r.updated_at,
                ),
            )
        else:
            project_rules_sorted = []

        return DataSourceAvailabilitySummary(
            catalog_entry_id=catalog_entry_id,
            effective_permission_level=effective_permission,
            effective_is_active=effective_permission != PermissionLevel.BLOCKED,
            global_rule=global_rule,
            project_rules=project_rules_sorted,
        )
