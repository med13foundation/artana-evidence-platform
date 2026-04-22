"""
Validation utilities for storage configuration operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.services.storage_providers.errors import StorageValidationError

if TYPE_CHECKING:
    from uuid import UUID

    from src.domain.repositories.storage_repository import (
        StorageConfigurationRepository,
    )
    from src.domain.services.storage_providers import StorageProviderPlugin
    from src.type_definitions.storage import (
        StorageProviderCapability,
        StorageProviderName,
        StorageUseCase,
    )


class StorageConfigurationValidator:
    """Business rule validation for storage configurations."""

    def ensure_unique_name(
        self,
        repository: StorageConfigurationRepository,
        *,
        name: str,
        exclude_id: UUID | None = None,
    ) -> None:
        existing = repository.list_configurations(include_disabled=True)
        for configuration in existing:
            if configuration.name.lower() != name.lower():
                continue
            if exclude_id and configuration.id == exclude_id:
                continue
            msg = f"Storage configuration '{name}' already exists"
            raise ValueError(msg)

    def ensure_capabilities_supported(
        self,
        *,
        plugin: StorageProviderPlugin,
        provider: StorageProviderName,
        requested: set[StorageProviderCapability],
    ) -> None:
        allowed = plugin.capabilities()
        unsupported = requested - allowed
        if unsupported:
            raise StorageValidationError(
                operation=None,
                provider=provider,
                details={
                    "reason": "unsupported_capability",
                    "unsupported_capabilities": [cap.value for cap in unsupported],
                    "supported_capabilities": [cap.value for cap in allowed],
                },
            )

    def ensure_use_cases_supported(
        self,
        *,
        plugin: StorageProviderPlugin,
        provider: StorageProviderName,
        use_cases: set[StorageUseCase],
    ) -> None:
        for use_case in use_cases:
            if not plugin.supports_use_case(use_case):
                raise StorageValidationError(
                    operation=None,
                    provider=provider,
                    details={
                        "reason": "unsupported_use_case",
                        "use_case": use_case.value,
                    },
                )

    def ensure_use_case_exclusivity(
        self,
        repository: StorageConfigurationRepository,
        *,
        provider: StorageProviderName,
        use_cases: set[StorageUseCase],
        exclude_id: UUID | None = None,
    ) -> None:
        if not use_cases:
            msg = "At least one default use case is required"
            raise ValueError(msg)
        for configuration in repository.list_configurations(include_disabled=True):
            if not configuration.enabled:
                continue
            if exclude_id and configuration.id == exclude_id:
                continue
            overlapping = {
                use_case
                for use_case in use_cases
                if configuration.applies_to_use_case(use_case)
            }
            if not overlapping:
                continue
            raise StorageValidationError(
                operation=None,
                provider=provider,
                details={
                    "reason": "use_case_already_assigned",
                    "conflict_configuration_id": str(configuration.id),
                    "use_cases": [case.value for case in overlapping],
                },
            )


__all__ = ["StorageConfigurationValidator"]
