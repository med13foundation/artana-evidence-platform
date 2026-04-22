"""
Domain entities for storage configurations and operations.

These entities encapsulate storage provider metadata, configuration,
and audit logs in a type-safe manner.
"""

from __future__ import annotations

from collections.abc import Iterable  # noqa: TC003
from datetime import UTC, datetime
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.type_definitions.common import JSONObject  # noqa: TC001
from src.type_definitions.storage import (
    StorageHealthReport,
    StorageHealthStatus,
    StorageOperationRecord,
    StorageOperationStatus,
    StorageOperationType,
    StorageProviderCapability,
    StorageProviderConfigModel,
    StorageProviderMetadata,
    StorageProviderName,
    StorageProviderTestResult,
    StorageUseCase,
)

EMPTY_JSON_OBJECT: JSONObject = {}


def _empty_json_object() -> JSONObject:
    return dict(EMPTY_JSON_OBJECT)


class StorageConfiguration(BaseModel):
    """Represents a storage configuration defined by administrators."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str = Field(..., min_length=3, max_length=255)
    provider: StorageProviderName
    config: StorageProviderConfigModel
    enabled: bool = True
    supported_capabilities: tuple[StorageProviderCapability, ...] = Field(
        default_factory=tuple,
    )
    default_use_cases: tuple[StorageUseCase, ...] = Field(default_factory=tuple)
    metadata: JSONObject = Field(default_factory=_empty_json_object)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            msg = "Storage configuration name cannot be empty"
            raise ValueError(msg)
        return normalized

    def supports_capability(self, capability: StorageProviderCapability) -> bool:
        """Check if the configuration supports a given capability."""
        return capability in self.supported_capabilities

    def applies_to_use_case(self, use_case: StorageUseCase) -> bool:
        """Determine if this configuration is mapped to a use case."""
        return use_case in self.default_use_cases

    def with_updated_metadata(self, metadata: JSONObject) -> StorageConfiguration:
        """Return a new configuration with updated metadata."""
        update_payload: dict[str, object] = {
            "metadata": metadata,
            "updated_at": datetime.now(UTC),
        }
        return self.model_copy(update=update_payload)

    def with_updated_use_cases(
        self,
        use_cases: Iterable[StorageUseCase],
    ) -> StorageConfiguration:
        """Return a new configuration with updated default use cases."""
        seen: set[StorageUseCase] = set()
        deduped: list[StorageUseCase] = []
        for use_case in use_cases:
            if use_case in seen:
                continue
            seen.add(use_case)
            deduped.append(use_case)
        update_payload: dict[str, object] = {
            "default_use_cases": tuple(deduped),
            "updated_at": datetime.now(UTC),
        }
        return self.model_copy(update=update_payload)


class StorageOperation(BaseModel):
    """Domain representation of a storage operation audit record."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    configuration_id: UUID
    user_id: UUID | None
    operation_type: StorageOperationType
    key: str
    file_size_bytes: int | None = None
    status: StorageOperationStatus = StorageOperationStatus.PENDING
    error_message: str | None = None
    metadata: JSONObject = Field(default_factory=_empty_json_object)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def as_record(self) -> StorageOperationRecord:
        """Convert to the shared StorageOperationRecord model."""
        return StorageOperationRecord(
            id=self.id,
            configuration_id=self.configuration_id,
            user_id=self.user_id,
            operation_type=self.operation_type,
            key=self.key,
            file_size_bytes=self.file_size_bytes,
            status=self.status,
            error_message=self.error_message,
            metadata=self.metadata,
            created_at=self.created_at,
        )


class StorageHealthSnapshot(BaseModel):
    """In-memory representation of provider health data."""

    model_config = ConfigDict(frozen=True)

    configuration_id: UUID
    provider: StorageProviderName
    status: StorageHealthStatus
    last_checked_at: datetime
    details: JSONObject = Field(default_factory=_empty_json_object)

    def as_report(self) -> StorageHealthReport:
        """Convert to transferable health report."""
        return StorageHealthReport(
            configuration_id=self.configuration_id,
            provider=self.provider,
            status=self.status,
            last_checked_at=self.last_checked_at,
            details=self.details,
        )


__all__ = [
    "StorageConfiguration",
    "StorageHealthSnapshot",
    "StorageOperation",
    "StorageProviderMetadata",
    "StorageProviderTestResult",
]
