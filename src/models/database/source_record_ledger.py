"""SQLAlchemy model for source record idempotency fingerprints."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SourceRecordLedgerModel(Base):
    """Persisted fingerprint ledger per source external record id."""

    __tablename__ = "source_record_ledger"

    source_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("user_data_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    external_record_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    first_seen_job_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_seen_job_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_changed_job_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index(
            "idx_source_record_ledger_source_last_processed",
            "source_id",
            "last_processed_at",
        ),
    )


__all__ = ["SourceRecordLedgerModel"]
