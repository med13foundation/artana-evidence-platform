"""
Helper workflows for storage configuration mutations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities.storage_configuration import StorageConfiguration
from src.type_definitions.storage import (
    StorageProviderName,
    StorageUseCase,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from src.domain.repositories.storage_repository import (
        StorageConfigurationRepository,
    )
    from src.domain.services.storage_providers import StorageProviderPlugin

    from .storage_configuration_requests import (
        CreateStorageConfigurationRequest,
        UpdateStorageConfigurationRequest,
    )
    from .storage_configuration_validator import StorageConfigurationValidator


async def create_configuration(
    *,
    request: CreateStorageConfigurationRequest,
    configuration_repository: StorageConfigurationRepository,
    validator: StorageConfigurationValidator,
    require_plugin: Callable[[StorageProviderName], StorageProviderPlugin],
    require_maintenance_for_mutation: Callable[[], Awaitable[None]],
) -> StorageConfiguration:
    """Create a new configuration using shared validation rules."""

    await require_maintenance_for_mutation()
    validator.ensure_unique_name(configuration_repository, name=request.name)
    plugin = require_plugin(request.provider)
    validated_config = await plugin.validate_config(request.config)
    requested_capabilities = set(
        request.supported_capabilities or plugin.capabilities(),
    )
    requested_use_cases = set(request.default_use_cases or {StorageUseCase.PDF})
    validator.ensure_capabilities_supported(
        plugin=plugin,
        provider=request.provider,
        requested=requested_capabilities,
    )
    validator.ensure_use_cases_supported(
        plugin=plugin,
        provider=request.provider,
        use_cases=requested_use_cases,
    )
    if request.enabled:
        validator.ensure_use_case_exclusivity(
            configuration_repository,
            provider=request.provider,
            use_cases=requested_use_cases,
        )

    configuration = StorageConfiguration(
        id=uuid4(),
        name=request.name,
        provider=request.provider,
        config=validated_config,
        enabled=request.enabled,
        supported_capabilities=tuple(requested_capabilities),
        default_use_cases=tuple(requested_use_cases),
        metadata=request.metadata,
    )
    persisted = configuration_repository.create(configuration)
    if request.ensure_storage_ready:
        await plugin.ensure_storage_exists(validated_config)
    return persisted


async def update_configuration(  # noqa: PLR0913 - explicit workflow inputs keep Clean Architecture boundaries
    *,
    configuration_id: UUID,
    request: UpdateStorageConfigurationRequest,
    configuration_repository: StorageConfigurationRepository,
    validator: StorageConfigurationValidator,
    require_configuration: Callable[[UUID], StorageConfiguration],
    require_plugin: Callable[[StorageProviderName], StorageProviderPlugin],
    require_maintenance_mode: Callable[[], Awaitable[None]],
) -> StorageConfiguration:
    """Update a configuration using shared guards."""

    current = require_configuration(configuration_id)
    requires_maintenance = request.config is not None
    if requires_maintenance:
        await require_maintenance_mode()

    updated_config_model = request.config or current.config
    plugin = require_plugin(current.provider)
    validated_config = await plugin.validate_config(updated_config_model)
    requested_capabilities = set(
        request.supported_capabilities or current.supported_capabilities,
    )
    requested_use_cases = set(
        request.default_use_cases or current.default_use_cases,
    )
    enabled = request.enabled if request.enabled is not None else current.enabled

    validator.ensure_capabilities_supported(
        plugin=plugin,
        provider=current.provider,
        requested=requested_capabilities,
    )
    validator.ensure_use_cases_supported(
        plugin=plugin,
        provider=current.provider,
        use_cases=requested_use_cases,
    )
    if enabled:
        validator.ensure_use_case_exclusivity(
            configuration_repository,
            provider=current.provider,
            use_cases=requested_use_cases,
            exclude_id=current.id,
        )

    changes: dict[str, object] = {
        "config": validated_config,
        "supported_capabilities": tuple(requested_capabilities),
        "default_use_cases": tuple(requested_use_cases),
    }
    if request.metadata is not None:
        changes["metadata"] = request.metadata
    if request.name is not None:
        validator.ensure_unique_name(
            configuration_repository,
            name=request.name,
            exclude_id=current.id,
        )
        changes["name"] = request.name
    if request.enabled is not None:
        changes["enabled"] = request.enabled
    updated = current.model_copy(update=changes)
    return configuration_repository.update(updated)


async def delete_or_disable_configuration(
    *,
    configuration_id: UUID,
    configuration_repository: StorageConfigurationRepository,
    require_configuration: Callable[[UUID], StorageConfiguration],
    require_maintenance_for_mutation: Callable[[], Awaitable[None]],
    force: bool,
) -> bool:
    """Delete or disable a configuration depending on flags."""

    configuration = require_configuration(configuration_id)
    await require_maintenance_for_mutation()
    if configuration.enabled and not force:
        updated = configuration.model_copy(
            update={
                "enabled": False,
            },
        )
        configuration_repository.update(updated)
        return True
    return configuration_repository.delete(configuration_id)
