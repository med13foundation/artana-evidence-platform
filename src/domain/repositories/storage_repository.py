"""
Repository interfaces for storage configurations and operations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from src.domain.entities.storage_configuration import (
        StorageConfiguration,
        StorageHealthSnapshot,
        StorageOperation,
    )
    from src.type_definitions.common import JSONObject
    from src.type_definitions.storage import (
        StorageOperationRecord,
        StorageProviderTestResult,
        StorageUsageMetrics,
    )


class StorageConfigurationRepository(ABC):
    """Repository interface for storage configurations."""

    @abstractmethod
    def create(self, configuration: StorageConfiguration) -> StorageConfiguration:
        """Persist a new storage configuration."""

    @abstractmethod
    def update(self, configuration: StorageConfiguration) -> StorageConfiguration:
        """Persist changes to a configuration."""

    @abstractmethod
    def get_by_id(self, configuration_id: UUID) -> StorageConfiguration | None:
        """Retrieve a configuration by ID."""

    @abstractmethod
    def list_configurations(
        self,
        *,
        include_disabled: bool = False,
    ) -> list[StorageConfiguration]:
        """Return available storage configurations."""

    @abstractmethod
    def paginate_configurations(
        self,
        *,
        include_disabled: bool = False,
        page: int = 1,
        per_page: int = 25,
    ) -> tuple[list[StorageConfiguration], int]:
        """Return a page of storage configurations and total count."""

    @abstractmethod
    def delete(self, configuration_id: UUID) -> bool:
        """Delete (or soft-delete) a configuration."""


class StorageOperationRepository(ABC):
    """Repository interface for storage operations and health data."""

    @abstractmethod
    def record_operation(self, operation: StorageOperation) -> StorageOperationRecord:
        """Persist an operation log entry."""

    @abstractmethod
    def list_operations(
        self,
        configuration_id: UUID,
        *,
        limit: int = 100,
    ) -> list[StorageOperationRecord]:
        """List recent operations."""

    @abstractmethod
    def list_failed_store_operations(
        self,
        *,
        limit: int = 100,
    ) -> list[StorageOperationRecord]:
        """Return recent failed store operations for retry workflows."""

    @abstractmethod
    def update_operation_metadata(
        self,
        operation_id: UUID,
        metadata: JSONObject,
    ) -> StorageOperationRecord:
        """Persist metadata changes for an operation."""

    @abstractmethod
    def upsert_health_snapshot(
        self,
        snapshot: StorageHealthSnapshot,
    ) -> StorageHealthSnapshot:
        """Persist provider health information."""

    @abstractmethod
    def get_health_snapshot(
        self,
        configuration_id: UUID,
    ) -> StorageHealthSnapshot | None:
        """Fetch the latest health snapshot."""

    @abstractmethod
    def record_test_result(
        self,
        result: StorageProviderTestResult,
    ) -> StorageProviderTestResult:
        """Persist results of a connection test."""

    @abstractmethod
    def get_usage_metrics(
        self,
        configuration_id: UUID,
    ) -> StorageUsageMetrics | None:
        """Return aggregated usage metrics."""
