"""SQLAlchemy model for per-source incremental sync checkpoints."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base


class SourceSyncStateModel(Base):
    """Persisted checkpoint state used for incremental source ingestion."""

    __tablename__ = "source_sync_state"

    source_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("user_data_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    checkpoint_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="none",
    )
    checkpoint_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    query_signature: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    last_successful_job_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_successful_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_attempted_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    upstream_etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    upstream_last_modified: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


__all__ = ["SourceSyncStateModel"]
