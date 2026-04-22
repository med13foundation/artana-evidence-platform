"""
Mappings between storage domain entities and SQLAlchemy models.
"""

from __future__ import annotations

from uuid import UUID

from src.domain.entities.storage_configuration import (
    StorageConfiguration,
    StorageHealthSnapshot,
    StorageOperation,
)
from src.models.database.storage import (
    StorageConfigurationModel,
    StorageHealthSnapshotModel,
    StorageHealthStatusEnum,
    StorageOperationModel,
    StorageOperationStatusEnum,
    StorageOperationTypeEnum,
    StorageProviderEnum,
)
from src.type_definitions.storage import (
    GoogleCloudStorageConfig,
    LocalFilesystemConfig,
    StorageHealthStatus,
    StorageOperationRecord,
    StorageOperationStatus,
    StorageOperationType,
    StorageProviderCapability,
    StorageProviderConfigModel,
    StorageProviderName,
    StorageUseCase,
)

_CONFIG_MODEL_BY_PROVIDER: dict[
    StorageProviderName,
    type[StorageProviderConfigModel],
] = {
    StorageProviderName.LOCAL_FILESYSTEM: LocalFilesystemConfig,
    StorageProviderName.GOOGLE_CLOUD_STORAGE: GoogleCloudStorageConfig,
}


class StorageMapper:
    """Helper class for mapping between persistence and domain models."""

    @staticmethod
    def configuration_from_model(
        model: StorageConfigurationModel,
    ) -> StorageConfiguration:
        provider = StorageProviderName(model.provider.value)
        config_cls = _CONFIG_MODEL_BY_PROVIDER[provider]
        config = config_cls.model_validate(model.config_data)
        return StorageConfiguration(
            id=UUID(model.id),
            name=model.name,
            provider=provider,
            config=config,
            enabled=model.enabled,
            supported_capabilities=tuple(
                StorageProviderCapability(capability)
                for capability in model.supported_capabilities
            ),
            default_use_cases=tuple(
                StorageUseCase(use_case) for use_case in model.default_use_cases
            ),
            metadata=model.metadata_payload or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def apply_configuration_to_model(
        configuration: StorageConfiguration,
        model: StorageConfigurationModel | None = None,
    ) -> StorageConfigurationModel:
        instance = model or StorageConfigurationModel(id=str(configuration.id))
        instance.name = configuration.name
        instance.provider = StorageProviderEnum(configuration.provider.value)
        instance.config_data = configuration.config.model_dump(mode="json")
        instance.enabled = configuration.enabled
        instance.supported_capabilities = [
            capability.value for capability in configuration.supported_capabilities
        ]
        instance.default_use_cases = [
            use_case.value for use_case in configuration.default_use_cases
        ]
        instance.metadata_payload = configuration.metadata or {}
        instance.updated_at = configuration.updated_at
        instance.created_at = configuration.created_at
        return instance

    @staticmethod
    def operation_to_model(operation: StorageOperation) -> StorageOperationModel:
        model = StorageOperationModel(
            id=str(operation.id),
            configuration_id=str(operation.configuration_id),
            user_id=str(operation.user_id) if operation.user_id else None,
            operation_type=StorageOperationTypeEnum(operation.operation_type.value),
            key=operation.key,
            file_size_bytes=operation.file_size_bytes,
            status=StorageOperationStatusEnum(operation.status.value),
            error_message=operation.error_message,
            metadata_payload=operation.metadata or {},
        )
        model.created_at = operation.created_at
        model.updated_at = operation.created_at
        return model

    @staticmethod
    def operation_record_from_model(
        model: StorageOperationModel,
    ) -> StorageOperationRecord:
        return StorageOperationRecord(
            id=UUID(model.id),
            configuration_id=UUID(model.configuration_id),
            user_id=UUID(model.user_id) if model.user_id else None,
            operation_type=StorageOperationType(model.operation_type.value),
            key=model.key,
            file_size_bytes=model.file_size_bytes,
            status=StorageOperationStatus(model.status.value),
            error_message=model.error_message,
            metadata=model.metadata_payload or {},
            created_at=model.created_at,
        )

    @staticmethod
    def health_snapshot_from_model(
        model: StorageHealthSnapshotModel,
    ) -> StorageHealthSnapshot:
        return StorageHealthSnapshot(
            configuration_id=UUID(model.configuration_id),
            provider=StorageProviderName(model.provider.value),
            status=StorageHealthStatus(model.status.value),
            last_checked_at=model.last_checked_at,
            details=model.details or {},
        )

    @staticmethod
    def apply_health_snapshot_to_model(
        snapshot: StorageHealthSnapshot,
        model: StorageHealthSnapshotModel | None = None,
    ) -> StorageHealthSnapshotModel:
        instance = model or StorageHealthSnapshotModel(
            configuration_id=str(snapshot.configuration_id),
        )
        instance.provider = StorageProviderEnum(snapshot.provider.value)
        instance.status = StorageHealthStatusEnum(snapshot.status.value)
        instance.last_checked_at = snapshot.last_checked_at
        instance.details = snapshot.details or {}
        return instance
