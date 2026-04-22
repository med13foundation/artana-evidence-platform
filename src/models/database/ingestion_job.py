from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base

if TYPE_CHECKING:
    from .user_data_source import UserDataSourceModel

# SQLAlchemy model for ingestion job executions (Data Sources module).


class IngestionStatusEnum(str, Enum):
    """SQLAlchemy enum for ingestion job status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class IngestionTriggerEnum(str, Enum):
    """SQLAlchemy enum for ingestion job triggers."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    API = "api"
    WEBHOOK = "webhook"
    RETRY = "retry"


class IngestionJobKindEnum(str, Enum):
    """SQLAlchemy enum for logical ingestion-job workload kinds."""

    INGESTION = "ingestion"
    PIPELINE_ORCHESTRATION = "pipeline_orchestration"


class IngestionJobModel(Base):
    """
    SQLAlchemy model for data ingestion job executions.

    Tracks the complete lifecycle of data acquisition from user sources,
    including performance metrics, errors, and provenance information.
    """

    __tablename__ = "ingestion_jobs"

    # Primary key
    id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), primary_key=True)

    # Source relationship
    source_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("user_data_sources.id"),
        nullable=False,
        index=True,
    )
    job_kind: Mapped[IngestionJobKindEnum] = mapped_column(
        SQLEnum(
            IngestionJobKindEnum,
            name="ingestionjobkindenum",
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=IngestionJobKindEnum.INGESTION,
        server_default=IngestionJobKindEnum.INGESTION.value,
        index=True,
    )

    # Execution details
    trigger: Mapped[IngestionTriggerEnum] = mapped_column(
        SQLEnum(
            IngestionTriggerEnum,
            name="ingestiontriggerenum",
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=IngestionTriggerEnum.MANUAL,
        server_default=IngestionTriggerEnum.MANUAL.value,
    )
    triggered_by: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    triggered_at: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # Status and progress
    status: Mapped[IngestionStatusEnum] = mapped_column(
        SQLEnum(
            IngestionStatusEnum,
            name="ingestionstatusenum",
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=IngestionStatusEnum.PENDING,
        server_default=IngestionStatusEnum.PENDING.value,
        index=True,
    )
    started_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Results and metrics
    metrics: Mapped[JSONObject] = mapped_column(JSON, nullable=False, default=dict)
    errors: Mapped[list[JSONObject]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    # Provenance and metadata
    provenance: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    job_metadata: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Configuration snapshot
    source_config_snapshot: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    dictionary_version_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    replay_policy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="strict",
        server_default="strict",
    )

    # Relationships
    source: Mapped[UserDataSourceModel] = relationship(
        "UserDataSourceModel",
        back_populates="ingestion_jobs",
    )

    def __repr__(self) -> str:
        """String representation of the ingestion job."""
        return (
            f"<IngestionJob(id={self.id}, source={self.source_id}, "
            f"kind={self.job_kind}, status={self.status})>"
        )
