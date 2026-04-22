from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base


class ExtractionStatusEnum(str, Enum):
    """SQLAlchemy enum for extraction queue status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractionQueueItemModel(Base):
    """SQLAlchemy model for queued publication extraction tasks."""

    __tablename__ = "extraction_queue"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
    )

    publication_id: Mapped[int | None] = mapped_column(
        ForeignKey("publications.id"),
        nullable=True,
        index=True,
    )
    pubmed_id: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    source_record_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    raw_storage_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )
    payload_ref: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("user_data_sources.id"),
        nullable=False,
        index=True,
    )
    ingestion_job_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("ingestion_jobs.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[ExtractionStatusEnum] = mapped_column(
        SQLEnum(
            ExtractionStatusEnum,
            name="extraction_status_enum",
            values_callable=lambda enum: [entry.value for entry in enum],
        ),
        nullable=False,
        default=ExtractionStatusEnum.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        index=True,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    queued_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "source_record_id",
            "extraction_version",
            name="uq_extraction_queue_source_record_version",
        ),
    )


__all__ = ["ExtractionQueueItemModel", "ExtractionStatusEnum"]
