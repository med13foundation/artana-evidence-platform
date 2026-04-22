from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base


class ExtractionOutcomeEnum(str, Enum):
    """SQLAlchemy enum for extraction outcome status."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PublicationExtractionModel(Base):
    """SQLAlchemy model for extracted publication facts."""

    __tablename__ = "publication_extractions"

    id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), primary_key=True)

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
    queue_item_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("extraction_queue.id"),
        nullable=False,
        index=True,
        unique=True,
    )

    status: Mapped[ExtractionOutcomeEnum] = mapped_column(
        SQLEnum(
            ExtractionOutcomeEnum,
            name="extraction_outcome_enum",
            values_callable=lambda enum: [entry.value for entry in enum],
        ),
        nullable=False,
        index=True,
    )
    extraction_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        index=True,
    )
    processor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    processor_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    text_source: Mapped[str] = mapped_column(String(30), nullable=False)
    document_reference: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    facts: Mapped[list[JSONObject]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    extracted_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint(
            "queue_item_id",
            name="uq_publication_extractions_queue_item",
        ),
    )


__all__ = ["PublicationExtractionModel", "ExtractionOutcomeEnum"]
