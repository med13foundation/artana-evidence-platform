"""
Storage configuration application service.

Implements storage configuration management, validation,
and health monitoring orchestration.
"""

from __future__ import annotations

from collections.abc import Iterable  # noqa: TC003
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

from src.domain.entities.storage_configuration import (
    StorageConfiguration,
    StorageHealthSnapshot,
)
from src.domain.services import storage_metrics, storage_providers
from src.type_definitions.storage import (
    StorageConfigurationModel,
    StorageHealthReport,
    StorageHealthStatus,
    StorageOperationRecord,
    StorageOperationStatus,
    StorageOverviewResponse,
    StorageProviderName,
    StorageProviderTestResult,
    StorageUsageMetrics,
    StorageUseCase,
)

from . import (
    storage_configuration_validator,
    storage_operation_recorder,
    storage_overview_builder,
)
from . import (
    storage_configuration_workflows as config_workflows,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.system_status_service import SystemStatusService
    from src.domain.repositories.storage_repository import (
        StorageConfigurationRepository,
        StorageOperationRepository,
    )
    from src.type_definitions.common import JSONObject

    from .storage_configuration_requests import (
        CreateStorageConfigurationRequest,
        UpdateStorageConfigurationRequest,
    )


class StorageConfigurationService:
    """Application service orchestrating storage configuration use cases."""

    def __init__(  # noqa: PLR0913 - explicit dependency wiring for Clean Architecture
        self,
        configuration_repository: StorageConfigurationRepository,
        operation_repository: StorageOperationRepository,
        plugin_registry: storage_providers.StoragePluginRegistry | None = None,
        validator: (
            storage_configuration_validator.StorageConfigurationValidator | None
        ) = None,
        system_status_service: SystemStatusService | None = None,
        metrics_recorder: storage_metrics.StorageMetricsRecorder | None = None,
    ):
        self._configuration_repository = configuration_repository
        self._operation_repository = operation_repository
        self._plugin_registry = (
            plugin_registry or storage_providers.default_storage_registry
        )
        self._validator = (
            validator or storage_configuration_validator.StorageConfigurationValidator()
        )
        self._system_status_service = system_status_service
        self._metrics_recorder = (
            metrics_recorder or storage_metrics.NoOpStorageMetricsRecorder()
        )

    async def create_configuration(
        self,
        request: CreateStorageConfigurationRequest,
    ) -> StorageConfiguration:
        """Create a new storage configuration."""

        return await config_workflows.create_configuration(
            request=request,
            configuration_repository=self._configuration_repository,
            validator=self._validator,
            require_plugin=self._require_plugin,
            require_maintenance_for_mutation=self._require_maintenance_for_mutation,
        )

    async def update_configuration(
        self,
        configuration_id: UUID,
        request: UpdateStorageConfigurationRequest,
    ) -> StorageConfiguration:
        """Update an existing configuration."""

        return await config_workflows.update_configuration(
            configuration_id=configuration_id,
            request=request,
            configuration_repository=self._configuration_repository,
            validator=self._validator,
            require_configuration=self._require_configuration,
            require_plugin=self._require_plugin,
            require_maintenance_mode=self._require_maintenance_mode,
        )

    def list_configurations(
        self,
        *,
        include_disabled: bool = False,
    ) -> list[StorageConfiguration]:
        """List stored configurations."""

        return self._configuration_repository.list_configurations(
            include_disabled=include_disabled,
        )

    def paginate_configurations(
        self,
        *,
        include_disabled: bool = False,
        page: int = 1,
        per_page: int = 25,
    ) -> tuple[list[StorageConfiguration], int]:
        """Return a paginated list of storage configurations."""

        return self._configuration_repository.paginate_configurations(
            include_disabled=include_disabled,
            page=page,
            per_page=per_page,
        )

    def get_configuration(self, configuration_id: UUID) -> StorageConfigurationModel:
        """Retrieve a configuration."""

        configuration = self._require_configuration(configuration_id)
        return self._to_model(configuration)

    def get_default_for_use_case(
        self,
        use_case: StorageUseCase,
    ) -> StorageConfiguration | None:
        """Resolve the first enabled configuration mapped to the use case."""

        for configuration in self._configuration_repository.list_configurations():
            if not configuration.enabled:
                continue
            if configuration.applies_to_use_case(use_case):
                return configuration
        return None

    def resolve_backend_for_use_case(
        self,
        use_case: StorageUseCase,
    ) -> StorageConfiguration | None:
        """Public helper for other services to fetch use-case mappings."""

        return self.get_default_for_use_case(use_case)

    def assign_use_cases(
        self,
        configuration_id: UUID,
        use_cases: Iterable[StorageUseCase],
    ) -> StorageConfiguration:
        """Assign default use cases to a configuration."""

        configuration = self._require_configuration(configuration_id)
        updated = configuration.with_updated_use_cases(use_cases)
        return self._configuration_repository.update(updated)

    async def test_configuration(
        self,
        configuration_id: UUID,
    ) -> StorageProviderTestResult:
        """Execute a provider connection test and record results."""

        configuration = self._require_configuration(configuration_id)
        plugin = self._require_plugin(configuration.provider)
        started_at = datetime.now(UTC)
        validated_config = await plugin.validate_config(configuration.config)
        result = await plugin.test_connection(
            validated_config,
            configuration_id=configuration.id,
        )
        self._operation_repository.record_test_result(result)
        snapshot = StorageHealthSnapshot(
            configuration_id=configuration.id,
            provider=configuration.provider,
            status=(
                StorageHealthStatus.HEALTHY
                if result.success
                else StorageHealthStatus.DEGRADED
            ),
            last_checked_at=result.checked_at,
            details=result.metadata,
        )
        self._operation_repository.upsert_health_snapshot(snapshot)
        duration_ms = result.latency_ms or int(
            (datetime.now(UTC) - started_at).total_seconds() * 1000,
        )
        test_metadata: JSONObject = {
            "latency_ms": result.latency_ms,
            "message": result.message,
        }
        storage_operation_recorder.record_test_metric(
            configuration=configuration,
            recorder=self._metrics_recorder,
            status=(
                StorageOperationStatus.SUCCESS
                if result.success
                else StorageOperationStatus.FAILED
            ),
            duration_ms=duration_ms,
            metadata=test_metadata,
        )
        return result

    async def record_store_operation(  # noqa: PLR0913 - orchestrator requires explicit context inputs
        self,
        configuration: StorageConfiguration,
        *,
        key: str,
        file_path: Path,
        content_type: str | None,
        user_id: UUID | None,
        metadata: JSONObject | None = None,
    ) -> StorageOperationRecord:
        """Store a file using the provider and record the operation."""

        plugin = self._require_plugin(configuration.provider)
        return await storage_operation_recorder.record_store_operation(
            configuration=configuration,
            plugin=plugin,
            operation_repository=self._operation_repository,
            metrics_recorder=self._metrics_recorder,
            key=key,
            file_path=file_path,
            content_type=content_type,
            user_id=user_id,
            metadata=metadata,
        )

    async def get_file_url(
        self,
        configuration: StorageConfiguration,
        *,
        key: str,
        user_id: UUID | None,
        metadata: JSONObject | None = None,
    ) -> str:
        """Retrieve a provider URL for an existing stored file."""

        plugin = self._require_plugin(configuration.provider)
        return await storage_operation_recorder.record_retrieve_operation(
            configuration=configuration,
            plugin=plugin,
            operation_repository=self._operation_repository,
            metrics_recorder=self._metrics_recorder,
            key=key,
            user_id=user_id,
            metadata=metadata,
        )

    async def get_file_url_for_use_case(
        self,
        use_case: StorageUseCase,
        *,
        key: str,
        user_id: UUID | None = None,
        metadata: JSONObject | None = None,
    ) -> str:
        """Retrieve a provider URL for a file tied to a storage use case."""

        configuration = self.get_default_for_use_case(use_case)
        if configuration is None:
            msg = f"No storage configuration defined for use case {use_case.value}"
            raise RuntimeError(msg)
        return await self.get_file_url(
            configuration,
            key=key,
            user_id=user_id,
            metadata=metadata,
        )

    def get_usage_metrics(self, configuration_id: UUID) -> StorageUsageMetrics | None:
        """Return aggregated usage metrics for a configuration."""

        self._require_configuration(configuration_id)
        return self._operation_repository.get_usage_metrics(configuration_id)

    def get_health_report(self, configuration_id: UUID) -> StorageHealthReport | None:
        """Return the latest health snapshot for the configuration."""

        self._require_configuration(configuration_id)
        snapshot = self._operation_repository.get_health_snapshot(configuration_id)
        if snapshot is None:
            return None
        return snapshot.as_report()

    def list_operations(
        self,
        configuration_id: UUID,
        *,
        limit: int = 100,
    ) -> list[StorageOperationRecord]:
        """List recent storage operations for a configuration."""

        self._require_configuration(configuration_id)
        return self._operation_repository.list_operations(
            configuration_id,
            limit=limit,
        )

    async def delete_configuration(
        self,
        configuration_id: UUID,
        *,
        force: bool = False,
    ) -> bool:
        """Delete or disable a storage configuration."""

        return await config_workflows.delete_or_disable_configuration(
            configuration_id=configuration_id,
            configuration_repository=self._configuration_repository,
            require_configuration=self._require_configuration,
            require_maintenance_for_mutation=self._require_maintenance_for_mutation,
            force=force,
        )

    def get_overview(self) -> StorageOverviewResponse:
        """Return aggregated stats for all storage configurations."""

        configurations = self._configuration_repository.list_configurations(
            include_disabled=True,
        )
        return storage_overview_builder.build_storage_overview(
            configurations=configurations,
            operation_repository=self._operation_repository,
            serializer=self._to_model,
        )

    def _require_plugin(
        self,
        provider: StorageProviderName,
    ) -> storage_providers.StorageProviderPlugin:
        plugin = self._plugin_registry.get(provider)
        if plugin is None:
            msg = f"No storage provider plugin registered for {provider.value}"
            raise RuntimeError(msg)
        return plugin

    def _require_configuration(self, configuration_id: UUID) -> StorageConfiguration:
        configuration = self._configuration_repository.get_by_id(configuration_id)
        if configuration is None:
            msg = f"Storage configuration {configuration_id} not found"
            raise ValueError(msg)
        return configuration

    def _to_model(
        self,
        configuration: StorageConfiguration,
    ) -> StorageConfigurationModel:
        return StorageConfigurationModel(
            id=configuration.id,
            name=configuration.name,
            provider=configuration.provider,
            config=configuration.config,
            enabled=configuration.enabled,
            supported_capabilities=set(configuration.supported_capabilities),
            default_use_cases=set(configuration.default_use_cases),
            metadata=configuration.metadata,
            created_at=configuration.created_at,
            updated_at=configuration.updated_at,
        )

    async def _require_maintenance_mode(self) -> None:
        """Ensure maintenance mode is active when a risky operation is requested."""
        if self._system_status_service is None:
            return
        await self._system_status_service.require_active()

    async def _require_maintenance_for_mutation(self) -> None:
        """Require maintenance mode when mutating configs while active backends exist."""
        if self._system_status_service is None:
            return
        has_enabled_config = bool(
            self._configuration_repository.list_configurations(include_disabled=False),
        )
        if not has_enabled_config:
            return
        await self._system_status_service.require_active()
