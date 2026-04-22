"""
Utilities for recording storage operations with observability hooks.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities.storage_configuration import (
    StorageConfiguration,
    StorageOperation,
)
from src.domain.services.storage_providers import StorageOperationError
from src.type_definitions.storage import (
    StorageMetricEvent,
    StorageMetricEventType,
    StorageOperationRecord,
    StorageOperationStatus,
    StorageOperationType,
)

if TYPE_CHECKING:
    from pathlib import Path
    from uuid import UUID

    from src.domain.repositories.storage_repository import StorageOperationRepository
    from src.domain.services.storage_metrics import StorageMetricsRecorder
    from src.domain.services.storage_providers import StorageProviderPlugin
    from src.type_definitions.common import JSONObject


async def record_store_operation(  # noqa: PLR0913 - explicit workflow inputs keep Clean Architecture boundaries
    *,
    configuration: StorageConfiguration,
    plugin: StorageProviderPlugin,
    operation_repository: StorageOperationRepository,
    metrics_recorder: StorageMetricsRecorder,
    key: str,
    file_path: Path,
    content_type: str | None,
    user_id: UUID | None,
    metadata: JSONObject | None,
) -> StorageOperationRecord:
    """Store a file and persist audit + metric events."""

    validated_config = await plugin.validate_config(configuration.config)
    operation_metadata: JSONObject = metadata or {}
    operation = StorageOperation(
        id=uuid4(),
        configuration_id=configuration.id,
        user_id=user_id,
        operation_type=StorageOperationType.STORE,
        key=key,
        metadata=operation_metadata,
        status=StorageOperationStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    started_at = datetime.now(UTC)
    try:
        storage_key = await plugin.store_file(
            validated_config,
            file_path=file_path,
            key=key,
            content_type=content_type,
        )
        success_operation = operation.model_copy(
            update={
                "key": storage_key,
                "status": StorageOperationStatus.SUCCESS,
            },
        )
    except StorageOperationError as exc:
        failure_operation = operation.model_copy(
            update={
                "status": StorageOperationStatus.FAILED,
                "error_message": str(exc),
            },
        )
        operation_repository.record_operation(failure_operation)
        failure_metadata: JSONObject = {
            **operation_metadata,
            "error": str(exc),
        }
        _record_metric(
            recorder=metrics_recorder,
            configuration=configuration,
            status=StorageOperationStatus.FAILED,
            started_at=started_at,
            metadata=failure_metadata,
            event_type=StorageMetricEventType.STORE,
        )
        raise
    else:
        recorded = operation_repository.record_operation(success_operation)
        success_metadata: JSONObject = {
            **operation_metadata,
            "key": storage_key,
        }
        _record_metric(
            recorder=metrics_recorder,
            configuration=configuration,
            status=StorageOperationStatus.SUCCESS,
            started_at=started_at,
            metadata=success_metadata,
            event_type=StorageMetricEventType.STORE,
        )
        return recorded


async def record_retrieve_operation(  # noqa: PLR0913 - explicit workflow inputs keep Clean Architecture boundaries
    *,
    configuration: StorageConfiguration,
    plugin: StorageProviderPlugin,
    operation_repository: StorageOperationRepository,
    metrics_recorder: StorageMetricsRecorder,
    key: str,
    user_id: UUID | None,
    metadata: JSONObject | None,
) -> str:
    """Retrieve a file URL and persist audit + metric events."""

    validated_config = await plugin.validate_config(configuration.config)
    operation_metadata: JSONObject = metadata or {}
    operation = StorageOperation(
        id=uuid4(),
        configuration_id=configuration.id,
        user_id=user_id,
        operation_type=StorageOperationType.RETRIEVE,
        key=key,
        metadata=operation_metadata,
        status=StorageOperationStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    started_at = datetime.now(UTC)
    try:
        url = await plugin.get_file_url(validated_config, key)
        success_operation = operation.model_copy(
            update={
                "status": StorageOperationStatus.SUCCESS,
            },
        )
    except StorageOperationError as exc:
        failure_operation = operation.model_copy(
            update={
                "status": StorageOperationStatus.FAILED,
                "error_message": str(exc),
            },
        )
        operation_repository.record_operation(failure_operation)
        failure_metadata: JSONObject = {
            **operation_metadata,
            "error": str(exc),
        }
        _record_metric(
            recorder=metrics_recorder,
            configuration=configuration,
            status=StorageOperationStatus.FAILED,
            started_at=started_at,
            metadata=failure_metadata,
            event_type=StorageMetricEventType.RETRIEVE,
        )
        raise
    else:
        operation_repository.record_operation(success_operation)
        success_metadata: JSONObject = {
            **operation_metadata,
            "url_generated": True,
        }
        _record_metric(
            recorder=metrics_recorder,
            configuration=configuration,
            status=StorageOperationStatus.SUCCESS,
            started_at=started_at,
            metadata=success_metadata,
            event_type=StorageMetricEventType.RETRIEVE,
        )
        return url


def record_test_metric(
    *,
    configuration: StorageConfiguration,
    recorder: StorageMetricsRecorder,
    status: StorageOperationStatus,
    duration_ms: int,
    metadata: JSONObject,
) -> None:
    """Emit a metric for provider connectivity tests."""

    recorder.record_event(
        StorageMetricEvent(
            event_id=uuid4(),
            configuration_id=configuration.id,
            provider=configuration.provider,
            event_type=StorageMetricEventType.TEST,
            status=status,
            duration_ms=duration_ms,
            metadata=metadata,
            emitted_at=datetime.now(UTC),
        ),
    )


def _record_metric(  # noqa: PLR0913 - helper requires explicit telemetry inputs
    *,
    recorder: StorageMetricsRecorder,
    configuration: StorageConfiguration,
    status: StorageOperationStatus,
    started_at: datetime,
    metadata: JSONObject,
    event_type: StorageMetricEventType,
) -> None:
    duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
    recorder.record_event(
        StorageMetricEvent(
            event_id=uuid4(),
            configuration_id=configuration.id,
            provider=configuration.provider,
            event_type=event_type,
            status=status,
            duration_ms=duration_ms,
            metadata=metadata,
            emitted_at=datetime.now(UTC),
        ),
    )


__all__ = [
    "record_retrieve_operation",
    "record_store_operation",
    "record_test_metric",
]
