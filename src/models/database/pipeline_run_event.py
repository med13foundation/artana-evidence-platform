"""SQLAlchemy model for append-only pipeline run trace events."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base


class PipelineRunEventModel(Base):
    """Append-only pipeline trace event persisted per pipeline run."""

    __tablename__ = "pipeline_run_events"

    seq: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    research_space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("research_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("user_data_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_run_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    scope_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="info",
        server_default="info",
        index=True,
    )
    status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    agent_kind: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    queue_wait_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    timeout_budget_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    __table_args__ = (
        Index(
            "idx_pipeline_run_events_source_run_occurred",
            "source_id",
            "pipeline_run_id",
            "occurred_at",
        ),
        Index(
            "idx_pipeline_run_events_run_scope",
            "pipeline_run_id",
            "scope_kind",
            "scope_id",
        ),
        Index(
            "idx_pipeline_run_events_run_agent",
            "pipeline_run_id",
            "agent_kind",
            "agent_run_id",
        ),
    )


__all__ = ["PipelineRunEventModel"]
