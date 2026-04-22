"""
Storage type definitions for Artana Resource Library.

Provides typed contracts for storage configurations, operations,
and provider metadata that can be shared between backend and frontend.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .common import JSONObject  # noqa: TC001


class StorageProviderName(StrEnum):
    """Enumerates supported storage providers."""

    LOCAL_FILESYSTEM = "local_filesystem"
    GOOGLE_CLOUD_STORAGE = "google_cloud_storage"


class StorageProviderCapability(StrEnum):
    """Capabilities that a storage provider advertises."""

    PDF = "pdf"
    EXPORT = "export"
    RAW_SOURCE = "raw_source"


class StorageUseCase(StrEnum):
    """Use cases that can be mapped to storage configurations."""

    PDF = "pdf"
    EXPORT = "export"
    RAW_SOURCE = "raw_source"
    DOCUMENT_CONTENT = "document_content"
    BACKUP = "backup"


class StorageOperationType(StrEnum):
    """Type of storage operation for audit logging."""

    STORE = "store"
    RETRIEVE = "retrieve"
    DELETE = "delete"
    LIST = "list"
    TEST = "test"


class StorageOperationStatus(StrEnum):
    """Operation result states."""

    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


class StorageMetricEventType(StrEnum):
    """Metric classification for observability exports."""

    STORE = "store"
    RETRIEVE = "retrieve"
    TEST = "test"


class StorageProviderConfig(BaseModel):
    """Base class for provider-specific configuration."""

    model_config = ConfigDict(extra="forbid")

    provider: StorageProviderName


class LocalFilesystemConfig(StorageProviderConfig):
    """Configuration for the local filesystem provider."""

    provider: StorageProviderName = Field(
        default=StorageProviderName.LOCAL_FILESYSTEM,
        frozen=True,
    )
    base_path: Path | str = Field(
        ...,
        description="Absolute path where files should be stored.",
    )
    create_directories: bool = Field(
        default=True,
        description="Automatically create directories when missing.",
    )
    expose_file_urls: bool = Field(
        default=False,
        description="Enable generation of file:// URLs for debugging.",
    )


class GoogleCloudStorageConfig(StorageProviderConfig):
    """Configuration for the Google Cloud Storage provider."""

    provider: StorageProviderName = Field(
        default=StorageProviderName.GOOGLE_CLOUD_STORAGE,
        frozen=True,
    )
    bucket_name: str = Field(..., min_length=3)
    base_path: str = Field(
        default="/",
        description="Prefix inside the bucket for Artana artifacts.",
    )
    credentials_secret_name: str = Field(
        ...,
        description="Secret Manager name containing service account credentials.",
    )
    public_read: bool = Field(
        default=False,
        description="Whether files should be publicly accessible.",
    )
    signed_url_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86_400,
        description="TTL for signed download URLs.",
    )


StorageProviderConfigModel = LocalFilesystemConfig | GoogleCloudStorageConfig


class StorageConfigurationModel(BaseModel):
    """Runtime representation of a storage configuration."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    provider: StorageProviderName
    config: StorageProviderConfigModel
    enabled: bool = True
    supported_capabilities: set[StorageProviderCapability]
    default_use_cases: set[StorageUseCase]
    metadata: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class StorageProviderMetadata(BaseModel):
    """Metadata returned by providers during registration or testing."""

    model_config = ConfigDict(extra="allow")

    provider: StorageProviderName
    capabilities: set[StorageProviderCapability] = Field(default_factory=set)
    default_path: str | None = None
    notes: str | None = None


class StorageOperationRecord(BaseModel):
    """Audit log entry for a storage operation."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    configuration_id: UUID
    user_id: UUID | None = None
    operation_type: StorageOperationType
    key: str
    file_size_bytes: int | None = None
    status: StorageOperationStatus
    error_message: str | None = None
    metadata: JSONObject = Field(default_factory=dict)
    created_at: datetime


class StorageProviderTestResult(BaseModel):
    """Result payload from testing a storage configuration."""

    model_config = ConfigDict(extra="forbid")

    configuration_id: UUID
    provider: StorageProviderName
    success: bool
    message: str | None = None
    checked_at: datetime
    capabilities: set[StorageProviderCapability] = Field(default_factory=set)
    latency_ms: int | None = None
    metadata: JSONObject = Field(default_factory=dict)


class StorageUsageMetrics(BaseModel):
    """Aggregated storage usage metrics."""

    model_config = ConfigDict(extra="forbid")

    configuration_id: UUID
    total_files: int
    total_size_bytes: int
    last_operation_at: datetime | None = None
    error_rate: float | None = None


class StorageHealthStatus(StrEnum):
    """Health indicator for providers."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class StorageHealthReport(BaseModel):
    """Health snapshot returned to the UI."""

    model_config = ConfigDict(extra="forbid")

    configuration_id: UUID
    provider: StorageProviderName
    status: StorageHealthStatus
    last_checked_at: datetime
    details: JSONObject = Field(default_factory=dict)


class StorageUrlModel(BaseModel):
    """Represents a generated file URL."""

    model_config = ConfigDict(extra="forbid")

    key: str
    url: HttpUrl
    expires_at: datetime | None = None


class SignedUrlRequest(BaseModel):
    """Parameters for requesting a signed download URL."""

    model_config = ConfigDict(extra="forbid")

    key: str
    expires_in: timedelta = Field(default=timedelta(hours=1))


class StorageConfigurationStats(BaseModel):
    """Aggregated metrics for a storage configuration."""

    model_config = ConfigDict(extra="forbid")

    configuration: StorageConfigurationModel
    usage: StorageUsageMetrics | None = None
    health: StorageHealthReport | None = None


class StorageOverviewTotals(BaseModel):
    """Totals for the storage platform overview."""

    model_config = ConfigDict(extra="forbid")

    total_configurations: int
    enabled_configurations: int
    disabled_configurations: int
    healthy_configurations: int
    degraded_configurations: int
    offline_configurations: int
    total_files: int
    total_size_bytes: int
    average_error_rate: float | None = None


class StorageOverviewResponse(BaseModel):
    """Overview response returned to the UI."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    totals: StorageOverviewTotals
    configurations: list[StorageConfigurationStats]


class StorageMetricEvent(BaseModel):
    """Structured metric payload emitted for observability exports."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    configuration_id: UUID | None
    provider: StorageProviderName
    event_type: StorageMetricEventType
    status: StorageOperationStatus
    duration_ms: int | None = None
    metadata: JSONObject = Field(default_factory=dict)
    emitted_at: datetime


__all__ = [
    "GoogleCloudStorageConfig",
    "LocalFilesystemConfig",
    "SignedUrlRequest",
    "StorageConfigurationModel",
    "StorageConfigurationStats",
    "StorageHealthReport",
    "StorageHealthStatus",
    "StorageMetricEvent",
    "StorageMetricEventType",
    "StorageOperationRecord",
    "StorageOperationStatus",
    "StorageOperationType",
    "StorageOverviewResponse",
    "StorageOverviewTotals",
    "StorageProviderCapability",
    "StorageProviderConfig",
    "StorageProviderConfigModel",
    "StorageProviderMetadata",
    "StorageProviderName",
    "StorageProviderTestResult",
    "StorageUrlModel",
    "StorageUsageMetrics",
    "StorageUseCase",
]
