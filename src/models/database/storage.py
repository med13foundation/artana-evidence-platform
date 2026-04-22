"""
SQLAlchemy models for storage configurations and operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base


class StorageProviderEnum(str, Enum):
    LOCAL_FILESYSTEM = "local_filesystem"
    GOOGLE_CLOUD_STORAGE = "google_cloud_storage"


class StorageCapabilityEnum(str, Enum):
    PDF = "pdf"
    EXPORT = "export"
    RAW_SOURCE = "raw_source"


class StorageUseCaseEnum(str, Enum):
    PDF = "pdf"
    EXPORT = "export"
    RAW_SOURCE = "raw_source"
    DOCUMENT_CONTENT = "document_content"
    BACKUP = "backup"


class StorageOperationTypeEnum(str, Enum):
    STORE = "store"
    RETRIEVE = "retrieve"
    DELETE = "delete"
    LIST = "list"
    TEST = "test"


class StorageOperationStatusEnum(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


class StorageHealthStatusEnum(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


def _storage_enum(enum_cls: type[Enum], name: str) -> SQLEnum:
    return SQLEnum(
        enum_cls,
        name=name,
        values_callable=_enum_values,
    )


class StorageConfigurationModel(Base):
    """SQLAlchemy model for storage configurations."""

    __tablename__ = "storage_configurations"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    provider: Mapped[StorageProviderEnum] = mapped_column(
        _storage_enum(StorageProviderEnum, "storageproviderenum"),
        nullable=False,
        index=True,
    )
    config_data: Mapped[JSONObject] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supported_capabilities: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    default_use_cases: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    operations: Mapped[list[StorageOperationModel]] = relationship(
        "StorageOperationModel",
        back_populates="configuration",
        cascade="all, delete-orphan",
    )
    health_snapshot: Mapped[StorageHealthSnapshotModel] = relationship(
        "StorageHealthSnapshotModel",
        back_populates="configuration",
        uselist=False,
        cascade="all, delete-orphan",
    )


class StorageOperationModel(Base):
    """SQLAlchemy model for storage operation logs."""

    __tablename__ = "storage_operations"

    id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), primary_key=True)
    configuration_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("storage_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    operation_type: Mapped[StorageOperationTypeEnum] = mapped_column(
        _storage_enum(StorageOperationTypeEnum, "storageoperationtypeenum"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[StorageOperationStatusEnum] = mapped_column(
        _storage_enum(StorageOperationStatusEnum, "storageoperationstatusenum"),
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    configuration: Mapped[StorageConfigurationModel] = relationship(
        "StorageConfigurationModel",
        back_populates="operations",
    )


class StorageHealthSnapshotModel(Base):
    """SQLAlchemy model for storage health snapshots."""

    __tablename__ = "storage_health_snapshots"

    configuration_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("storage_configurations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[StorageProviderEnum] = mapped_column(
        _storage_enum(StorageProviderEnum, "storageproviderenum"),
        nullable=False,
    )
    status: Mapped[StorageHealthStatusEnum] = mapped_column(
        _storage_enum(StorageHealthStatusEnum, "storagehealthstatusenum"),
        nullable=False,
    )
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    details: Mapped[JSONObject] = mapped_column(JSON, nullable=False, default=dict)

    configuration: Mapped[StorageConfigurationModel] = relationship(
        "StorageConfigurationModel",
        back_populates="health_snapshot",
    )


__all__ = [
    "StorageCapabilityEnum",
    "StorageConfigurationModel",
    "StorageHealthSnapshotModel",
    "StorageHealthStatusEnum",
    "StorageOperationModel",
    "StorageOperationStatusEnum",
    "StorageOperationTypeEnum",
    "StorageProviderEnum",
    "StorageUseCaseEnum",
]
